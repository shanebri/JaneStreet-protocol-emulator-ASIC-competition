# FPGA bring-up v2 implementation — 2026-11-01

The [extended campaign](../tools/bringup/EXTENDED.md) implements persistent
dual-engine stress, boundary/recovery tests, pad ownership/open-drain checks,
and concurrent UART plus SPI with independent USB UART and Nano 33 BLE peers.
It retains deterministic expectations, observed results, raw traffic, sampled
digital waveforms and offline analysis. **Physical v2 board/peer runs have not
been performed.** Cables and the UART adapter are pending.

ASIC RTL, manifest, constraints and production physical recipe are unchanged.
The active ASIC qualification ledger validated successfully. No ASIC timing
headroom is consumed, and no new extracted ASIC signoff run is claimed.
This work changes the FPGA wrapper, host tooling, regression and documentation.

## Qualification scope

The FPGA candidate is built in a fresh directory for the Arty A7-100T
(`xc7a100tcsg324-1`) with Vivado 2026.1 build 6511674. Clocks remain 100 MHz input
and 50 MHz core. The [preserved physical parent](fpga_baseline_20261030.md)
reports +4.618 ns setup and +0.040 ns hold. The builder now rejects a new image
below either reported margin, even when timing remains positive. Comparison is
at the reports' 1 ps precision.

Selected implementation: **`20261101-v2-18`**, with **+4.871 ns setup and
+0.047 ns hold**. This improves the preserved parent's reported margins by
**253 ps setup and 7 ps hold**, consuming no required headroom. The clean build
passes its margin gates and reports **zero DRC findings**, including warnings.
CDC reports 14 safe endpoints and zero unsafe/unknown/missing-ASYNC_REG endpoints.
Timing coverage reports zero no-clock registers and unconstrained internal
endpoints. Utilization is 5089 LUTs (8.03%), 1304 registers (1.03%) and seven
block-RAM tiles (5.19%).

Bitstream SHA-256:
`624e969ab52f0a32527cfea3c4c325e51bf328d14dce2d9d64d0fa7bdac271e9`.
The [receipt](fpga_bringup_v2_20261101_receipt.json) anchors the local candidate
bundle, source snapshot and reports. This qualifies FPGA implementation;
programming, initial smoke and external-peer board tests remain pending.

## Implementation attempts

All directories are under ignored `fpga/build/bringup/`. Failures retain logs,
available reports/checkpoints and source hashes. Earlier passing bitstreams are
retained as experiments; only the selected candidate should be used for v2
bring-up. The preserved v1 image was neither overwritten nor programmed.

| Directory | Setup / hold (ns) | Result |
| --- | ---: | --- |
| `20261101-v2-01` | Not routed | Capture memory inferred as flip-flops; resource DRC failed. |
| `20261101-v2-02` | Not launched | Sandbox could not launch the Vivado environment. |
| `20261101-v2-03` | 3.712 / 0.040 | Native timing passed; 0.906 ns setup regression rejected. |
| `20261101-v2-04` | 3.712 / 0.040 | Explore implementation did not recover setup. |
| `20261101-v2-05` | Not qualified | Forced replication is unsupported after routing; moved before routing. |
| `20261101-v2-06` | Not qualified | Placement completed; the harness incorrectly required 100% run progress at this intermediate stop. |
| `20261101-v2-07` | Not qualified | Harness mistook the next unstarted step for failed placement; replaced status guesses with the concrete placed checkpoint. |
| `20261101-v2-08` | 3.896 / 0.040 | Engine-0 decode replicated; competing engine-1 path limited setup. Rejected. |
| `20261101-v2-09` | 3.896 / 0.040 | Additional decode selection did not improve the critical path. Rejected. |
| `20261101-v2-10` | 3.860 / 0.024 | Decode/ISR fanout replication consumed 16 ps hold as well as setup. Rejected. |
| `20261101-v2-11` | 4.034 / 0.048 | Timing-oriented synthesis improved hold, but setup remained below parent. |
| `20261101-v2-12` | 4.350 / 0.048 | Replicated the measured 350-load early-decode net; sibling decode bit became critical. Rejected. |
| `20261101-v2-13` | 4.618 / 0.035 | Replicated both early-decode bits; setup recovered, but hold lost 5 ps. Rejected. |
| `20261101-v2-14` | 4.618 / 0.084 | Independent FIFO address hold repair passed both margins; capture-RAM asynchronous-control DRC warnings required follow-up. |
| `20261101-v2-15` | 4.119 / 0.047 | Registered observation/reset removes all DRC findings; changed placement consumes setup. Rejected. |
| `20261101-v2-16` | 4.305 / 0.023 | Additional bit-count fanout repair improves setup but loses hold. Rejected. |
| `20261101-v2-17` | 4.269 / 0.047 | Replicated engine-0 PC nets; critical path moves to engine 1. Rejected. |
| `20261101-v2-18` | **4.871 / 0.047** | Both engines' measured PC/decode/count locality targets; all margin, timing-coverage, CDC and zero-DRC checks pass. Selected. |

The memory inference fix uses one multiplexed write port and a synchronous read
port, allowing block RAM rather than a register array. Timing-oriented synthesis
and measured LUT-driver replication spend available FPGA area on locality.
They do not add ASIC pipeline stages or change architectural cycles. These
results illustrate why replication must be measured: the ISR-related trial
degraded hold, despite positive setup/hold slacks.

The retained flow uses timing-oriented synthesis and Explore implementation,
then replicates measured PC registers and competing decode/count LUT drivers in
both engines before routing. Register replication preserves their cycles.
[AMD documents forced net replication](https://docs.amd.com/r/en-US/ug949-vivado-design-methodology/Use-Physical-Optimization)
and the [performance synthesis settings](https://docs.amd.com/r/en-US/ug901-vivado-synthesis/Vivado-Preconfigured-Strategies).
These are implementation choices for this measured FPGA candidate, not a claim
that a strategy always improves timing.

Hold is checked separately. If native paths fall below the preserved 40 ps
margin, complete register-clock-pin-to-data-pin paths are temporarily given an
additional 0.100 ns minimum-delay requirement so routing must add delay.
After repair, `reset_timing` clears timing constraints and the original
`arty_bringup.xdc` is reloaded. Every final setup/hold, competing-path, CDC,
exception, timing-coverage and DRC report uses that original XDC. The temporary
minimum-delay requirement is saved only in `hold_repair_tightened_*.rpt`; it is
absent from final `exceptions.rpt`. Native requirements are neither relaxed nor
hidden by an internal false path. The post-repair `qualified_routed.dcp` is the
final checkpoint; the project's placed checkpoint is not the qualified state.
The selected build already exceeds the hold floor and does not enter this
repair branch. A separate retained diagnostic verifies the branch against the
23 ps checkpoint from rejected build 16: native hold improves to 47 ps, with
setup unchanged at 4.305 ns. That diagnostic does not promote build 16.

The observer has six independent two-register physical-input synchronizers.
The only new XDC exception covers their first-stage D pins. A common registered
observation boundary and a synchronous observer reset prevent asynchronously
asserted clock-loss reset from entering BRAM control/trigger cones. That
observation cycle never feeds the emulated ASIC. Core reset remains visible in
the trace, since only bridge reset resets the observer.

## Software and functional validation

| Check | Local result/evidence |
| --- | --- |
| Original RTL regression and adapter/pad/FIFO unit checks | 39 RTL tests passed, zero failed/skipped; `test/run.py` |
| Bring-up software units | 22 passed; `.bringup/validation/20261101-v2-03/units-final.log` |
| Existing independent SPI checker | 5 passed; `.bringup/validation/20261101-v2-01/spi-checker.log` |
| Legacy accelerated bridge smoke | Passed; `.bringup/validation/20261101-v2-01/smoke.log` |
| Real 434-cycle control-UART divisor check | Passed; `.bringup/validation/20261101-v2-01/default-baud.log` |
| Extended bridge suite | Five tests passed, zero failed/skipped, including the registered observer and all five physical-input protocol channels. |
| Independent saved-capture analysis | UART/SPI, continuous markers, freeze, reset and open-drain captures decode successfully; all remain simulation evidence. |
| Hold-repair branch on a retained weak checkpoint | 0.023 → 0.047 ns native hold, setup unchanged; `.bringup/validation/20261101-v2-03/hold-screen/` |
| Qualified ASIC ledger/source validation | Passed; `.bringup/validation/20261101-v2-01/asic-ledger.log` |

The extended suite exercises actual serial framing, the real bridge, the public
nibble adapter and both cores. Independent simulated UART and SPI peers check
wire data. It tests full RX/TX queues, active drain/refill, overflow/underflow,
TX starvation, partial writes and reads, reset/disable state, IMEM retention,
restart, ABORT release, both pad owners and open-drain transitions.

The retained final simulation is
`test/sim_build/bringup-extended/20261101-210527-755426/`. Its scored concurrent
capture decodes UART `BD E7 83 46` and SPI MOSI `02` / MISO `A7`, with 84.48 us
overlap, host activity during that overlap and four consistent pad loopbacks.
UART, SCLK, MOSI, CS and MISO are decoded from physical-input samples in the
simulation fixture; OE must remain released on all loopback pads. This used the
accelerated control link and simulated peers. It is not a measured board result.
Five captures are retained, including marker progress during host accesses.

Synthesis reports unused packet storage and reserved host-control bits; the
implementation log also reports empty weak-path/violation queries. These were
reviewed as expected messages. The selected default DRC report has zero findings,
and the production FPGA script now rejects DRC warnings as well as errors.

Earlier failures are also retained. They include an incorrect group RESUME
encoding (fixed to `0x030`), a missing harness constant import, and diagnostic
filters initially counted as skipped full-suite tests. Explicit filtered runs
are now labelled diagnostic subsets; a complete suite still rejects all skips.
CI runs the unfiltered suite and uploads its XML, logs and captured waveforms.

## Physical work remaining

Use the [campaign guide](../tools/bringup/EXTENDED.md) to prepare fixtures, program
the selected image, run initial smoke, then change wiring between stress,
recovery, pad and concurrent profiles. The Nano firmware is unchanged. The USB
UART adapter is an independent receive-only 3.3 V TTL peer. The concurrent
profile uses persistent programs with synchronized START/RESUME bursts; the
separate marker phase checks continuous engine progress during host accesses.

Save a new run and separate analysis directory for every attempt. Default
on-FPGA captures include physical pad/input observations, internal-net samples,
raw binary, CSV and VCD; only verified physical-input observations can satisfy
`--require-physical-waveforms`. Time is based on the nominal FPGA clock.
Analog levels, impedance, rise time, contention current and board I/O timing
remain unmeasured. External I/O timing is excluded with the same baseline scope;
the new observer exception does not exempt internal core paths. None of these
FPGA checks replaces extracted ASIC timing/electrical/physical signoff.
