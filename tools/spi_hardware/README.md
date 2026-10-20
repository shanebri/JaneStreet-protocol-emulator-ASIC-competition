# Arty PIO SPI master + Arduino Nano 33 BLE test

This setup uses the **Arty A7-100T FPGA, Nano 33 BLE, and your PC**. No Raspberry
Pi is involved. The FPGA runs the existing `examples/spi_mode0.asm` on the
unchanged ASIC core; the Nano uses its nRF52840 hardware SPI slave peripheral.
USB serial is only the control/report channel to the PC.

One BTN1 press performs 256 separate one-byte transactions. FPGA MOSI sends
`00, 01, ... FF`. For transaction `n`, the Nano sends `n XOR A5` on MISO. It
preloads that reply **before CS falls**: SPI is simultaneous, so this is not an
attempt to echo a byte that has not yet arrived. Both endpoints independently
check the received byte. The extra READY signal prevents a transfer while the
Nano is preparing its next buffer.

## 1. Wire the boards

Disconnect power while wiring. Use short wires, preferably 10–15 cm or less for
initial tests. Both signal interfaces are **3.3 V**. Power each board through its
own USB connector; connect grounds, but **do not connect their 5 V, VIN or 3.3 V
power pins together**. This sketch is for the Nano 33 BLE, not a classic 5 V Nano.

| Signal | Direction | Arty connector | FPGA package pin | Nano header |
| --- | --- | --- | --- | --- |
| MOSI | FPGA -> Nano | JA1 | G13 | D11 / MOSI |
| SCLK | FPGA -> Nano | JA2 | B11 | D13 / SCK |
| CS_n | FPGA -> Nano | JA3 | A11 | D10 |
| MISO | Nano -> FPGA | JA4 | D12 | D12 / MISO |
| READY | Nano -> FPGA | JA7 | D13 | D2 |
| Ground | Shared | JA5 or JA11 (GND) | — | GND |

JA1–JA6 are one row and JA7–JA12 the other; identify **pin 1 from the board's
marking**, not by assuming a viewing orientation. JA6 and JA12 are power: leave
them unconnected. The Nano's D13 LED can flicker with SCLK; it is not a PASS LED.

Pin mappings were checked against [Digilent's Arty A7-100 master
XDC](https://github.com/Digilent/digilent-xdc/blob/master/Arty-A7-100-Master.xdc)
and [Arduino's Nano 33 BLE
variant](https://github.com/arduino/ArduinoCore-mbed/blob/main/variants/ARDUINO_NANO33BLE/variant.cpp).
The Nano maps D10=P1.02, D11=P1.01, D12=P1.08 and D13=P0.13. The sketch configures
SPIS2 directly; the normal Arduino SPI master library is not used.

## 2. Load the Nano sketch

In Arduino IDE, install **Arduino Mbed OS Nano Boards**, select **Arduino Nano
33 BLE**, and open [nano_spi_slave.ino](nano_spi_slave/nano_spi_slave.ino). Upload
to the Nano's USB port. This sketch was compile-checked with board package 4.6.0
and FQBN `arduino:mbed_nano:nano33ble`.

No extra Arduino library is required. Do not add `SPI.begin()` or BLE/sensor
libraries to this test sketch; it owns the SPIS2 peripheral. It does not block
waiting for a Serial Monitor and stays unarmed until the PC sends `ARM`.

Close Arduino Serial Monitor before using the PC checker. Only one application
can own a COM port at a time. The Nano's upload/bootloader COM number can differ
from its running-sketch COM number; rediscover it after uploading if necessary.

## 3. Build the FPGA test image manually in Vivado

Use a separate project for `xc7a100tcsg324-1`, or copy these sources into your
existing project and select the new top. **No Vivado project has been edited or
build launched by these tools.**

Add all ASIC design sources listed in info.yaml:

```text
src/project.sv
src/host_interface.sv
src/pio_pads.sv
src/protocol_core.sv
src/pio_fifo.sv
src/execution_unit.sv
src/frontend/pc.sv
src/frontend/instruction_fetch.sv
src/frontend/decoder.sv
```

Add these four FPGA-only sources:

```text
fpga/arty_spi_test_top.sv
fpga/arty_spi_test_host.sv
fpga/byte_nibble_host.sv
fpga/spi_test_uart_tx.sv
```

Set top to **arty_spi_test_top**. Enable **only**
`fpga/arty_spi_test.xdc` for this build; disable the UART demo constraints,
UART diagnostic constraints and `constraints/janestreet.xdc`. Do not add the SPI
testbench as a synthesis source. There is no additional IP to generate: the top
uses the same MMCM/BUFG primitives as the UART top to make a 50 MHz core clock.

Run synthesis, implementation and bitstream generation yourself. Check timing,
DRC and that the top/pin report matches the wiring table. The output exceptions
describe externally observed slow SPI/debug signals; they do not establish timing
at the Nano pins. Program the newly generated **arty_spi_test_top.bit** through
Hardware Manager. The previous UART images cannot run this test.

The host ROM contains the ten canonical SPI instruction words and HALT padding;
there is no runtime `.hex` path dependency when copying the HDL into Vivado.
The simulation compares that ROM against `examples/spi_mode0.hex`.

## 4. Run the PC checker

Connect the Arty PROG/UART USB port and the Nano USB port to the PC. From the
repository root in PowerShell:

```powershell
py -m pip install -r tools/spi_hardware/requirements.txt
py tools/spi_hardware/check_spi.py --list
py tools/spi_hardware/check_spi.py --fpga-port COM3 --nano-port COM5
```

Substitute the actual COM numbers. Use `python` if that is your Python command.
For a portable copy, keep `check_spi.py` and `requirements.txt` together and run
them from their directory. Both serial links use 115200 in the PC software.

The checker first identifies the Nano. It then prompts you to press and release
**FPGA BTN0**, wait for **LD4 and LD7**, and press Enter on the PC. It arms the
Nano and tells you to press **FPGA BTN1 once**. Let the roughly two-second batch
finish. Do not reset either board midway. The default overall timeout is 90
seconds, including time to press BTN1.

Expected final output:

```text
PASS: all 256 byte values checked in both directions. FPGA LD5 should be on, LD6 off.
```

To save decoded reports, add `--log spi-results.jsonl`. This overwrites the named
log. Exit code 0 means both 256-record streams and the Nano's successful DONE
were received; a missing stream, corrupted UART report, wrong byte, duplicate or
out-of-order record, nonzero result code or timeout exits with code 1.

| FPGA LED | Meaning in this SPI test image |
| --- | --- |
| LD4 | Loader ready, waiting for BTN1; turns off during/after a batch |
| LD5 | Entire batch completed with every FPGA MISO comparison passing |
| LD6 | Sticky MISO mismatch, core fault, or timeout; this is NOT a heartbeat |
| LD7 | MMCM locked |

LD5 alone verifies the FPGA side. The PC checker also requires the Nano's MOSI
results. Restart the checker and follow its BTN0 prompt for every new batch;
resetting only one endpoint loses sequence alignment.

## Timing and reporting details

The default `SPI_DIVIDER=32` in `arty_spi_test_host.sv` gives SCLK **97.65625 kHz**
at 50 MHz, mode 0, MSB-first, eight bits per CS assertion. READY remains low for at
least 5 ms between bytes. After the initial test works, changing SPI_DIVIDER and
rebuilding is how to test other rates; the Nano remains a clocked slave. Start
slow and validate wiring/timing before increasing it. The SPI firmware samples
the already-synchronized MISO value, as described in [the SPI
guide](../../docs/spi_mode0.md).

Arty UART reports are binary, not ASCII U frames. Each seven-byte packet is
`A5 5A sequence transmitted received status checksum`; checksum is the XOR of the
preceding six bytes. Status 0=pass, 1=MISO mismatch, 2=PIO fault/missing RX,
3=PIO execution timeout, 4=READY handshake timeout. Ordinary mismatches are
reported and the batch continues; fatal errors stop the batch. A handshake error
after a reported byte can produce a second report for that sequence with status 4.

The Nano emits decimal text records `RX sequence received sent count pass`, then
`DONE 256 failures`. EasyDMA counts complete received bytes; its two-byte buffer
detects extra whole bytes, not every possible partial-bit glitch. Exact clock
edges are verified in simulation. A logic analyzer or oscilloscope is needed to
measure physical setup/hold, voltage quality or malformed partial clocks.

The UART serializer in the FPGA wrapper only reports results to the PC. The SPI
clock, data and sampling all come from the PIO assembly running on the ASIC core.

## Troubleshooting

- **Nano does not answer PING:** wrong COM port, wrong sketch, or another serial
  monitor owns the port. Confirm Nano 33 BLE board selection and upload success.
- **LD7 off:** check the FPGA clock, power, selected device and bitstream.
- **LD4 never lights:** verify all eight current ASIC sources and the new test
  top/host are included, then rebuild the correct top.
- **READY timeout/status 4:** check JA7 to Nano D2, shared ground, successful ARM,
  and that both endpoints started from sequence zero.
- **Nano MOSI error:** check MOSI/CS/SCLK wiring, mode 0 and board pin orientation.
- **FPGA MISO error/status 1:** check Nano D12 to JA4, ground, and the bitstream's
  pin report. Replies must equal sequence XOR A5; bytes `EE` can indicate an
  unprepared/overrun slave transaction.
- **Only one endpoint reports:** confirm both USB cables/ports. The Arty COM port
  carries binary reports; the Nano port carries text. Do not use the old UART
  monitor for automated SPI verdicts.

## Local validation (no hardware programming)

```powershell
./fpga/test_spi.ps1
py -m unittest discover -s tools/spi_hardware -p test_checker.py -v
```

The FPGA harness simulation runs 512 SPI transactions through the real PIO core
and host interface, decodes every UART report, injects a bad MISO reply and tests
a missing READY timeout. It also checks a READY-low pulse that ends before the
UART report finishes. The existing cocotb suite checks detailed SPI edge timing.
The five checker tests exercise split serial frames, corruption, sequence/data
errors and the requirement that both endpoints complete. The Nano sketch is
compile-checked; physical FPGA/Nano interoperability remains to be tested on
your hardware. No synthesis, implementation, bitstream or upload was performed.

Host revision 0x21 transfers each byte low nibble then high nibble on uio[3:0].
See [the transport contract](../../docs/pio21_contract.md) for framing, reset and resynchronization.
