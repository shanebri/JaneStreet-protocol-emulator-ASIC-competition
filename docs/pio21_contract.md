> This contract defines the compatible per-engine revision 0x21 behavior.
> The implemented [dual-PIO extension](dual_pio.md) adds a second independent
> instance, bank selection, static output ownership and group commands.

# PIO 0x21 architecture contract

This contract precedes implementation. One state machine, 32x16 instruction RAM,
four-word TX/RX FIFOs, 8x4 tile allocation and 50 MHz target are retained.

## Ownership and transport

| Physical pins | Logical output/value/direction | Logical input |
| --- | --- | --- |
| uo[7:0] | 0..7, fixed output | none |
| uio[4], uio[5], uio[6], uio[7] | 8, 9, 10, 11 | 2, 3, 4, 5 |
| ui[6], ui[7] | none | 0, 1 |
| uio[3:0] | host only | host only |

ui[3:0], ui[4], ui[5] remain address, WR, RD. Synchronous transactions
transfer low then high nibble. Both strobes must be sampled low between beats.
Held strobes never repeat. Read data is valid after the accepted rising clock
edge (clock-to-Q plus combinational delay), and held through RD. Only uio[3:0]
drive during enabled, armed, exclusive RD. Idle/reset/disable/WR/RD+WR release
host drivers. First write beat stages; second matching beat commits once. First
read beat captures and accepts one byte read; second returns its saved high half.
DATA_0 first beat snapshots/pops RX once, even if abandoned: finish normal reads.
Idle preserves phase indefinitely. Any observed address change or opposite
direction discards phase. RD+WR discards phase without architectural effects.
Reset/disable discard phase; a sampled enabled low-strobe cycle re-arms transfers.

A minimum byte uses four clocks including both low gaps (80 ns at 50 MHz).
A four-byte word uses 16 clocks, or 20 including selector (400 ns, 2.5 Mword/s).
Reads pop at the first DATA_0 beat; writes commit on DATA_3's second beat.
FIFO depth absorbs bursts, not a sustained service deficit. The adapter exposes
the original byte address/data/acceptance interface for future replacement.

## Reset and timing qualification

The implementation retains **A1, externally synchronous state reset**. Clock
must run while reset is low. Hold `rst_n=0` through at least one rising edge
with valid setup/hold; a pulse entirely between edges is not a state reset.
Reset is sampled regardless of `ena`. IMEM retains its program and rejects
writes at every reset edge; all bank staging, FIFO metadata and execution state
reset. FIFO storage also rejects reset-edge writes, although its old words are
not architectural state after the level resets to zero.

Hold RD and WR low during reset and release. After release, sample one rising
edge with `rst_n=1`, `ena=1`, RD=WR=0 to re-arm. The first beat may be accepted
at the following rising edge. No ready wire or extra command cycle is added.
START still commits on its final high-nibble edge, and the first execution tick
is the following enabled edge. Runtime disable discards transport phase and
requires the same enabled idle re-arm edge; it preserves selection, staging,
firmware and execution state. RD+WR resynchronization also requires re-arm.

Raw reset immediately disables both host and protocol pad OEs without a clock.
With a stopped clock, assertion releases drive but does not reset state. Keep
reset asserted until a clock edge has sampled it before releasing reset and
re-arming. An asynchronous reset source must be conditioned by the system to
meet this synchronous contract; this design adds no release synchronizer.

For this timing experiment, keep the existing 20 ns clock, 4 ns input **min and
max** delays, 4 ns output **min and max** delays, 0.25 ns uncertainty, 0.15 ns
clock transition, 0.95/1.05 early/late derates, existing input driver and 0.006 pF
output loads. These are preserved block-boundary budgets, not measured board
delays. Production continues to use the flow's fallback SDC; no reset, enable,
host multicycle or asynchronous input exception is installed. The six protocol
inputs remain timed until mapped first-stage synchronizer endpoints and CDC
requirements can be qualified. Reset-to-OE paths remain timed. Operational
case analysis is a separate diagnostic session only.

Required corners are `nom_slow_1p08V_125C`, `nom_typ_1p20V_25C` and
`nom_fast_1p32V_m40C`, retaining nominal RC. Acceptance requires setup/hold
slack >= 0 ns, zero TNS/violating endpoints, zero slew/cap/fanout violations and
zero unexplained parasitic annotation gaps at all three corners. No additional
engineering margin or unrun RC corner is implied. Preserve DRC/LVS/antenna and
structural checks. The implementation remains an experiment until routed results
and independent per-port/register/reset reports satisfy these requirements.

## Additive stopped-state configuration

Existing byte addresses and selectors 0x00..0x15 retain meaning, except PINS
selector 4 expands to 12 bits and INPUT byte E expands to six bits. VERSION=0x21.
New selectors use the existing little-endian 6,7,9,A staging/snapshot interface.

| Selector | Fields | Reset |
| --- | --- | --- |
| 0x16 ROUTE | bit0 extended enable; [4:1] OUT/MOV base; [8:5] width; [12:9] SET base; [16:13] width; [19:17] IN base; [23:20] side-set index; [26:24] JMP input; bit27 side-set targets directions | 0 |
| 0x17 DIRS | [11:8] programmed pad direction; [7:0] read as FF, writes ignored | 0x0FF |
| 0x18 OD | [11:8] open drain; other bits read zero, writes ignored | 0 |
| 0x19 FILTER | [3:0] enable four-sample qualification on pad inputs | 0 |

All listed configuration is writable only stopped; unsupported bits read zero.
ROUTE=0 uses original PINCTRL fields, width zero/>8 means eight, clipping at
index 7. Extended width zero/>12 means twelve; ranges clip at index 11; base
12..15 writes nothing. IN base/JMP 6..7 read zero; side-set 12..15 does nothing.
WAIT GPIO/PIN encoded indices 0..5 are legal; PIN is base relative, missing bits
read zero; 6..31 fault. OUT/SET PINDIRS destination=4 uses the respective mapping.
Side-set wins only on its selected state; value and direction can update together.
Illegal instructions have no side-set effects. Stalled OUT is atomic.

DIRS is programmed capability-masked direction, not electrical OE: in OD mode
value one releases even when DIRS=1. Pad layer implements push-pull data=value,
OE=direction; OD data=0, OE=direction AND NOT value. Readback always uses pads.
Reset state is PINS=0xF01, DIRS=0x0FF, OD=0. Protocol OE is also gated by rst_n
immediately, before a resetting edge. State reset is synchronous. STOP/HALT/
fault/ena=0 preserve state, potentially holding a bus low. START preserves pad
state/configuration. CONTROL bit5 ABORT_RELEASE stops and clears all four pad
directions; priority over STOP/START/RESUME; bit2 FIFO clear is permitted with
abort, otherwise abort preserves queues. Error-clear remains independently valid.
START/RESUME do not re-arm directions. Live FIFO and IRQ accesses remain available.

All six inputs have two synchronizer stages even stopped/disabled. Instructions
consume their previous registered result. Enabled pad filters require four equal
successive synchronized samples, adding four clocks to visibility (5–6 clocks
from asynchronous transition to observable qualified state). At 50 MHz this
rejects ideal digital pulses <=50 ns; it is not an analog compliance guarantee.
Firmware waits long enough after driving SCL low to flush stale high samples.
Data must be established before enabling push-pull output; atomic RTL updates
do not prove analog glitch freedom.

## Firmware boundary

I2C uses bounded, FIFO-streamed commands, with waveform sequencing and stretching
handled by instructions. No protocol FSM or host waveform register writes.
Default SDA output8/input2, SCL output9/input3; routing is configurable.
The implementation guide specifies command words, timing, service deadlines,
status interpretation and bus clear. Physical fit/timing require CMOS5L flow;
simulation and generic synthesis alone do not establish them.
