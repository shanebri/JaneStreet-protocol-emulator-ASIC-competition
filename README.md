# Programmable Protocol Emulator — dual PIO revision 0x21

A PIO-inspired protocol engine for the Jane Street ASIC competition, targeting
**8×4 Tiny Tapeout tiles on IHP CMOS5L**. Protocol timing and framing are firmware.
The old accumulator and dedicated UART transmitter have been replaced.

- Two independent state machines, each with 32 words of 16-bit writable
  instruction memory, programmable entry point and zero-overhead wrap.
- 32-bit OSR, ISR, X and Y; shifts of 1–32 bits in either direction.
- Per-engine independent four-word, 32-bit TX/RX FIFOs with blocking/nonblocking operations,
  automatic pull/push, atomic host access and visible error flags.
- JMP, WAIT, IN, OUT, PUSH/PULL, MOV, SET, IRQ, EXEC, delay and optional side-set.
- Eight dedicated outputs, four general bidirectional pads, six synchronized inputs,
  per-pad open drain and optional input qualification.
- One instruction per clock at divider 1, including taken branches and shifts.
  Delays, input/IRQ waits and FIFO backpressure are explicit exceptions.
- Synchronous four-bit host transport with byte registers, plus a small label-aware Python assembler.

This is a **breaking ISA/host-map update** (revision register `0xF` reads `0x21`).
Old accumulator firmware must be replaced. It is PIO-inspired, not a binary
compatible RP2040 implementation. The host transport is low-nibble-first; existing PIO UART/SPI binaries retain
their meaning. The [dual-PIO extension](docs/dual_pio.md) adds engine selection, exclusive GPIO
ownership and group control while retaining VERSION=0x21. FIFO joining, fractional
clock division and external DMA are not implemented.

## Run the firmware UART demo

Load [uart_v0.hex](examples/uart_v0.hex), configure `DIVIDER=31`,
`PINCTRL=0x1008` and `SHIFTCTRL=3`, enqueue `0x55` in the TX FIFO, and issue START. The
[eight-instruction program](examples/uart_v0.asm) drives an 8N1 `U` frame on
`uo[0]`, raises `uo[1]` after the stop bit, and halts. Each bit lasts exactly
434 clocks: approximately 115200 baud at 50 MHz. Replay requires enqueuing another
byte. There is no UART peripheral or UART divider register in the RTL.

[uart_rx.asm](examples/uart_rx.asm) demonstrates firmware receive on `ui[6]`
at 16 clocks/bit, delivering the byte in bits [31:24] of an RX FIFO word.
It is a minimal receive example without framing-error/break handling.

The [datasheet](docs/info.md) defines timing, logical pin assignments and every
host transaction. The [ISA reference](docs/isa.md) defines the current instructions
and assembler syntax. The [historical optimization report](docs/pio_v0_optimization_report.md)
records the original revision-0x20 work; use [project status](docs/project_status.md)
for current results and next qualification steps.

## SPI mode-0 firmware

[spi_mode0.asm](examples/spi_mode0.asm) performs one eight-bit, MSB-first,
full-duplex SPI transfer using the existing ISA. OUT drives MOSI, side-set drives
SCLK, and IN samples synchronized MISO; SET controls active-low chip select.
The [SPI guide](docs/spi_mode0.md) defines configuration, byte packing, pin
mapping, clock timing and the cocotb slave model. The FPGA SPI host is also migrated to the reusable nibble adapter; see its
[hardware test guide](tools/spi_hardware/README.md).

## I2C firmware

The [I2C guide](docs/i2c.md) covers a 24-word controller program, Python transaction
driver, repeated START, ACK/NACK status, stretching and bounded bus recovery.
Nominal 100/400 kHz configurations target 50 MHz. Host and protocol pads operate
concurrently. See the [architecture contract](docs/pio21_contract.md),
[decision record](docs/adr_four_bit_host.md), and [verification matrix](docs/pio21_verification.md).

## Build and test

The [repeatable bring-up suite](tools/bringup/README.md) provides Python-driven
host-interface smoke tests, an FPGA serial bridge, saved run bundles and optional
UART/SPI/I2C peer profiles. The bridge is simulation-tested; board implementation
and physical peer qualification remain required.

```sh
python tools/pioasm.py examples/uart_v0.asm
python -m pip install -r test/requirements.txt
python test/run.py
```

Icarus Verilog must be on PATH. On Windows, `./test/run.ps1` also finds the optional
project-local tools. The runner checks FIFO boundaries, exhaustive adapter/pad unit cases and pin-level
core/ISA/I2C regressions. See [test/README.md](test/README.md) for synthesis and gate-level
checks. The [Arty A7 guide](fpga/README.md) covers the updated FPGA loader and
button-triggered firmware UART demo; `./fpga/test.ps1` verifies its behavior.

## Qualified implementation and current work

The 50 MHz dual-engine ASIC baseline at `bb7c5ef` passes extracted three-corner
timing/electrical checks, routing/Magic DRC, antenna, LVS, Tiny Tapeout precheck
and all **39 functional gate-level tests** in
[Actions run 40938542430](https://github.com/shanebri/JaneStreet-protocol-emulator-ASIC-competition/actions/runs/40938542430).
Core utilization excluding filler is **31.52%**. Worst overall setup margin is
**0.303 ns**; worst hold margin is **0.0128 ns**, so implementation changes still
require full requalification. KLayout DRC was disabled in this flow.

See [project status](docs/project_status.md) for exact evidence, physical-check
scope and timing margins; the [coverage audit](docs/timing_coverage_audit_20261029.md)
explains the misleading native register-setup `Infinity` metric. The
[documentation guide](docs/README.md) separates current contracts and commands
from historical experiments and architecture proposals.

The repeatable bring-up tooling is simulation-tested. Vivado implementation of
the new bridge and physical UART/SPI/I2C peer tests remain outstanding. Its smoke
tests provide repeatable board access to behavior already covered more deeply by
simulation; they do not establish ASIC timing or hardware interoperability.

## Origin and licensing

The project started from
[TinyTapeout/ttihp-verilog-template, branch cmos5l](https://github.com/TinyTapeout/ttihp-verilog-template/tree/b86a2a781484bcab7ba522dc5de540086695a430).
The original MIT license remains in [LICENSE](LICENSE); imported Tiny Tapeout files
retain their Apache-2.0 license in [LICENSE-TinyTapeout](LICENSE-TinyTapeout).
