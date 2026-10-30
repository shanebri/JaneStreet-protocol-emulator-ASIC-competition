# Arty FPGA baseline — 2026-10-30

The current programmable FPGA image has a preserved physical USB-host/core smoke
baseline: the initial six checks passed, followed by 100 complete iterations of
the same six scenarios (600 checks), with no recorded failures. This qualifies
the exercised behavior on the reported board setup. External protocol peers,
sustained concurrent engine/host stress and physical waveform measurements remain
open. No ASIC qualification is implied.

## Identity and preserved artifacts

| Item | Recorded value |
| --- | --- |
| Baseline ID | `arty-a7-100t-20261030-smoke` |
| Build/run Git commit | `51be3fe9d4941ceb86ff7f57cef561802485b2c0` |
| FPGA top / target | `arty_bringup_top` / `xc7a100tcsg324-1` |
| Tool | Vivado 2026.1, build 6511674 |
| Core / input clocks | 50 MHz / 100 MHz |
| Control link | Arty onboard USB UART, COM3, 115200 baud, 8N1 |
| Bitstream SHA-256 | `eae65c98681b502283fa53732b4229626d2c81eef60da5c0945aa448c7986d15` |
| Original build | `fpga/build/bringup/20261030-153607-616748` |
| Original runs | `test/output/bringup-001`, `test/output/smoke-endurance-001` |
| Preserved directory | `.bringup/baselines/arty-a7-100t-20261030-smoke/` |
| Portable archive | `.bringup/baselines/arty-a7-100t-20261030-smoke.zip` |
| Archive checksum | Same archive path plus `.sha256`; see companion receipt in `docs/` |

The archive retains the bitstream, complete isolated Vivado project and routed
checkpoints, build logs/reports/metadata, original run manifests, result records,
raw UART packet logs, fixture files, source snapshots, assembler, host software,
firmware assembly/hex, wiring record, waveform acquisition status and verification
script. Per-file hashes are in `files.sha256.json`. Original evidence is copied,
not overwritten. Heavy/local artifacts remain ignored by Git; this report and
the checksum receipt can be version controlled. The archive is local storage,
not an off-device backup. Copy the ZIP and checksum to durable backup storage.

All sources covered by the build's recorded source hashes are checked against
the preserved source copies; both run image hashes match the preserved bitstream.
Example assembly hashes are also checked against the run manifests. Both runs
recorded a dirty working tree. Current Git status/diff are preserved separately
as preservation-time provenance; they cannot reconstruct every uncommitted file
as it existed at test time. The run manifests did not hash the Python harness;
its current snapshot is preserved without claiming historical hash attestation.
The image hash identifies the on-disk file selected in the fixtures, not an
independent JTAG readback of the device configuration.

## Results and implementation review

| Run | Result | Seeds | Recorded interval (America/Phoenix) |
| --- | --- | --- | --- |
| Initial smoke | 6/6 PASS | 2201 | Oct 30, 15:44:46–15:45:04 |
| Endurance | 600/600 PASS, 100/100 complete iterations | 2201–2300 | Oct 30, 16:01:56–16:30:09 |

The initial run repeats the first endurance seed: there are 100 distinct seeds,
not 101. Preservation verifies exact scenario/iteration/seed coverage and audits
the transport logs for paired commands/replies, packet checksums, sequence
continuity and successful reply status. Counts are recorded in `summary.json`.
Host timestamps measure software session duration; they are not pin waveforms
or cycle-accurate engine execution measurements. LD7 was reported continuously
on during endurance, without an instrumented lock-history capture.

| Routed report | Finding |
| --- | --- |
| Setup slack | +4.618 ns |
| Hold slack | +0.040 ns |
| DRC | 0 reported violations in the default report |
| CDC summary | 8 safe endpoints, 0 unsafe, 0 unknown, 0 lacking ASYNC_REG |
| Internal timing coverage | 0 no-clock registers; 0 unconstrained internal endpoints |
| External timing scope | 8 inputs and 13 outputs have no I/O delays and are covered by false paths |

These slacks are static timing analysis, not measured delays. External false-path
constraints leave board-level setup/hold and electrical behavior unqualified.
The timing summary also states that `report_methodology` was not run beforehand;
the reports are not a full methodology signoff. Preserve the exact XDC when
comparing timing across revisions, especially the 40 ps hold margin.

## Priority coverage and remaining work

| Priority | Exercised in this baseline | Still required for stronger physical qualification |
| --- | --- | --- |
| Simultaneous engines during host traffic | Both banks loaded; group-start both engines; four short executions with independent RX checks and host polling | Sustained looping execution on both engines while host reads/writes continue; verify progress/data integrity and absence of cross-bank corruption. The current four-instruction runs may finish before the next serial command reaches the core. |
| FIFO boundaries | Four distinct TX words per engine; full TX level observed; ordered draining; one RX word checked at a time; empty TX blocking | RX depth four and full backpressure, attempted overflow/underflow with flags, nonblocking operations, and refill/drain during active dual-engine execution |
| Reset / disable recovery | Engine 0 blocks on empty TX; global disable/re-enable; enqueue unblocks it; reset restores discovery/empty-FIFO state; fresh reset before every case | Reset/disable with both engines running, nonempty RX/TX, blocked RX-full, partial host staging and asserted bidirectional output enables; prove pad release and clean restart |
| Pad ownership | Walking all eight dedicated output bits; switch entire ownership mask to engine 1 and back; internal output-net sampling | Split ownership masks, simultaneous output updates, bidirectional pad input/output/OE readback, open-drain release, and external electrical observation of contention/release |

Discovery also checks revision `0x21`, capabilities and both banks. Bank tests
check seeded scratch isolation and interleaved partial word commits. Instruction
memory tests write/read all 32 addresses in each engine using seeded patterns.
These are repeatable checks of the physical USB-to-core path.

The ownership scenario samples FPGA internal nets through the bridge. It does
not observe voltages at JA/JB/JC. No external pin behavior is credited from that
scenario alone.

## Firmware and wiring

Smoke firmware is generated dynamically, rather than running the UART/SPI/I2C
examples. The preserved `firmware/` contains assembled snapshots of:

```text
fifo_execution: pull block; mov isr, osr; push block; halt
recovery:       pull block; halt
```

Other scenarios use direct host register writes or seeded instruction-memory
patterns, reproducible from `source/tools/bringup/scenarios.py`, the saved seeds
and assembler. The original instruction writes also remain in the UART logs.
The `examples/` programs are saved as references; physical protocol testing of
those examples was not performed in these runs.

The reported physical setup is one PC-to-Arty PROG/UART micro-USB data cable,
with no external protocol peers connected. Wiring is user-described, without
a photograph or independent connector inspection. Exact board revision, serial,
USB supply measurements and ambient temperature were not recorded.

| Connector | Preserved image mapping; external behavior unmeasured |
| --- | --- |
| JA1 / JA2 / JA3 | Output0 / output1 / output2; SPI MOSI / SCLK / CS_n; JA1 also PIO UART TX |
| JA4 / JA7 | Dedicated input0 / input1; SPI MISO / READY |
| JB1 / JB2 / JB3 / JB4 / JB7 | Outputs3 / 4 / 5 / 6 / 7 |
| JC1 / JC2 / JC3 / JC4 | Bidirectional protocol pads0 / 1 / 2 / 3; I2C SDA / SCL on JC1 / JC2 |
| JA5 / JA11 | Ground |
| JA6 / JA12 | 3.3 V power; not signal pins |

The authoritative mapping is the archived `source/fpga/arty_bringup.xdc`.
The endurance fixture contains `uart_peer_port: COM3`, which smoke does not use.
It is not a valid separate UART receiver configuration. Original fixtures are
preserved unchanged; use a new fixture for future peer tests.

## Physical waveform record and acquisition plan

**NOT ACQUIRED.** No physical measured waveforms were supplied or found in the
repository. Existing FST files are simulation output and are excluded from the
physical evidence. `waveforms/capture-status.json` explicitly records the gap;
raw host serial logs are preserved without relabeling them as measurements.

When capture equipment is available, append a new evidence bundle referencing
this bitstream hash; do not alter this frozen bundle. Prioritize:

1. Concurrent engines plus host traffic: capture independently identifiable
   engine output markers together with USB-UART RX/TX signals where accessible;
   correlate host transactions with continued progress of both engines.
2. FIFO boundaries: capture observable progress before/during/after TX starvation
   and RX-full backpressure, with exact host commands and returned levels/flags.
3. Reset/disable recovery: capture reset/enable-related behavior and pad release
   while both engines are active, then prove correct restart and FIFO state.
4. Ownership: capture dedicated and bidirectional outputs across ownership
   transfers; measure high-impedance/open-drain release using an appropriate
   external load/pull-up and check for contention. A static logic level alone
   does not prove high impedance.

For every acquisition retain the instrument's native capture, exported samples,
annotated screenshot, wiring photograph/table, instrument/probe model, sample
rate, thresholds, voltage range, timebase, trigger, loading/pull-up details,
firmware/settings/seed, host logs, supply/ambient observations, timestamp and
SHA-256 hashes. Do not infer analog rise time or voltage quality from a digital
logic-analyzer trace.

## Reuse and integrity

From the repository root, verify the portable archive:

```powershell
Get-FileHash .bringup/baselines/arty-a7-100t-20261030-smoke.zip -Algorithm SHA256
Get-Content .bringup/baselines/arty-a7-100t-20261030-smoke.zip.sha256
py .bringup/baselines/arty-a7-100t-20261030-smoke/verify.py
```

For a future revision, keep the frozen image and harness, create new fixture/run
directories, record the new image hash, and repeat seeds 2201–2300 before adding
stronger scenarios. Compare per-scenario results, packet errors, exact constraints,
implementation timing and external captures separately. Host elapsed time is
affected by PC scheduling and USB latency and is not a core-speed benchmark.

The artifact preserves the completed baseline; it does not claim that the open
priority tests or missing waveform acquisitions have been completed. No new
hardware session, FPGA rebuild or source RTL change was made during preservation.
