## Current implementation status

The dual-engine 8x4 CMOS5L baseline `bb7c5ef` is qualified at 50 MHz by extracted
STA/electrical checks, physical checks and 39 functional gate tests. See
[project status](project_status.md) for the exact run, margins and DRC scope.
Board interoperability and silicon operation are separate from that evidence.

## How it works

PIO V0 replaces the accumulator/UART architecture with a programmable I/O state
machine. The [dual-PIO extension](dual_pio.md) instantiates two independent
engines; this section describes each engine. A 32-word instruction memory feeds a combinational decoder and 32-bit
shift/register datapath. OSR serializes TX FIFO data; ISR collects data for the RX
FIFO. X and Y are independent 32-bit scratch registers for counters, comparisons,
loop control and default output data. All protocol framing is firmware.

This project borrows the instruction structure described in the
[Raspberry Pi PIO documentation](https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#hardware_pio),
but this document defines its own contract. It is not an RP2040-compatible core.
The host map and example binaries are incompatible with the earlier accumulator V0.

### Pins and clocking

| Pins | Function |
| --- | --- |
| `ui[3:0]` | Host byte-register address |
| `ui[4]`, `ui[5]` | WR, RD strobes |
| `ui[6]`, `ui[7]` | Protocol inputs 0 and 1; independent two-flop synchronizers |
| `uio[3:0]` | Bidirectional host nibble data |
| `uio[7:4]` | Independent protocol pads, default SDA/SCL on uio[4:5] |
| `uo[7:0]` | Programmable output pins 7 through 0; reset value `0x01` |
| `clk` | Shared synchronous host/core clock, target 50 MHz |
| `rst_n` | Synchronous state reset; immediate host/protocol OE gating |
| `ena` | Host/engine enable; keep high during timed protocols |

State reset requires a running clock and at least one rising edge with reset
low. Keep both host strobes low through release, then sample an enabled idle
edge before the first beat. Raw reset releases host/protocol OEs even with a
stopped clock. See the [reset and timing contract](pio21_contract.md#reset-and-timing-qualification)
for reset retention, re-arm and the unchanged timing budgets/corner requirements.

The complete logical correspondence and pad capabilities are defined in the
[single pin table](pio21_contract.md#ownership-and-transport). Dedicated outputs
retain indices 0..7. Protocol pads have value indices 8..11 and input indices 2..5.
All six inputs use two synchronizer stages, even while stopped or disabled.
Optional per-pad four-sample filters add latency; see the contract and I2C guide.

### Deterministic execution

An SM tick occurs every DIVIDER enabled clocks (integer 1–65535; zero writes become
one). The first tick is the clock following START. At DIVIDER=1 each ordinary
instruction completes on one rising edge. There is no fetch bubble, branch penalty,
multi-cycle ALU or background UART. IN/OUT count does not affect execution latency.

An instruction with delay `d` makes the next instruction eligible `d+1` SM ticks
later. Delay follows retirement, including taken branches. An explicit wait or
blocking FIFO instruction retries on each SM tick without changing PC, registers,
shift counts or FIFO contents. Side-set is the exception: it applies on the first
attempt and remains applied while stalled. Invalid instructions fault before any
side-set or architectural effect.

Autopull and autopush are atomic parts of OUT and IN respectively, with no hidden
extra tick. A FIFO word written on an edge to an empty TX FIFO becomes available
on the next SM tick. A full FIFO permits simultaneous dequeue/enqueue using the
old head; an empty FIFO has no same-edge bypass. These rules make boundary timing
explicit. Timed firmware must keep enough data queued to avoid intentional stalls.

`ena=0` freezes execution, divider and delay state and disables host transactions.
It stretches waveforms. STOP freezes the same execution state and retains outputs;
RESUME continues it. START begins a fresh execution at ENTRY. Reset returns outputs
to `0x01`. STOP and HALT do not force a UART idle level: firmware owns the pins.

### Host transactions

All host signals are synchronous to `clk`; there is no asynchronous handshake.
Each logical byte uses low nibble then high nibble at the same address/direction.
Sample both strobes low between beats. Holding a strobe high never repeats a
beat. Write side effects occur only at the second matching beat. The first read
beat captures one coherent byte and performs its read side effect; the second
beat returns that same byte's high half. Read data is valid after the accepted
edge plus clock-to-Q/combinational delay, and stable through held RD.

Idle gaps preserve phase indefinitely. An observed address or direction change
abandons phase. RD=WR=1 is reserved resynchronization: no core transaction or
host drive, phase discarded, then both strobes must be sampled low. It does not
stop the engine or change protocol pads. Reset/disable discard phase; an enabled
low-strobe edge is required to re-arm. Host drivers only drive uio[3:0], only for
exclusive enabled reads; idle/write/reset/disable/resync release them.

A byte requires at least four clocks including low gaps: 80 ns at 50 MHz.
A word is 16 clocks, or 20 including selector (400 ns). Extra polling and host
service add overhead. FIFO depth buffers bursts, not a sustained bandwidth deficit.

Instruction writes stage the low byte and commit on the high byte, incrementing
IMEM_ADDR modulo 32. Instruction writes/staging are ignored while running.

For a **32-bit data write**, select DATA_ADDR, write bytes in order to host registers
`6, 7, 9, A` (little endian). Writing A commits all four bytes atomically. The shared
staging bytes may be written while running; only FIFO/IRQ commits are then accepted.
Every writer must supply all four bytes; there is one staging buffer and no byte mask.

For a **32-bit data read**, select DATA_ADDR and read `6, 7, 9, A` in that order.
Reading 6 snapshots the entire selected word; the other three registers read that
snapshot even if the core changes state. When selecting RX, reading 6 also dequeues
one word at its first low-nibble beat. Abandoning that read does not undo the pop;
clients must complete normal reads. A held RD never dequeues twice. Reading an empty RX returns zero and sets
underflow. A new read of 6 replaces the snapshot. Separate words are separate
snapshots; STOP first for a coherent multi-register debug dump.

### Host byte-register map

Registers 0..E and data selectors 00..19 address the selected engine (reset 0).
See [the dual-PIO contract](dual_pio.md) for common selectors 1A..1E, banked
transaction state, GPIO ownership, and simultaneous group commands.

| Address | Name | Read / write |
| --- | --- | --- |
| `0` | CONTROL | Reads zero. W: bit0 START, bit1 STOP, bit2 FIFO_CLEAR, bit3 CLEAR_ERRORS, bit4 RESUME, bit5 ABORT_RELEASE; bits7:6 ignored |
| `1` | STATUS | R: bit0 running, bit1 delayed/stalled, bit2 fault, bit3 TX full, bit4 RX empty, bit5 any IRQ, bit6 TX overflow, bit7 RX underflow |
| `2` | IMEM_ADDR | R/W low five bits |
| `3` | IMEM_LO | R selected instruction low byte; W stage low byte while stopped |
| `4` | IMEM_HI | R selected instruction high byte; W commit/increment while stopped |
| `5` | DATA_ADDR | R/W 8-bit data-map selector |
| `6` | DATA_0 | R snapshot low byte (RX pop); W stage byte 0 |
| `7` | DATA_1 | R snapshot byte 1; W stage byte 1 |
| `8` | PC | R current five-bit program-memory address |
| `9` | DATA_2 | R snapshot byte 2; W stage byte 2 |
| `A` | DATA_3 | R snapshot byte 3; W commit 32-bit word |
| `B` | FIFO_LEVEL | R TX count[2:0], RX count[6:4], remaining bits zero |
| `C` | IRQ | R eight flags; W one-to-clear, including while running |
| `D` | DEBUG | R sticky bit0 TX overflow, bit1 RX underflow, bit2 nonblocking PUSH drop, bit3 empty nonblocking PULL fallback; W one-to-clear |
| `E` | INPUT | R synchronized protocol inputs [5:0], filtered where enabled |
| `F` | VERSION / SM_SELECT | R `0x21`; W 0/1 selects engine, other values ignored |

ABORT_RELEASE stops and clears all four protocol direction bits, with priority
over STOP/START/RESUME. It preserves values, dedicated outputs, configuration and
FIFOs (unless FIFO_CLEAR is also requested). START/RESUME never implicitly re-arm
directions. STOP wins over START/RESUME; START wins over RESUME. START clears X/Y/OSR/ISR,
shift counts (OSR=32/empty, ISR=0), delay/divider phase, pending EXEC/IRQ-wait and
fault. It preserves configuration, output levels, IRQ flags, FIFOs and sticky errors.
STOP preserves all execution state except running. RESUME only sets running and is
ignored during fault. It can start host-initialized register state at the current PC.
HALT holds its PC and clears running. RESUME after HALT executes HALT again.

FIFO_CLEAR clears both queues only when already stopped or combined with STOP or ABORT_RELEASE;
it does not clear OSR/ISR or counts. It is ignored while running, including a restart
of a running engine. CLEAR_ERRORS clears DEBUG; new errors on the same edge win.
Reset clears registers, queues, flags and host state, but not instruction memory.
Load every reachable instruction after power-up.

### 32-bit data map

All values are zero-extended to 32 bits where narrower. Unmapped reads are zero;
unmapped writes are ignored. Unless stated otherwise, writes require stopped state.

| Selector | Register | Behavior / reset |
| --- | --- | --- |
| `00`, `01` | X, Y | R/W 32-bit scratch; reset 0 |
| `02` | OSR | R/W; write also clears OUT count; reset 0 with count 32 |
| `03` | ISR | R/W; write also clears IN count; reset 0 |
| `04` | PINS | R/W programmed output levels[11:0]; reset 0xF01 |
| `05` | COUNTS | R OUT count[5:0], IN count[13:8]; saturate at 32 |
| `08` | TX | W enqueue 32-bit word, live while running; R0. Full write rejected with overflow unless same-edge CPU pop makes room |
| `09` | RX | R snapshot/pop at DATA_0; writes ignored |
| `10` | SHIFTCTRL | R/W described below; reset 3 |
| `11` | EXECCTRL | R/W described below; reset `0x03E0` |
| `12` | PINCTRL | R/W described below; reset 0 |
| `13` | DIVIDER | R/W low 16 bits; reset 1, zero clamps to1 |
| `14` | IRQ_SET | R IRQ flags; W low8 bits one-to-set, live while running |
| `15` | FIFO_LEVEL | R same packing as host B |
| `16` | ROUTE | R/W 28 bits, extended routing, reset 0 |
| `17` | DIRS | R/W [11:8]; [7:0] fixed output read FF, writes ignored; reset 0x0FF |
| `18` | OD | R/W [11:8] open drain, others ignored/read zero; reset 0 |
| `19` | FILTER | R/W [3:0] four-sample pad qualifier enables; reset 0 |

SHIFTCTRL: bit0 OUT right, bit1 IN right, bit2 autopull, bit3 autopush,
bits[8:4] pull threshold, bits[13:9] push threshold. A zero threshold means 32.
Both directions are independently configurable; reset uses right shifts.

EXECCTRL: bits[4:0] wrap bottom, bits[9:5] wrap top, bits[14:10] ENTRY,
bit15 optional single-bit side-set enable. Sequential retirement at wrap top jumps
to wrap bottom without a tick penalty. A taken branch overrides wrap. Otherwise
the five-bit PC increments modulo32. Configure a meaningful reachable wrap region.

PINCTRL: bits[2:0] OUT/MOV base, bits[6:3] OUT/MOV width; bits[10:8] SET base,
bits[14:11] SET width; bit16 IN base (0/1); bits[19:17] side-set pin;
bit20 JMP input pin (0/1). Other bits reserved. Width 0 or >8 means8. Mappings are
clipped at output 7, not rotated. IN reads the synchronized six-bit input vector
shifted right by IN base, zero extended. SET/OUT/MOV preserve unmapped outputs.
Side-set wins overlaps with instruction writes to the same state. PINCTRL
reserved bits7/15 and bits31:21 read zero and ignore writes.

ROUTE fields: bit0 extended mapping enable; [4:1] OUT/MOV base; [8:5] width;
[12:9] SET base; [16:13] width; [19:17] IN base; [23:20] side-set index;
[26:24] JMP input; bit27 side-set targets directions instead of values. Reset
zero uses old PINCTRL fields. Extended width 0 or >12 means12, clipping at index11;
base12..15 writes nothing. IN/JMP indices6..7 read zero; side-set12..15 is ignored.
Bits31:28 are ignored/read zero. All configuration writes require stopped state;
live FIFO/IRQ remains available. Other unmapped bits of defined registers read
zero and ignore writes unless explicitly specified.

DIRS reads programmed capability-masked direction, not electrical OE. Dedicated
outputs are always outputs. Only the four protocol pads support OD. Push-pull
uses data=value and OE=direction; open-drain uses data=0 and OE=direction AND NOT
value. Input readback always samples physical pads. Reset sets pad values one,
directions input/released, OD disabled, and immediately gates their OEs low.
Synchronous reset retains dedicated-output reset 0x01. STOP/HALT/fault/disable
retain pad state and can hold a bus low. Establish data before enabling a
push-pull driver; atomic logical writes do not establish analog glitch freedom.

### Instruction set

The current [PIO V0 ISA reference](isa.md) defines the 16-bit encoding, all eight
opcode groups, operands, shifts, delays, side-set, EXEC, HALT, reserved encodings,
and assembler syntax. Host VERSION is `0x21`; use only programs for this revision.

### Load and run UART

1. Reset with RD=WR=0, `ena=1`, and a running clock.
2. Select data `0x13`, write bytes `1F 00 00 00` to host `6,7,9,A` (divider31).
3. Select data `0x12`, write `08 10 00 00` (OUT pin0, SET pins[1:0]).
4. Select data `0x08`, write `55 00 00 00` to queue ASCII U.
5. Set IMEM_ADDR=0; load these words low byte then high byte:
   `80A0 E027 ED00 6C01 0043 ED01 E003 C080`.
6. Write CONTROL=1. Firmware emits start, eight LSB-first data bits, stop, and
   completion on output 1. Each bit occupies 14 ticks ×31 clocks  = 434 clocks.
7. Poll running clear. For replay queue another byte and START again. To abort,
   STOP; to also return UART idle, write PINS=1 while stopped, or reset.

Use `python tools/pioasm.py examples/uart_v0.asm` to regenerate the hex file.
The assembler supports labels, decimal/hex values, `[delay]`, `.sideset` and
`side 0/1`. Configure the corresponding host registers separately; the assembler
does not apply DIVIDER, pin mapping, entry or wrap settings automatically.

## How to test

The [SPI mode-0 guide](spi_mode0.md) describes a full-duplex eight-bit program,
host configuration, synchronized input timing and its pin-level slave test.

Run `python test/run.py` or `./test/run.ps1`. The FIFO unit test exhausts occupancy
and simultaneous read/write boundaries. Pin-level tests cover state, timing, UART TX/RX, SPI, general pads, host
framing, and I2C transfers/recovery; see the [verification matrix](pio21_verification.md). See [test/README.md](../test/README.md)
and [project status](project_status.md) for current validation scope. The optimization
report and single-engine matrix are historical records.

## External hardware

Use a synchronous host and compatible logic levels. A logic analyzer can observe
all programmable outputs; a UART adapter receives the example at 115200 8N1 with
a 50 MHz core clock. Input0 (`ui[6]`) can receive the RX example at 16 clocks/bit.
The fixed Arty UART demo uses a transmit-only USB connection. The separate
[programmable bring-up top](../tools/bringup/README.md) uses USB UART for host
commands and exposes protocol pins independently. Its I2C pads are on JC1/2;
the older reusable I2C wrapper's JA fragment is a different integration. None of
these instructions establishes board interoperability without running the tests.
Ethernet/USB require separate architectures and are outside this implementation.
