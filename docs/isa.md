# PIO V0 instruction set (revision 0x21)

This is the current ISA implemented by `src/frontend/decoder.sv`,
`src/protocol_core.sv`, and `src/execution_unit.sv`, and assembled by
`tools/pioasm.py`. The host VERSION register returns `0x21`. This is a local,
PIO-inspired ISA, not a binary-compatible RP2040 implementation. Earlier
accumulator/UART programs cannot run on this engine.

## Machine state and timing

There is one state machine, 32 words of 16-bit instruction memory, a five-bit PC,
four 32-bit registers (X, Y, OSR, ISR), and separate four-word, 32-bit TX/RX FIFOs.
OSR serializes transmit data; ISR accumulates received data. IN and OUT counts
saturate at 32 and are separate from register contents. Twelve programmed output values include eight dedicated outputs and four
bidirectional pads; six physical inputs are independently synchronized.

An ordinary instruction takes one state-machine (SM) tick. A tick takes DIVIDER
core clocks (1–65535, zero clamps to one). The first tick is the clock after START.
Delay `d` makes the next instruction eligible `d + 1` ticks after retirement.
Taken branches have no extra penalty; IN/OUT widths 1–32 have the same latency.
Wrap has no extra tick. These are digital execution guarantees, not a physical
SPI speed or asynchronous timing guarantee.

WAIT and blocking FIFO instructions retry without advancing the PC or partially
updating registers/FIFOs. Enabled side-set applies on the first attempt, including
while stalled, and is reapplied on retries. Delay starts only after retirement.
An illegal instruction sets the fault flag and stops before side-set or data
updates. STOP and `ena=0` freeze timing; they stretch protocol waveforms. HALT
stops execution and retains the outputs and its PC.

START resets X/Y/OSR/ISR, counts (OUT=32, IN=0), divider/delay state, pending EXEC,
IRQ-wait state and fault, and sets PC to ENTRY. It preserves output levels,
configuration, FIFOs and IRQ/error flags. RESUME preserves execution state;
resuming a HALT executes the HALT again. Reset returns dedicated outputs to `0x01` and releases the four protocol pads, clears
queues/registers/configuration, and does not clear instruction memory.

The [host/interface specification](info.md) defines byte transactions, control
priority, atomic word access, configuration registers and reset details.

## Instruction encoding

Each 16-bit word is `{opcode[2:0], timing[4:0], argument[7:0]}`. Without side-set,
timing is a 0–31 delay. With EXECCTRL.bit15 set, timing[4] enables side-set for that
instruction, timing[3] is the value, timing[2:0] is a 0–7 delay. Optional side-set
disabled on an instruction still leaves only three delay bits.

| Opcode | Instruction / argument | Behavior |
| --- | --- | --- |
| 0 | JMP condition[7:5], target[4:0] | Branch conditions below |
| 1 | WAIT polarity[7], source[6:5], index[4:0] | Stall until input/IRQ matches polarity |
| 2 | IN source[7:5], count[4:0] | Shift low count source bits into ISR |
| 3 | OUT destination[7:5], count[4:0] | Shift count bits from OSR to destination |
| 4 | PUSH/PULL pull[7], conditional[6], block[5], zero[4:0] | FIFO transfer; see below |
| 5 | MOV destination[7:5], operation[4:3], source[2:0] | Register/pin transfer, optional inversion or bit reversal |
| 6 | IRQ zero[7], clear[6], wait[5], zero[4:3], index[2:0] | Set, clear, or set-and-wait for flag acknowledgment |
| 7 | SET destination[7:5], immediate[4:0] | Zero-extended immediate to pins(0), X(1), Y(2), PINDIRS(4) |

`0xC080` is the local HALT extension with timing field zero. Opcode 6 with argument
`0x80` is HALT for any timing field (for example `halt side 0` is `0xD080` when
optional side-set is enabled). NOP is `MOV Y,Y` (`0xA042`). HALT ignores
delay, applies enabled side-set, and retains output levels. Reserved encodings
halt with fault before changing data. All encoded JMP targets are five bits.

JMP conditions: 0 always, 1 X==0, 2 X--, 3 Y==0, 4 Y--, 5 X!=Y, 6 configured
input pin high, 7 OSR count below pull threshold. Decrement tests the old value for
nonzero and always decrements modulo2^32, including zero wrapping to `0xFFFFFFFF`.

WAIT sources: 0 absolute input index0..5; 1 relative to IN base (missing bits read0);
2 local IRQ index0–7. Other indices/sources fault. WAIT 1 IRQ clears that flag on
successful retirement. WAIT 0 IRQ does not clear it.

IN sources: pins0, X1, Y2, null3, ISR6, OSR7. Count field 0 means 32; otherwise1–31.
Right IN shifts ISR right and inserts the low source bits at its high end. Left IN
shifts left and inserts low source bits at its low end. IN count saturates at 32.
At the autopush threshold, enqueue the newly shifted value and clear ISR/count;
if RX is full the entire IN stalls before any shift. Autopush only applies to IN.

OUT destinations: pins0, X1, Y2, null3 (discard), PINDIRS4, PC5, ISR6, EXEC7. PINDIRS uses the OUT mapping and normal atomic
shift/autopull rules; dedicated-output direction writes are ignored. Right OUT extracts low bits; left OUT extracts high bits; the
extracted result is right-aligned, zero extended, and OSR shifts with zero fill.
OUT count saturates at 32. OUT ISR replaces ISR and sets IN count to the shift width.
OUT PC branches using the low five extracted bits. With autopull, an empty OSR
(count >= threshold) pulls a word immediately before the OUT on the same tick;
an empty TX FIFO stalls. No refill occurs in the background or after other opcodes.

PULL replaces OSR and clears OUT count. Conditional PULL acts only when OSR is
empty. Blocking PULL waits for data; nonblocking empty PULL uses X and sets DEBUG3.
PUSH enqueues ISR and clears ISR/IN count. Conditional PUSH acts only when IN count
meets the push threshold. Blocking PUSH waits for space; nonblocking full PUSH
drops the value, clears ISR/count and sets DEBUG2. Skipped conditional operations
still retire and apply delay/side-set.

MOV sources: pins0, X1, Y2, null3, status5 (FIFO_LEVEL packing), ISR6, OSR7.
Destinations: pins0, X1, Y2, EXEC4, PC5, ISR6, OSR7. Operation 0 copies, 1 inverts
all 32 bits, 2 reverses all 32 bits; 3 faults. MOV ISR/OSR resets the corresponding
shift count. MOV PC uses low five bits.

MOV/OUT EXEC executes the low 16-bit result on the next eligible tick, after the
originating instruction's delay. The original instruction advances PC once. An
injected instruction holds that PC unless it takes a branch/writes PC; it may
inject another instruction. Its own waits, delays, side-set and faults apply.
PC readback during injection is the already-advanced program-memory address.

IRQ SET sets a flag; CLEAR clears it. IRQ WAIT sets a flag once, then stalls until
the host clears it. Relative/multi-SM IRQ indexing is not supported. Concurrent
firmware sets win host clears; firmware clears win host sets. Flags are visible by
polling the host interface; there is no dedicated interrupt output pin.

## Operand encodings

Numbers below are encoded selectors, not host data-map addresses. A dash is an
illegal selector for that instruction. `pins` as a source reads synchronized
inputs, not the output latch. `status` is the packed TX/RX FIFO level word.

| Selector | IN source | OUT destination | MOV source | MOV destination | SET destination |
| --- | --- | --- | --- | --- | --- |
| 0 | pins | pins | pins | pins | pins |
| 1 | X | X | X | X | X |
| 2 | Y | Y | Y | Y | Y |
| 3 | null (zero) | null (discard) | null (zero) | — | — |
| 4 | — | — | — | EXEC | — |
| 5 | — | PC | status | PC | — |
| 6 | ISR | ISR | ISR | ISR | — |
| 7 | OSR | EXEC | OSR | OSR | — |

Illegal encodings include WAIT source 3, WAIT GPIO/PIN indices above 5, WAIT IRQ
indices above 7, unsupported table entries, PUSH/PULL with nonzero argument[4:0],
MOV operation 3, and SET destinations other than 0,1,2,4. IRQ requires argument[4:3]=0 and
does not permit clear and wait together; argument[7]=1 is illegal except HALT's
argument `0x80`. All JMP condition values 0–7 are valid. There is no relative IRQ addressing or second state machine.

## Configuration required by assembly

Configuration is written through the host while stopped; it is not encoded in
the program. See [the host data map](info.md#32-bit-data-map) for access details.

| Register | Fields used by instructions |
| --- | --- |
| SHIFTCTRL (`0x10`) | bit0 OUT shift right, bit1 IN shift right; zero selects left. bit2 autopull, bit3 autopush. [8:4] pull threshold, [13:9] push threshold; zero means 32. |
| EXECCTRL (`0x11`) | [4:0] wrap bottom, [9:5] wrap top, [14:10] entry, bit15 optional one-bit side-set enable. |
| PINCTRL (`0x12`) | [2:0] OUT/MOV base, [6:3] OUT/MOV width; [10:8] SET base, [14:11] SET width; bit16 IN base, [19:17] side-set output, bit20 JMP input. |
| DIVIDER (`0x13`) | Low 16 bits: core clocks per SM tick; zero becomes one. |

OUT/MOV and SET map the low bits of their result to separate output ranges and
preserve all other outputs. Width zero or above eight means eight. Ranges clip at
output 7 rather than wrapping. IN/MOV input sources use the six-bit synchronized
input vector shifted right by IN base, zero-extended to 32 bits. Side-set writes
one selected output and wins if it overlaps the instruction's output range.

Inputs pass through two flip-flops clocked by the core clock; instructions see
the previous synchronized value at their execution edge. They do not sample the
external pad instantaneously. A protocol must leave time for external propagation,
two synchronization stages, and clock-phase uncertainty before consuming a bit.

Extended ROUTE, DIRS, OD and FILTER fields are specified in the
[architecture contract](pio21_contract.md#additive-stopped-state-configuration).
ROUTE enables 12-output mapping with clipped writes, six-input selection, and
side-set targeting direction. SET PINDIRS uses SET mapping; OUT PINDIRS uses OUT
mapping, including atomic autopull/stall behavior. Side-set wins overlaps on its
selected state and applies even on a stall; illegal instructions apply none.
Input indices outside the real vector read zero after base mapping; encoded WAIT
GPIO/PIN indices6..31 fault. Capability masking preserves fixed output directions.

## Assembler syntax

Run `python tools/pioasm.py examples/spi_mode0.asm` to produce one four-digit hex
word per line. `-o path.hex` selects a different output. Programs may contain at
most 32 instructions. The assembler accepts case-insensitive mnemonics, `;`
comments, labels (`name:`), comma- or whitespace-separated operands, and ordinary
decimal or `0x` hexadecimal operand literals. Label names begin with a letter or
underscore and contain letters, digits and underscores.

| Instruction | Accepted forms |
| --- | --- |
| JMP | `jmp label` or `jmp condition, label`; condition: `always`, `!x`, `x--`, `!y`, `y--`, `x!=y`, `pin`, `!osre`. Numeric targets 0–31 also work. |
| WAIT | `wait 0/1, gpio/pin/irq, index` |
| IN / OUT | `in source, count` / `out destination, count`; counts 1–32 (write `32`, not encoded zero). |
| PUSH | `push [iffull] [block/noblock]`; brackets here indicate optional operands, not delay syntax. Default is unconditional blocking. |
| PULL | `pull [ifempty] [block/noblock]`; default is unconditional blocking. |
| MOV | `mov destination, source`, `mov destination, ~source`, `mov destination, ::source` |
| IRQ | `irq set, index`, `irq clear, index`, `irq wait, index` |
| SET | `set pins/x/y/pindirs, immediate`; immediate 0–31. |
| Pseudoinstructions | `nop` = MOV Y,Y; `halt` = local HALT extension. |

Append `[d]` for a decimal delay. A program-wide `.sideset` directive changes
encoding to the optional one-bit side-set layout and allows `side 0` / `side 1`.
The order is `instruction operands side value [delay]`, for example
`in pins, 1 side 1 [7]`. Instructions that omit `side` preserve that output but
still have only three delay bits in a `.sideset` program. The host must separately
enable EXECCTRL.bit15; the directive does not configure hardware. There are no
`.wrap`, `.origin`, pin-assignment, or clock directives in this assembler.

## Protocol examples

- [UART TX](../examples/uart_v0.asm): right-shift OSR for LSB-first UART framing;
  output delays encode start/data/stop timing.
- [UART RX](../examples/uart_rx.asm): wait for start and sample synchronized input
  into ISR with timed instructions.
- [SPI mode 0](../examples/spi_mode0.asm): left-shift OSR/ISR for MSB-first full
  duplex, with SCLK on side-set. See [SPI setup and timing](spi_mode0.md).


- [I2C controller](i2c.md): 24-word FIFO command firmware, open-drain pads, clock stretching and recovery.
