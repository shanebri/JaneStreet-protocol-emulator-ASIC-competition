# PIO V0 verification

Install Python 3.11+, Icarus Verilog and `test/requirements.txt`, then run:

```sh
python test/run.py
```

On Windows, `./test/run.ps1` locates optional `.tools` binaries. The portable runner
uses the submission source list in `info.yaml`. It first runs `pio_fifo_tb.sv`,
then exhaustive host/pad unit tests and the pin-only core, PIO21 and I2C suite. `make -C test` runs the same cocotb suite; the
standalone FIFO/host/pad units are included by the Python runner only.

Coverage includes all shift widths 1–32 in both directions, count saturation,
scratch comparisons/decrement loops, MOV/OUT EXEC and PC writes, atomic 32-bit
host access, input synchronization/WAIT, IRQ handshakes, FIFO order/overflow/
underflow, simultaneous full/empty traffic, wraparound, conditional and nonblocking
transfers, automatic transfers at thresholds 8 and 32, exact delay/divider timing,
side-set during stalls, zero-cost program wrap, enable/stop/resume, reset, write
protection, and invalid instructions. FIFO scoreboard tests exercise 1,000 further
deterministic traffic combinations after exhaustively checking boundary states.

TX tests compare every clock of start/data/stop for bytes 55/00/FF/A6 at dividers
1,2,31. The checked-in example is assembled and compared with its hex file, loaded
and read back through host pins, then checked at exactly 434 clocks per bit with
the completion marker after the full stop bit. RX firmware is driven with the
same four byte patterns at 16 clocks per bit and checked through the RX FIFO.

The [SPI mode-0 test](../docs/spi_mode0.md#verification) checks 42 full-duplex
eight-bit transfers across three dividers and two logical pin layouts. It models
a slave with delayed MISO updates after falling edges and checks exactly eight
clock pulses, MSB-first MOSI, synchronized MISO results, clock/CS timing, safe
waiting on empty TX, and preservation of unrelated output pins.

```powershell
$env:COCOTB_TEST_FILTER = 'firmware_uart_full_waveforms_and_example$'
./test/run.ps1
Remove-Item Env:COCOTB_TEST_FILTER
```

To run only SPI, use `firmware_spi_mode0_byte_transfer$` as the test filter.

Results are `test/results.xml` and `test/tb.fst`. Open the latter with GTKWave or
Surfer; `test/tb.gtkw` includes PC, shifters, scratch state and queue levels. Tests
do not depend on internal RTL names, so the cocotb suite can also run against a
hardened `tt_um_shanebri_top` netlist:

```sh
make -C test -B GATES=yes
```

That requires `test/gate_level_netlist.v` and the CMOS5L PDK at `PDK_ROOT`.
No hardened netlist was produced as part of this update. RTL behavior does not
prove setup/hold closure or clock-domain-crossing reliability.

Generic synthesis/structural check:

```sh
yosys -p 'read_verilog -sv src/project.sv src/protocol_core.sv src/host_interface.sv src/pio_pads.sv src/execution_unit.sv src/pio_fifo.sv src/frontend/pc.sv src/frontend/decoder.sv src/frontend/instruction_fetch.sv; synth -noabc -top tt_um_shanebri_top; check -assert; stat'
```

Use `./fpga/test.ps1` for the Arty loader/debounce/replay/reset simulation. Run the
Vivado implementation and ASIC physical flows separately to establish timing and
area. The optimization report records the generic synthesis comparison.

Host revision 0x21 transfers each byte low nibble then high nibble on uio[3:0].
See [the transport contract](../docs/pio21_contract.md) for framing, reset and resynchronization.

For baseline/final comparable generic synthesis from the actual manifest:

```sh
python test/synth.py --revision HEAD --name baseline
python test/synth.py
```

Use `--yosys path/to/yowasp-yosys.exe` on Windows where appropriate. Both runs use
`synth -noabc`, `check -assert`, and a no-latches assertion. Reports are below
`test/sim_build/synth_*`. This is not a CMOS5L area/timing estimate.

Run `./fpga/test_spi.ps1` and `./fpga/test_i2c.ps1` for the migrated SPI and I2C
wrappers. [The matrix](../docs/pio21_verification.md) records requirement coverage
and physical checks that remain unavailable.
