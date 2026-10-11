# Programmable Protocol Emulator — V0

An early end-to-end 16-bit protocol emulator for the Jane Street ASIC competition,
targeting **8×4 Tiny Tapeout tiles on IHP CMOS5L**. The prototype prioritizes a
small, testable path from a host-loaded program to real output waveforms.

The V0 slice implements:

- 32 × 16-bit writable instruction memory and a 5-bit word-addressed PC.
- A decoder, 16-bit accumulator, load/store, immediate ALU operations and branches.
- Eight 16-bit scratch registers and a mapped GPIO/UART register bank.
- Seven GPIO outputs, a cycle-counted WAIT instruction and a UART completion wait.
- An 8-bit synchronous parallel host bus for loading, starting, stopping and inspecting programs.
- A TX-only UART that sends 8N1 frames with a programmable 16-bit clocks-per-bit divider.

## Try the end-to-end example

The [UART program](examples/uart_v0.asm) and its [loadable words](examples/uart_v0.hex)
configure 434 clocks per bit, move ASCII `U` through scratch memory, transmit it on
`uo[0]`, raise `uo[1]` when the frame completes, wait 16 clocks and halt. With a
50 MHz clock this is approximately 115200 baud.

The [datasheet](docs/info.md) describes each host transaction, the instruction set,
the complete address/register maps and reset/timing behavior. Program memory must
be loaded after power-up; there is no automatic boot program.

## Run the tests

Install Icarus Verilog and Python 3.11 or newer, then from the repository root:

```sh
python -m pip install -r test/requirements.txt
python test/run.py
```

Alternatively, use `make -C test` or `./test/run.ps1` on Windows. These run the same ten pin-level cocotb tests and
produce `test/results.xml` and `test/tb.fst`. See the [test guide](test/README.md)
for waveform viewing, a single-demo run and gate-level simulation.

The regression exercises host read/write timing, complete program upload and
readback, arithmetic and branches, exact waits, UART frames and busy handling,
reset/abort, protection of running code and PC wraparound.

## Arty A7-100T board test

The [FPGA demo guide](fpga/README.md) provides a board wrapper, pin constraints,
Vivado project script, and button-triggered UART test using the onboard USB serial
connection. The ASIC core stays unchanged.

## Scope and area

`info.yaml` declares the updated **8x4** allocation and all eight RTL source files.
The data and instruction widths are 16 bits; narrow addresses and small memories
keep this first prototype bounded. Instruction storage is inferred RTL memory
and can map to flip-flops, not an ASIC SRAM macro.

This is an integration prototype. UART RX, FIFOs, interrupts, arbitrary protocol
timing and a general-purpose host software stack are future work. Generic
synthesis is a structural check; fitting 8×4 tiles and meeting the 50 MHz target
still require the CMOS5L place-and-route, timing and gate-level flows. The existing
GDS workflow is configured to run those flows.

## Origin and licensing

The project started from [TinyTapeout/ttihp-verilog-template, branch cmos5l](https://github.com/TinyTapeout/ttihp-verilog-template/tree/b86a2a781484bcab7ba522dc5de540086695a430),
upstream commit `b86a2a781484bcab7ba522dc5de540086695a430`.
The repository's original MIT license is retained in [LICENSE](LICENSE).
Imported Tiny Tapeout files retain their Apache-2.0 license in
[LICENSE-TinyTapeout](LICENSE-TinyTapeout) and their original notices.
