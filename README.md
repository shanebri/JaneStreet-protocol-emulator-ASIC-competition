# Programmable Protocol Emulator — PIO V0

A PIO-inspired protocol engine for the Jane Street ASIC competition, targeting
**8×4 Tiny Tapeout tiles on IHP CMOS5L**. Protocol timing and framing are firmware.
The old accumulator and dedicated UART transmitter have been replaced.

- One state machine, 32 × 16-bit writable instruction memory, programmable entry
  point and zero-overhead wrap.
- 32-bit OSR, ISR, X and Y; shifts of 1–32 bits in either direction.
- Independent four-word, 32-bit TX/RX FIFOs with blocking/nonblocking operations,
  automatic pull/push, atomic host access and visible error flags.
- JMP, WAIT, IN, OUT, PUSH/PULL, MOV, SET, IRQ, EXEC, delay and optional side-set.
- Eight programmable outputs and two synchronized inputs.
- One instruction per clock at divider 1, including taken branches and shifts.
  Delays, input/IRQ waits and FIFO backpressure are explicit exceptions.
- Synchronous 8-bit host bus, plus a small label-aware Python assembler.

This is a **breaking ISA/host-map update** (revision register `0xF` reads `0x20`).
Old accumulator firmware must be replaced. It is PIO-inspired, not a binary
compatible RP2040 implementation. The current package has fixed-direction protocol
pins; pin-direction instructions, multiple state machines, FIFO joining, fractional
clock division, and external DMA are not implemented.

## Run the firmware UART demo

Load [uart_v0.hex](examples/uart_v0.hex), configure `DIVIDER=31` and
`PINCTRL=0x1008`, enqueue `0x55` in the TX FIFO, and issue START. The
[eight-instruction program](examples/uart_v0.asm) drives an 8N1 `U` frame on
`uo[0]`, raises `uo[1]` after the stop bit, and halts. Each bit lasts exactly
434 clocks: approximately 115200 baud at 50 MHz. Replay requires enqueuing another
byte. There is no UART peripheral or UART divider register in the RTL.

[uart_rx.asm](examples/uart_rx.asm) demonstrates firmware receive on `ui[6]`
at 16 clocks/bit, delivering the byte in bits [31:24] of an RX FIFO word.
It is a minimal receive example without framing-error/break handling.

The [datasheet](docs/info.md) defines encoding, timing, pin assignments and every
host transaction. The [optimization report](docs/pio_v0_optimization_report.md)
records validation results and priorities for the next version.

## Build and test

```sh
python tools/pioasm.py examples/uart_v0.asm
python -m pip install -r test/requirements.txt
python test/run.py
```

Icarus Verilog must be on PATH. On Windows, `./test/run.ps1` also finds the optional
project-local tools. The runner checks FIFO boundary cases and eleven pin-level
cocotb regressions. See [test/README.md](test/README.md) for synthesis and gate-level
checks. The [Arty A7 guide](fpga/README.md) covers the updated FPGA loader and
button-triggered firmware UART demo; `./fpga/test.ps1` verifies its behavior.

The 50 MHz clock and 8×4 tile allocation remain targets. Generic synthesis passes;
CMOS5L place-and-route, timing closure and physical gate-level validation remain
necessary before claiming fit or Ethernet/USB capability.

## Origin and licensing

The project started from
[TinyTapeout/ttihp-verilog-template, branch cmos5l](https://github.com/TinyTapeout/ttihp-verilog-template/tree/b86a2a781484bcab7ba522dc5de540086695a430).
The original MIT license remains in [LICENSE](LICENSE); imported Tiny Tapeout files
retain their Apache-2.0 license in [LICENSE-TinyTapeout](LICENSE-TinyTapeout).
