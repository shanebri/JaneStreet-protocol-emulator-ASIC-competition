# PIO V0 verification

Install Python 3.11+, Icarus Verilog and `test/requirements.txt`, then run:

```sh
python test/run.py
```

On Windows, `./test/run.ps1` locates optional `.tools` binaries. The portable runner
uses the submission source list in `info.yaml`. It first runs `pio_fifo_tb.sv`,
then eleven pin-only cocotb tests. `make -C test` runs the same cocotb suite; the
standalone FIFO unit is included by the Python runner only.

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

```powershell
$env:COCOTB_TEST_FILTER = 'firmware_uart_full_waveforms_and_example$'
./test/run.ps1
Remove-Item Env:COCOTB_TEST_FILTER
```

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
yosys -p 'read_verilog -sv src/project.sv src/protocol_core.sv src/host_interface.sv src/execution_unit.sv src/pio_fifo.sv src/frontend/pc.sv src/frontend/decoder.sv src/frontend/instruction_fetch.sv; synth -noabc -top tt_um_shanebri_top; check -assert; stat'
```

Use `./fpga/test.ps1` for the Arty loader/debounce/replay/reset simulation. Run the
Vivado implementation and ASIC physical flows separately to establish timing and
area. The optimization report records the generic synthesis comparison.
