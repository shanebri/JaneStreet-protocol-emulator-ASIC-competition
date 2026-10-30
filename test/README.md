# PIO V0 verification

Timing investigation guardrails now include `frontend_timing_tb.sv`, run by the
normal runner: all-address branch/fetch and host reads, restart priority, freeze,
wrap, write collisions and program retention. `test_timing_tools.py` also checks
replay orchestration with a fake STA process; those tests do not measure timing.
See [the test-only diagnosis and hypotheses](../docs/timing_hypotheses_85506c6.md).

Install Python 3.11+, Icarus Verilog and `test/requirements.txt`, then run:

```sh
python test/run.py
```

On Windows, `./test/run.ps1` locates optional `.tools` binaries. The portable runner
uses the submission source list in `info.yaml`. It first runs `pio_fifo_tb.sv`,
then exhaustive host/pad units, exact-edge dual-subsystem FIFO tests and the
pin-only core, PIO21, I2C and dual-PIO suite. The runner also runs host-wrapper
contention/cancellation tests. `make -C test` runs the same cocotb suite; the
standalone FIFO/host/pad/subsystem units and host-wrapper tests are included by
the Python runner only.

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
Use Icarus **13.0** for this PDK revision's gate models, matching the pinned
[Tiny Tapeout gate-test action](https://github.com/TinyTapeout/tt-gds-action/blob/3412659307918422f3f0727917cf9b499aaca588/gl_test/action.yml).
Ubuntu's Icarus 11 left the models' delayed flip-flop signals unknown during
local verification; the same routed netlist passed all 39 tests with version 13.
The physical build and functional gate-level results for commit `b380b86` are
recorded in the [area assessment](../docs/architecture_area_budget.md). These
functional simulations do not prove setup/hold closure or CDC reliability.

### Gate-level CI result naming

The upstream `TinyTapeout/tt-gds-action/gl_test@ihp-cmos5l` action checks results
with `! grep failure results.xml`, including testcase metadata. In
[run 39379346181](https://github.com/shanebri/JaneStreet-protocol-emulator-ASIC-competition/actions/runs/39379346181/job/118519148257),
all 27 tests passed, but the name
`i2c_reset_mid_byte_and_permanent_scl_clear_failure` triggered that check. It is
now named `i2c_reset_mid_byte_and_permanent_scl_clear_rejected`; its assertions,
including the expected `bus_clear_failed` status, are unchanged. Avoid the literal
word `failure` in passing testcase names while using this upstream action.
Actual JUnit `<failure>` elements still cause the gate job to fail.

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

## Dual-engine validation

See [the implemented contract](../docs/dual_pio.md) and
[validation record](../docs/dual_pio_verification.md). `test_dual_pio.py` adds twelve
pin-only tests, also included in the gate-level Makefile module list. Filter
with `COCOTB_TEST_FILTER=^test_dual_pio\.` for focused development. The subsystem
SV unit checks simultaneous operations at the byte interface; it intentionally
uses RTL hierarchy and is not part of the gate-netlist suite. Host-wrapper tests
can also run with `python -m unittest discover -s test -p test_pio_host.py -v`.
