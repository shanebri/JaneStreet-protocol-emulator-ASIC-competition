# Arty A7-100T hardware demo

This FPGA-only wrapper instantiates the unchanged JaneStreet Tiny Tapeout design.
It generates 50 MHz from the board's 100 MHz clock using an MMCM and loads all 32
instruction words through the real synchronous host interface. The first eight words
match `examples/uart_v0.hex`; the remaining words are HALT. The loader also writes
DIVIDER=31, PINCTRL=0x1008 and queues `0x55` in the TX FIFO. The state machine
generates the entire UART frame in firmware. No external host wiring,
Clocking Wizard IP generation, or separate USB-UART adapter is needed.

## Create the Vivado project

Close the current Vivado project, then run this in its Tcl console (adjust the path
if the repository moves):

```tcl
source C:/Users/shane/Projects/JaneStreet-protocol-emulator-ASIC-competition/fpga/create_project.tcl
```

The script creates `fpga/build/janestreet_arty/janestreet_arty.xpr`, targeting
`xc7a100tcsg324-1`, with `arty_a7_top` selected as the top module. It does not overwrite
an existing project. Open the generated project directly on later visits.

Alternatively, add `arty_a7_top.sv` and `arty_demo.sv` alongside all eight existing
RTL files to your existing project, set `arty_a7_top` as top, and add
`arty_a7_100t.xdc`. Disable/remove `constraints/janestreet.xdc` from that FPGA
project's active constraints set: it describes the bare core's `clk` input, while
this wrapper exposes `clk100` and generates 50 MHz internally. Keep the original
file for standalone core timing analysis.

When updating an older project, remove `uart_tx.sv` and add `pio_fifo.sv`.
The batch build script performs this source-list migration automatically.

For a command-line build, run from the repository root in a Vivado-enabled shell:

```text
vivado -mode batch -source fpga/build_bitstream.tcl
```

This opens or creates the isolated project, resets its synthesis run, and builds
through bitstream generation. Reports are saved under `fpga/build/`. The output is
`fpga/build/janestreet_arty/janestreet_arty.runs/impl_1/arty_a7_top.bit`.

Run Synthesis, Implementation, and Generate Bitstream. Check that timing is met
and no NSTD-1/UCIO-1 violations remain. `report_clocks` should show the 10 ns input
clock and a 20 ns MMCM output clock. The MMCM and BUFGs are built-in Xilinx
primitives; Vivado derives the generated clock automatically.

## Program and test

For a desktop Python monitor with COM-port selection, hex/text output, and an
expected-byte counter, see the [UART client guide](../tools/UART_CLIENT.md).

1. Connect a USB data cable to the Arty's PROG/UART connector and power the board.
2. In Hardware Manager, Open Target -> Auto Connect -> Program Device. Select the
   generated `arty_a7_top.bit` in the project's implementation run directory.
3. Open the board's USB serial COM port at **115200 baud, 8N1, no flow control**.
4. Wait for LD4 (ready) and LD7 (clock locked). LD6 blinks with a roughly 2.68 s
   full period. The core does not transmit automatically at power-up.
5. Press **BTN1** for at least 10 ms. The wrapper resets the core, reloads the
   program, and starts it. The serial terminal receives **U**, then **LD5** lights.
   Each UART bit lasts 434 clocks, or 8.68 microseconds.
6. Release BTN1 for at least 10 ms, then press again to replay. Holding it does not
   repeat. Press **BTN0** to abort/reset and reload without starting execution.

| Board signal | FPGA pin | Function |
| --- | --- | --- |
| 100 MHz oscillator | E3 | MMCM input |
| BTN0 | D9 | Reset/reload, active high |
| BTN1 | C9 | Debounced run/replay, active high |
| USB-UART bridge receive input | D10 | FPGA UART TX to PC |
| LD4 | H5 | Loader ready; also high during program execution |
| LD5 | J5 | Program's PIO_OUT[1] completion flag |
| LD6 | T9 | 50 MHz domain heartbeat |
| LD7 | T10 | MMCM locked |

Pin assignments follow the [Digilent Arty A7-100 Rev D/E master XDC](https://github.com/Digilent/digilent-xdc/blob/master/Arty-A7-100-Master.xdc).
All exposed ports use LVCMOS33. Both button inputs are synchronized. Loss of MMCM
lock asserts the clock reset asynchronously; its release is synchronized. Timing exceptions
cover only the asynchronous button boundaries and indicator/UART outputs, not
internal core paths.

This is a fixed demonstration loader, not a serial command interface. Typing in
the terminal does not load programs. A future UART-to-host bridge can provide that.
Loading the FPGA over JTAG is volatile; reprogram after power cycling.

## Simulation

### Standalone USB-UART diagnostic

If LD5 lights in the normal demo but the PC receives no bytes, use the separate
`arty_uart_diagnostic` image to test the USB path without the PIO engine. Build
it in a separate Vivado batch process from the repository root:

```powershell
vivado -mode batch -source fpga/build_uart_diagnostic.tcl
```

Program `fpga/build/uart_diagnostic/arty_uart_diagnostic.bit` through Hardware
Manager. This temporarily replaces the running demo; program the normal demo
bitstream again afterward. The diagnostic automatically sends `U` (`55`) about
twice per second at 115200 8N1 on D10. No button press is needed. LD5 toggles after
each frame, LD6 blinks, LD7 stays on (an image indicator, not MMCM lock in this
diagnostic), and LD4 follows BTN1. Holding BTN0 resets/pauses transmission.

Connect the Python client before or after programming. If repeated `55` bytes
arrive, investigate the PIO demo implementation. If RX stays at zero with LD5
toggling, investigate the USB serial path, driver, board connection, or physical
output. This image uses the board's 100 MHz clock directly and has a simulation
testbench in `tb_arty_uart_diagnostic.sv` checking three complete UART frames.

### PIO demo simulation

```powershell
./fpga/test.ps1
```

Uses local `.tools` Icarus binaries when present, otherwise Icarus on PATH. Tests
the loader/core at 50 MHz against the canonical example, UART bit timing, short
button bounces, held buttons, replay, and reset during transmission. This simulation
does not model the Xilinx MMCM or physical pins; validate those in Vivado and on
the board. No Tiny Tapeout submission sources or manifest entries are changed.
