> Historical single-engine revision 0x21 report. Current dual-engine
> implementation results and remaining physical qualification are in
> [dual_pio_verification.md](dual_pio_verification.md).

# Revision 0x21 verification matrix and report

Tests observe the external Tiny Tapeout pins unless explicitly listed as a module
unit. Production firmware/encoder drives the resolved-wire acceptance model;
the target decodes actual wire transitions independently of instruction encoding.
No test result establishes analog compliance, board interoperability or physical fit.

## Requirement-to-test matrix

All cocotb names below are runnable with `COCOTB_TEST_FILTER`. Paths containing
the named tests are linked in the first column. Loops within each test cover
multiple values, maps, rates and lifecycle states.

| Requirement | Concrete test / independent check |
| --- | --- |
| 4/4 ownership, all addresses/byte values, byte boundary | [host_interface_tb](../test/host_interface_tb.sv): all 16×256 combinations against mock core acceptance counters; [pio_pads_tb](../test/pio_pads_tb.sv); I2C external tests |
| Low/high order, held strobes, idle gaps, coherent snapshots | `host_interface_tb`; `host_bus_atomic_words_and_reset`; `conditional_transfers_nonblocking_drop_and_snapshot` in [test.py](../test/test.py) |
| Address/direction abandonment, RD+WR resync, reset/disable/reentry | `host_interface_tb`; `protection_pause_restart_fault_and_natural_wrap`; `partial_host_commits_and_abandoned_rx_snapshot` |
| Read stable during held RD, forbidden host OE, concurrent protocol activity | `host_interface_tb`; Host helper asserts low-nibble OE on every transfer; all [test_i2c.py](../test/test_i2c.py) tests service the host while firmware runs |
| Exactly-once instruction commit/increment, FIFO word commit and IRQ clear | `host_bus_atomic_words_and_reset`; `partial_host_commits_and_abandoned_rx_snapshot` in [test_pio21.py](../test/test_pio21.py) |
| RX first-nibble snapshot/pop, abandoned read not rolled back | `partial_host_commits_and_abandoned_rx_snapshot`; `fifo_order_backpressure_and_nonblocking` |
| FIFO full/empty simultaneous core/host traffic, atomic stalls | [pio_fifo_tb](../test/pio_fifo_tb.sv) exhaustive boundaries plus deterministic scoreboard; `fifo_order_backpressure_and_nonblocking`; `autopull_autopush_and_atomic_stall` |
| Every pad/mixed value-direction-OD combination, reset gating | `pio_pads_tb`: all 16×16×16 vectors, independent drive/release classification; `side_direction_priority_lifecycle_abort` |
| Fixed capability masks, unrelated state preserved | `input_namespaces_sync_filter_and_physical_readback`; `directions_mapping_counts_autopull_and_exec`; `expanded_value_mov_out_mapping_and_sideset` |
| Released output latch high while external actual input low | `input_namespaces_sync_filter_and_physical_readback`; FPGA contention/abort test |
| SET/OUT PINDIRS, all bases, width clipping, counts1..32, both shift directions | `directions_mapping_counts_autopull_and_exec`; `expanded_value_mov_out_mapping_and_sideset`; existing `variable_shifts_all_widths_both_directions` |
| PINDIRS autopull success/stall, no partial consume, EXEC injection | `directions_mapping_counts_autopull_and_exec` (both MOV EXEC and OUT EXEC); existing `scratch_branches_mov_and_exec` |
| Side-set value/direction overlap and separate-state updates, stall, illegal suppression | `side_direction_priority_lifecycle_abort`; `sideset_all_indices_halt_capabilities_and_invalid_routing`; `deterministic_timing_wrap_delays_and_sideset`; `abort_wait_fifo_partial_transport_and_rearm` |
| All six IN/MOV/WAIT GPIO/PIN/JMP inputs, bases, invalid indices | `input_namespaces_sync_filter_and_physical_readback`; `synchronization_latency_and_relative_wait_indices`; `assembler_revision_and_checked_examples` |
| Synchronizer latency, running while disabled, spike qualification | `synchronization_latency_and_relative_wait_indices`; `input_namespaces_sync_filter_and_physical_readback` (40 ns rejected pulse and stable transition) |
| START/STOP/RESUME/HALT/fault/disable, driven high and low, WAIT/FIFO stalls, partial transport abort, re-arm | `abort_wait_fifo_partial_transport_and_rearm`; `side_direction_priority_lifecycle_abort`; `freeze_delay_and_irq_wait_semantics`; `protection_pause_restart_fault_and_natural_wrap` |
| Stopped configuration protection and live FIFO/IRQ | `side_direction_priority_lifecycle_abort`; `protection_pause_restart_fault_and_natural_wrap`; `input_wait_irq_and_firmware_receive`; I2C timeout/recovery |
| Assembler new encodings/rejections and checked hex | `assembler_revision_and_checked_examples`: every checked-in assembly/hex pair; [FPGA I2C test](../fpga/tb_arty_i2c_bridge.sv) loads canonical hex |
| Resolved pull-ups, controller/target ownership, no active-high OD, delayed rise | [i2c_model.Bus](../test/i2c_model.py) continuously resolves separate drivers and checks target-owned SDA; `tb_arty_i2c_bridge` detects actual X under intentional push-pull contention |
| Address/write ACK/NACK at every payload position | `i2c_nacks_at_every_position` (address plus each of six data positions); `i2c_rates_payloads_repeated_start_and_remap` |
| Read bytes, intermediate ACK/final NACK, repeated START and STOP | `i2c_rates_payloads_repeated_start_and_remap`; `i2c_fifo_streaming_starvation_backpressure`; target independently records bytes/ACKs/STARTs/STOPs |
| 00/FF/55/AA/01/80, walking bits, seeded random | `i2c_rates_payloads_repeated_start_and_remap`, seed2102, both target rates |
| Both rates, diagnostic rate, delayed SDA/rise, multiple stretch positions | `i2c_rates_payloads_repeated_start_and_remap`: dividers6/24/240, delayed edges, stretches at falls1/7/9/18; `i2c_asynchronous_target_phases_and_rise_budget` covers 1/3/7 ns phase offsets and rise delays through 295 ns |
| Actual-wire setup/high/low/START/STOP/bus-free, post-stretch high, pulse counts | `Bus.check_timing` and rise-count assertion in `i2c_rates_payloads_repeated_start_and_remap`; explicit SCL period limits, byte order/ACK ownership and start/stop counts reject spurious edges |
| More than four FIFO words, deliberate service gaps, RX full/TX empty legal stalls | `i2c_fifo_streaming_starvation_backpressure`: twenty ordered read bytes, eight queued commands, full RX, stable edge counters during waits |
| Bus busy, SDA stuck, successful and failed nine-clock clear | `i2c_busy_clear_timeout_abort_and_recovery` |
| Permanent SCL low, bounded abort, host accessibility, re-arm and subsequent transfer | `i2c_busy_clear_timeout_abort_and_recovery`; `i2c_reset_mid_byte_and_permanent_scl_clear_failure` |
| Reset mid-transfer and subsequent clean transaction | `i2c_reset_mid_byte_and_permanent_scl_clear_failure` |
| Alternate/nonadjacent pad assignment, unrelated outputs | `i2c_rates_payloads_repeated_start_and_remap`: pads0/1,2/3,3/1; dedicated outputs checked |
| Preserve UART TX/RX, SPI timing/ISA binaries | `firmware_uart_full_waveforms_and_example`; `input_wait_irq_and_firmware_receive`; `firmware_spi_mode0_byte_transfer`; all original twelve tests retained |
| FPGA integration migration/shared framing | `tb_arty_demo`; `tb_arty_spi_test`; `tb_arty_i2c_bridge`; `tb_arty_uart_diagnostic` |
| Manifest completeness, no unintended latches/multiple drivers/internal tri-states | [run.py](../test/run.py), FPGA runners and [synth.py](../test/synth.py) use info.yaml; Yosys check/no-latch assertion; ASIC has no Z assignments |
| 8x4 and 50 MHz target, CMOS5L physical and gate checks | Manifest/config retain targets; physical tools/PDK/netlist unavailable, **not validated** |

## Reproducible commands

From repository root, using the installed optional Windows tools:

```powershell
./test/run.ps1
./fpga/test.ps1
./fpga/test_spi.ps1
./fpga/test_i2c.ps1
$env:PATH = "$PWD/.tools/icarus12/mingw64/bin;$PWD/.tools/mingw64/bin;$env:PATH"
iverilog -g2012 -Wall -Wno-timescale -s tb_arty_uart_diagnostic -o fpga/build/uart_diagnostic.vvp fpga/arty_uart_diagnostic.sv fpga/tb_arty_uart_diagnostic.sv
vvp fpga/build/uart_diagnostic.vvp
$env:YOWASP_CACHE = "$PWD/.tools/yowasp-cache"
.tools/venv/Scripts/python.exe test/synth.py --yosys .tools/venv/Scripts/yowasp-yosys.exe --revision HEAD --name baseline
.tools/venv/Scripts/python.exe test/synth.py --yosys .tools/venv/Scripts/yowasp-yosys.exe
git diff --check
```

The baseline is the pre-change HEAD. On other platforms use `python test/run.py`
and `python test/synth.py --yosys yosys` with dependencies on PATH. Icarus crashed
with access violation inside this session's filesystem sandbox; simulator runs
succeeded outside that sandbox. The checked-in scripts prefer installed Icarus12.
No toolchain was installed for this task.

## Synthesis comparison and physical limits

Recorded functional outcomes on 2026-10-19:

- Complete cocotb run: **27 passed, 0 failed**, including all original twelve tests.
- Standalone units: FIFO scoreboard passed; host 4096 address/value combinations
  passed; pad 4096 value/direction/mode combinations passed.
- Recovery refinement: all three focused metadata/recovery/reset tests passed
  after adding the LOW command before bus clear, including a first-pulse low-time
  assertion. Firmware hex and 24-word memory use are unchanged.
- FPGA UART loader: three frames, exact 434-clock bits, debounce/replay/reset passed.
- FPGA SPI: 512 transfers, UART reports, mismatch and missing-target checks passed.
- FPGA I2C: canonical firmware, tri-state readback, address NACK/STOP, intentional
  contention and abort-release passed.
- Standalone FPGA UART diagnostic: three frames at 868 clocks/bit and reset passed.
- `git diff --check` passed. Final synthesis source snapshot matches every current
  ASIC source listed in the submission manifest.

Both snapshots use identical `synth -noabc`/`check -assert`/no-latch flow on their
actual manifest sources. YoWASP ABC could not create its temporary genlib path,
so neither reported comparison includes ABC mapping.

| Generic metric | Baseline | Revision0x21 | Delta |
| --- | ---: | ---: | ---: |
| Cells including submodules | 9154 | 10030 | +876 (9.57%) |
| Mux cells | 4747 | 5207 | +460 |
| Flip-flop cells, all enable/reset variants | 1142 | 1218 | +76 |
| Wire bits | 10745 | 12132 | +1387 |

Structural checks pass with no inferred latches or conflicting drivers. The one
synthesis warning expands the three four-bit filter-history array entries into
registers, as intended. Icarus `-Wall` compilation reports no width truncation
warnings in the ASIC modules. Combinational pad OE depends on registered direction,
value and OD configuration. OD data is tied low. Push-pull data/OE paths can have
different propagation delays; software establishes values before enabling drivers.
Reset gates protocol OE combinationally; state reset remains synchronous.

CMOS5L area/timing, PDK cell simulation and gate-level tests could not run:
`PDK_ROOT` is unset, no gate-level netlist exists, and librelane/Verilator/Vivado
are not on PATH. Generic counts are not area, placement, 50 MHz closure or 8x4 fit.
No board was programmed and no hardware interoperability was tested.

## Firmware and bandwidth

I2C uses 24/32 instruction words and one TX/RX word per byte (plus START/STOP
commands). UART and SPI checked hex remain unchanged. Minimum host byte service
is four clocks; a word with selector is twenty clocks (400 ns at 50 MHz), a
2.5 Mword/s upper bound before polling/service overhead. The byte-paced I2C driver
drains each response; bounded low-phase stalls absorb host jitter, not sustained
throughput deficits. See [the timing derivation and limitations](i2c.md).

In resolved-wire tests with delayed rise and stretching, observed minimum low/high
times were 1395/1225 ns (Fast configuration) and 5575/4505 ns (Standard
configuration). These exceed Table11 minima; they are simulation observations,
not analog compliance measurements. Stuck operations use simulator-time deadlines;
random payloads use explicit deterministic seeds. FPGA testbenches have hard
watchdog timeouts.
