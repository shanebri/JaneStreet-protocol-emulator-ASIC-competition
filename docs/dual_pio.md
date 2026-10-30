# Dual PIO extension, revision 1

The ASIC contains two independent PIO engines. Each has a 32x16 writable
instruction store, four-word 32-bit TX and RX FIFOs, X/Y/OSR/ISR, five-bit PC,
divider, delay, EXEC state, routing/configuration, output latches, IRQs and errors.
Both can execute an ordinary instruction on the same core edge at divider 1.
The ISA and explicit stall/delay rules in [isa.md](isa.md) apply to each engine.

The implementation follows the recommended option in the
[design proposal](dual_pio_design_proposal.md). It shares the existing host nibble
adapter, six input synchronizers, four continuously running input qualifiers,
clock/reset, and final pad boundary. FILTER enable remains per engine. Sampling
latency and the previous-edge execution view are unchanged.

There is no direct shared IRQ bank, new instruction, SRAM, DMA, larger FIFO,
fractional divider, or USB/Ethernet logic in this extension.

## Discovery and engine selection

The host byte transport and existing register addresses are unchanged. Reading
byte address `F` returns `0x21`, the compatible ISA/transport revision. Existing
engine-0 software, including the exact I2C version check, continues to work.

A complete byte write of 0 or 1 to address `F` selects that engine. Other values
are ignored. Reset selects engine 0. Bytes `0..E` address the selected engine.
`ena=0` discards the adapter's nibble phase but retains selection and both host
contexts. Engine selection does not start, stop, clear, or reconfigure an engine.

Each engine has its own IMEM_ADDR/low-byte stage, DATA_ADDR, word-write staging,
and saved read snapshot. A selection change cannot redirect staged bytes or a
previously popped RX word. Switching back permits completing the original word.
As in revision 0x21, software must supply all four bytes of every new word;
there is no staging-byte validity mask.

All transactions still require low then high nibble and low-strobe gaps.
Selection commits only on byte-F's accepted high write nibble. The adapter's
captured read byte supplies both read nibbles. Address/direction changes,
RD+WR, reset and disable retain their documented phase-abandonment rules.

## Common data selectors

These selectors are accessible from either engine's DATA_ADDR context. Writes
use byte registers `6,7,9,A`; reads use the same sequence. DATA_0 captures a
coherent complete word into that bank's existing snapshot. Common reads never
pop a FIFO. Unspecified selectors retain zero-read/ignored-write behavior.

| Selector | Name | Read / write |
| --- | --- | --- |
| `1A` | CAPABILITIES | R `0x50490102`: signature `0x5049`, extension revision 1, engine count 2. W ignored. Older hardware reads zero. |
| `1B` | GPIO_OWNER | R/W low 12 bits, one owner bit per output index: 0 engine0, 1 engine1. Reset zero. Upper bits ignored/read zero. Writes require safe stopped/released state. |
| `1C` | GROUP_CONTROL | W command masks described below; R zero. |
| `1D` | GLOBAL_STATUS | R STATUS0[7:0], STATUS1[15:8], IRQ0[23:16], IRQ1[31:24], captured together. W ignored. |
| `1E` | SELECTED_ENGINE | R selected engine index, zero-extended. W ignored. |

Existing selectors `00..19`, STATUS, PC, FIFO_LEVEL, IRQ, DEBUG and INPUT keep
their meaning within the selected bank. PINS/DIRS/OD read the engine's programmed
state, which can differ from physical pins when the peer owns an output.

## Output ownership and safe handoff

GPIO_OWNER selects the value of each of output indices 0..11. For protocol
pads8..11, the same owner selects direction and open-drain mode. The existing
pad layer then derives physical data and OE. All outputs have exactly one owner.
Both engines can always read all six physical inputs, with independent routing
and FILTER enables.

Reset gives engine 0 all output ownership; both engines start stopped. Programmed
values reset to `0xF01`, pad directions to zero, and OD to zero in both engines.
Reset gates the physical protocol OEs off immediately; state/ownership resets
are synchronous. Dedicated outputs retain the existing synchronous reset behavior.

Instructions on a non-owner engine update its own shadow PINS/DIRS normally and
retire without a grant or extra cycle. Only the owner's state reaches that pin.
This includes stalled side-set, SET/OUT/MOV and direction writes. There is no
round-robin arbitration or wired-OR combination of both engines.

GPIO_OWNER writes are accepted only when both engines are stopped. Every
bidirectional pad whose owner changes must also have direction zero in **both**
engines. If any check fails, the entire word is ignored; read back to confirm.
An OD value of one is not a substitute for direction zero in this check.

To hand off pins: stop both engines, clear both directions for changing pads,
prepare the incoming values/OD, write/read back GPIO_OWNER, then explicitly arm
the new directions. Dedicated outputs cannot be released; prepare matching old
and new levels when an ownership transition must not change their level.
This logical handoff does not establish analog glitch-free switching.

ABORT_RELEASE stops and clears only the selected engine's directions, including
its shadow directions. It releases only pads that engine owns. STOP/HALT/fault
and `ena=0` preserve outputs as before. START/RESUME never re-arm directions.

## Group commands and IRQs

GROUP_CONTROL consists of six independent two-engine masks. Within each mask,
bit0 targets engine0 and bit1 targets engine1:

| Word bits | Operation |
| --- | --- |
| 1:0 | START |
| 3:2 | STOP |
| 5:4 | RESUME |
| 7:6 | ABORT_RELEASE |
| 9:8 | FIFO_CLEAR |
| 11:10 | CLEAR_ERRORS |

Upper bits are ignored. Commands take effect on DATA_3's accepted high-nibble
write edge, independently of the selected engine. Per-engine priority remains
ABORT_RELEASE > STOP > START > RESUME. FIFO_CLEAR is accepted only if the target
was already stopped or receives STOP/ABORT on that edge; CLEAR_ERRORS remains
independent and new errors win. Group commands use the same core control signals
as the original selected-engine CONTROL byte.

For example, write GROUP_CONTROL=3 to START both; write `3<<2` to STOP both;
write `(1<<7)|(1<<9)` to abort/release and clear engine1 only. START resets the
selected engines' divider phase; the first tick is the next enabled core clock.
Equal dividers therefore start aligned. RESUME preserves prior divider/delay/EXEC
state and does not synchronize different paused phases. A stall can make the
two programs progress differently even when their divider phases are aligned.

Each engine retains eight local IRQ flags and its own IRQ WAIT handshake state.
Existing SET/CLEAR/WAIT encodings and host collision priority remain unchanged.
There is no external interrupt output. Use GLOBAL_STATUS for a coherent polling
snapshot, then select the relevant engine to acknowledge its flags. To notify
the peer, the host may write that engine's IRQ_SET selector. This has host
transport latency; direct firmware-to-firmware event signaling remains deferred.

## Python clients and serialization

`tools/pio_host.py` wraps an existing async byte transport. Share one PIOHost
instance across clients so selection and accepted byte operations are locked:

```python
from pio_host import PIOHost, CAPABILITIES, GPIO_OWNER, GROUP_CONTROL
from i2c_driver import I2C

host = PIOHost(transport)
pio0, pio1 = host.engine(0), host.engine(1)
assert await pio0.read_word(CAPABILITIES) == 0x50490102

# Both engines must be stopped and changing pads released before this write.
await pio0.write_word(GPIO_OWNER, 0x0FF)  # engine1 owns dedicated outputs
assert await pio0.read_word(GPIO_OWNER) == 0x0FF
bus = I2C(pio0)                         # I2C on engine0's protocol pads
await bus.configure(400_000)
result = await bus.transfer(0x48, b"\x00", read=2)
```

The wrapper selects its engine while holding the shared lock for every byte
operation; its word helpers hold the lock across the selector and all four bytes.
Different engines' byte sequences can safely interleave because hardware contexts
are banked. Clients using the same engine must serialize complete logical
operations as well. For example:

```python
async with pio0.transaction() as selected_bus:
    result = await I2C(selected_bus).transfer(0x48, b"\x00", read=2)
```

Use the yielded selected bus inside that context; calling pio0's locking methods
there would deadlock on its non-reentrant lock. Raw transport clients bypass
serialization. Transport errors/cancellation release the software lock but cannot
undo already accepted hardware operations; use the documented resync/abort and
reload/rearm procedures when recovering. A transport must bound its own I/O calls.

The physical host still has one aggregate service budget. With selector already
set, a word takes at least 16 core clocks; adding DATA_ADDR takes 20; adding
SM_SELECT takes 24. The convenience wrapper's per-byte selection can cost more.
Use word helpers or a selected transaction for efficient bursts. Four-word
queues absorb bursts and cannot correct a sustained bandwidth deficit.

## Validation and physical status

The current qualified ASIC baseline is `bb7c5ef`: its 8x4 CMOS5L build passes
extracted three-corner timing/electrical checks, routing/Magic DRC, antenna, LVS,
precheck and all 39 functional gate tests. See [project status](project_status.md)
for exact evidence, margins and check scope; the
[implementation record](dual_pio_verification.md) preserves the development tests.
Keep CLOCK_PERIOD=20 ns and the specified cycle behavior. Any ASIC change must
repeat the physical acceptance checks against its passing parent. Generic
synthesis, simulation and FPGA smoke tests do not qualify a changed ASIC layout.
