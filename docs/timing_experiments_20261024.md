> Historical checkpoint or task record. Status statements and next steps below
> apply to the named revision/date. See [current project status](project_status.md)
> for the qualified dual-engine build and remaining hardware work.

# Physical timing experiments, 2026-10-24

Design: `85506c60783641f7f0a14e13a7e099c9a9b9603f`; historical reference:
`37c74dc17c3803d30d7b225aa51da10f0809330c`.
Branch: `codex/timing-closure-20261024`. Previous uncommitted tests and reports
were preserved. The user authorized targeted STA followed by controlled repairs.

**Outcome: no verified timing closure and no production optimization retained.**
The PDK and historical baseline were verified, all requested path classes were
inspected, and five repair candidates were implemented and physically measured.
Every candidate failed the quantitative signoff gate. The RTL candidate was
reverted after regression. Production RTL, constraints, configuration, tile
allocation and CI acceptance remain at 85506c6. Tests, diagnostic tools, isolated
repair recipes and evidence are retained for review.

## Verified environment and baseline reproduction

PDK Git HEAD is `2bbec755dc67ca3db0261c3d6163e15735d66710`.
All six original standard-cell/IO slow, typical and fast Liberty files are
present; hashes are in [environment.json](timing/20261024/environment.json).
Each installed Liberty file also byte-matches its Git blob at the pinned PDK
revision, ruling out uncommitted local model changes.
LibreLane is 3.1.0.dev3, OpenSTA 2.7.0, OpenROAD
`dcf36133a369abc8f3c5e5738cd4d82e4903c0e0`, and Yosys 0.66
`86f2ddebce7e98ce7cacc27e8a5c14cb53b51b51`. The LibreLane checkout is
`ca6adb1e2982cd75445a68b632d461213d8ca421`.

The complete baseline and current GDS_logs archives were hash-checked and
extracted under `/home/shane/eda/timing-20261024/{baseline,current}`.
Existing netlist, nominal SPEF and final SDC were replayed in independent STA
processes. All six historical setup/hold slack values reproduced within 0.001 ns:

| Corner | Historical setup WS (ns) | Replayed setup WS (ns) | Replayed hold WS (ns) |
| --- | ---: | ---: | ---: |
| Slow | -5.885337 | -5.885337 | 0.646020 |
| Typical | 2.427592 | 2.427593 | 0.301122 |
| Fast | 7.069545 | 7.069545 | 0.112777 |

The baseline/current effective SDC is unchanged: 20 ns period, 4 ns I/O budgets,
0.25 ns uncertainty, 0.15 ns clock transition, 0.95/1.05 derates, propagated
clock, and 0.006 pF output loads. No production exception or case analysis was
installed. Nominal RC at all three required cell corners is retained.

## What the targeted reports establish

Both designs were analyzed at all three corners with reset dynamic, held
inactive, and held active: 18 independent sessions. Each generated separate
register-only, reset rise/fall, input-port and output-port setup/hold reports.
All 18 constraint-coverage reports were empty (no reported issues).
Case-analysis sessions are diagnostic and do not qualify reset sequencing.

| Slow-corner targeted result (ns) | Historical | Current |
| --- | ---: | ---: |
| Global setup, reset dynamic | -5.885337 | -6.809803 |
| Global setup, reset held inactive | -3.842775 | -6.809803 |
| Register-to-register setup, reset dynamic | -3.418458 | -6.809803 |
| Reset rise setup | -5.885337 | 1.776970 |
| Reset fall setup | -4.305575 | 2.097446 |
| Worst input setup excluding reset | -3.854863 (`ui_in[2]`) | -4.812579 (`ui_in[1]`) |
| Worst output/OE setup, reset dynamic | 5.617109 | 4.144582 |
| Global setup, reset held active | 11.943954 | 11.808442 |

The local-control change removed the previously failing reset timing, but
internal violations were already present underneath it. Current register setup
is worse by 3.391345 ns in the restricted dynamic-reset query. Host inputs also
have deeper failing alternatives than the global endpoint-winner list exposed:
the current per-port `ui_in[2]` query reaches -4.484401 ns, and `ui_in[1]` reaches
-4.812579 ns. No input/output timing-budget relaxation is justified by these data.

The current register bottleneck remains `_33835_/Q` to `_33839_/D`, mapped to
engine 1 inferred IMEM read-address state. Its loaded terminal NOR and excessive
slew justify the first physical repair trial. Every data/OE output setup query
passes in the current archive; no new output pipeline is indicated.

All-corner per-port and register results, with endpoints, are preserved in
[targeted_paths.json](timing/20261024/targeted_paths.json). Replay manifests and
representative full path reports are beside it. Full reports remain in the WSL
`replay-baseline-v2` and `replay-current` directories.

## Implementation and reproduction

`tools/timing/replay.py` now accepts OpenSTA 2.7's `worst slack max/min` output
and optionally generates reset-held-active sessions via `--reset-active`.
This fixes a real parser incompatibility found on first execution. Added tests
cover the labeled format and separate mode matrix.

`tools/timing/physical_trial.py` resumes physical work from an archived state,
relocating paths to the verified local PDK and extracted artifacts. It never
edits the archived or production configuration, refuses an existing output
directory and records input hashes, the single experimental setting and status.
Unchanged structural metrics are inherited from the archived synthesis;
post-route timing/electrical results must come from the newly completed STA.

Commands run inside the pinned Nix environment (workspace paths abbreviated):

```sh
python3 tools/timing/replay.py --run <baseline>/runs/wokwi \
  --pdk-root /home/shane/eda/pdk-2bbec755 --out <new-baseline-reports> \
  --reference --reset-active
python3 tools/timing/replay.py --run <current>/runs/wokwi \
  --pdk-root /home/shane/eda/pdk-2bbec755 --out <new-current-reports> \
  --target _33839_/D --reset-active
python3 tools/timing/physical_trial.py --archive-root <current> \
  --pdk-root /home/shane/eda/pdk-2bbec755 --out <new-trial> --trial electrical
python3 tools/timing/physical_trial.py --archive-root <current> \
  --pdk-root /home/shane/eda/pdk-2bbec755 --out <new-control> --trial control
```

The electrical trial changes only `RUN_POST_GRT_DESIGN_REPAIR` to true and
starts from the saved global-route state. Its unchanged control starts from
that same state with repair disabled. Both reroute and extract parasitics, retain
all final acceptance settings and continue through native physical checks.
The first two launch attempts failed at Python API setup before physical work;
the first physical launches were `electrical-02` and `control-01`.

The pinned OpenROAD step has a thread-selection defect:
`str(self.config["OPENROAD_THREADS"]) or ...` converts an unset value into
the literal string `None`, so commands use `-threads None`. These runs consumed
about one CPU core, and the archived detailed-route runtime was 01:37:42.138.
The two incomplete serial experiments were deliberately terminated and preserved.
Both comparison runs were restarted with the same explicit `OPENROAD_THREADS=8`:
`electrical-03` and `control-02`. This execution override is recorded separately
from the repair hypothesis. No result from the terminated runs is treated as a
completed physical measurement. A local unchanged control is needed because
thread count can change routing results.

## Functional validation

Linux system Python/Icarus passed the complete `test/run.py` suite: all 39
cocotb tests, 16 timing-tool tests at that snapshot, three Python host tests,
standalone FIFO/frontend/host/pad/subsystem units, and 27,391 differential
cycles against the frozen reference. An additional relocation test then brought
the timing-tool suite to 17 passing tests. RTL is unchanged in these physical
trials. A final acceptance-gate integration test subsequently brought the tool
suite to **18 passing tests**, including rejection of a fanout-only failure.
The successful full log is
`/home/shane/eda/timing-20261024/rtl-regression-complete.log`.

The first Linux verification launches exposed environment issues: mixing
system Python with Nix's wrapped simulator could not load `libexpat.so.1`,
and the initial copied test tree lacked `examples/` firmware fixtures. The
complete rerun used the system simulator with its matching Python venv and all
fixtures. No assertion was weakened or test skipped.

## Clock-distribution experiments

`cts-01` starts from the original detailed-placement state and changes only
`CTS_SINK_CLUSTERING_SIZE` to eight, with the shared eight-thread execution
setting. The generated CTS netlist reduced clock-buffer outputs with more than
eight logical loads from 174 to four. Maximum fanout fell from 17 to 16.
This is a structural result, not a final electrical pass. Cluster size controls
sink grouping but does not cap the fanout of every internal tree branch.

The four remaining drivers are `clkbuf_2_{0,1,2,3}_0_clk`, each with 16 loads.
The separate follow-up `cts-branches-01` adds a deterministic
`OpenROAD.RepairClockFanout` step immediately after CTS and before normal timing
repair. `tools/timing/repair_clock_fanout.tcl` splits each overloaded branch into
groups of at most eight, inserts eight `sg13cmos5l_buf_8` cells in total, legalizes
placement and asserts the resulting clock-buffer fanout limit. The generated
check passed. Clock timing, hold and final electrical checks remain mandatory;
no fanout limit or clock exception was changed.

The custom Tcl script hash is recorded in the trial manifest. The runner can
reproduce these experiments with `--trial cts --cluster-size 8` or
`--trial cts_branches --cluster-size 8`. These recipes are isolated from the
electrical trial and production `src/config.json`.

## Parallel instruction-read RTL experiment

The measured path launches at inferred IMEM read-address state, traverses a
large selection/control cone, and returns to address state. Physical-only
repairs did not recover its setup deficit. The next isolated experiment changes
only `src/frontend/instruction_fetch.sv`: a shared address decode masks the 32
instruction words and a balanced OR tree combines the result. The host read
port, write edge/guard, memory contents and interface are unchanged. No register,
instruction cycle or pipeline latency is added. Synthesis may transform this
structure again; only the new extracted result can establish benefit.

The original 85506c6 RTL was frozen from the pre-change verification copy.
Its renamed differential reference SHA-256 is
`3c4c3d338caaa86f827d1b7d0921a44a0a74cbd1488d0327dd77bc7e68e7e6b6`.
The modified fetch source SHA-256 is
`23a5335340c7162b919ae2e403919eefde0c7ab532e797730244b5cd8b326bf4`.

Validation before physical implementation:

- Yosys sequential equivalence proved all 544 comparison points (including all
  512 stored bits), with zero unproven points, between original and new fetch.
  This is a two-state formal proof, not a claim about arbitrary X propagation.
- Generic Yosys synthesis/structural/no-latch checks passed.
- Both Verilator lint runs reported nine warnings under the explicit local
  command; neither produced a lint error.
- Full RTL regression passed all 39 cocotb tests and all standalone/Python units.
- Separate differential simulation passed 27,391 cycles against frozen 85506c6;
  the normal differential test also passed against frozen 37c74dc.
- All three FPGA simulation regressions passed, including 512 SPI transfers.

Fresh hardening is `parallel-fetch-01`, using `tools/timing/rtl_trial.py` with
the archived resolved settings, verified PDK and shared eight-thread execution.
It starts with synthesis rather than reusing an incompatible physical netlist.
The original template was not in the GDS_logs archive; its replacement was
downloaded from Tiny Tapeout support-tools commit
`d66cf179e7bc4d296362ab7e2e3b344dc3c4f665`. Its die boundary and all 43 signal
pin placements, orientations and layer shapes match the archived applied
template exactly. Allocation, power-pin copy policy and all physical settings
are retained. The input template and source hashes are recorded in the run.

## Gate-level verification environment

Ubuntu's Icarus 11 failed immediately with unknown outputs using this revision's
PDK flip-flop models, whose delayed signals need newer simulator support.
The pinned Tiny Tapeout gate-test action installs Icarus 13.0. That exact package
was downloaded and extracted into the isolated timing workspace, without changing
the PDK models. Gate tests started correctly with this version. These runs use
functional models without SDF; extracted STA remains the timing qualification.

The reproduced routed control passed all 39 functional gate-level tests with
Icarus 13.0, no skips (847.79 s). Its result XML is preserved in
`timing/20261024/control_gate_results.xml`.

## Measured physical-only outcomes

All results below are newly routed and extracted, using the same eight-thread
execution setting. The unchanged control reproduces the archived current
setup/TNS/counts exactly. Its STA log points to the newly emitted netlist and
newly extracted SPEF, ruling out a carried-forward pre-route metric as the
source of that comparison. Required setup/hold and electrical checks were run
on each actual post-route state with `check_signoff.py`; all five were rejected.

| Trial | Slow setup WS (ns) | Change (ns) | Slow TNS (ns) | Setup endpoints | Slow slew | Fanout/corner | Cell area (um2) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Unchanged control | -6.809803 | 0 | -979.921111 | 616 | 55 | 183 | 369414 |
| Post-GRT electrical repair | -6.669463 | +0.140339 | -1166.127309 | 628 | 53 | 178 | 369294 |
| CTS cluster size 8 | -7.193721 | -0.383919 | -1130.830501 | 618 | 52 | 9 | 375635 |
| CTS cluster 8 plus branch split | -6.776606 | +0.033197 | -1055.483069 | 625 | 30 | 7 | 375748 |
| Post-GRT setup/hold repair | -6.485150 | +0.324652 | -1179.156390 | 629 | 58 | 183 | 369479 |

The electrical and setup/hold repair trials improve worst slack slightly but
worsen aggregate setup and endpoint count. They are not retained as production
changes. Timing repair resized one cell and inserted two hold buffers under
global-route estimates; that limited action did not recover the extracted
setup deficit. Merely enabling the switch is not a timing solution.

The CTS branch split removes all clock-buffer fanout violations; its seven
remaining violations are data nets (`fanout2503`, `_17051_`, `fanout2728`,
`_33860_`, `fanout1636`, `fanout2502`, `fanout581`). It is a useful isolated
clock-distribution recipe, but cannot be accepted as closure: slow setup,
aggregate setup, slew and remaining data fanout still fail.

Remaining Magic checks on these rejected runs were intentionally stopped after
the extracted timing decision. The archived Magic DRC alone took 48 min 30 s.
Stop-reason files identify the cutoffs. Interrupted Magic results must not be
treated as valid DRC passes even if a partial tool report contains zero; fresh
DRC/LVS/precheck completion is required before accepting any future candidate.
These trials establish measured repair results and rejection, not fabrication
qualification. Their post-route states, paths, summaries and strict-gate logs
are preserved under `timing/20261024/<trial>/` and as `<trial>_metrics.json`.

## RTL experiment rejection and final decision

The parallel-read candidate completed detailed routing and extracted STA, but
regressed slow setup to **-9.486900 ns**, TNS to **-4689.111070 ns**, and violating
endpoints to **927**. Slew counts became **86 / 16 / 0**, capacitance counts
**6 / 6 / 6**, and fanout counts **186** per corner. Standard-cell area fell
to **366710 um2** (about 0.73% smaller); that area reduction is not a timing win.
The strict gate rejected this result, and the source change was reverted.
The reviewable patch remains at
[failed_parallel_fetch.patch](timing/20261024/failed_parallel_fetch.patch).

All nine targeted sessions were repeated on this candidate's actual routed
netlist/SPEF/SDC. Slow register-only setup improved only from -6.809803 to
-6.197446 ns. Reset rise and fall setup regressed from +1.776970/+2.097446 to
-1.072275/-1.576801 ns. The worst path moved to rising `ui_in[0]` through
host/control logic to `_33300_/D`, mapped to engine 0 RX FIFO word 1, bit 25.
The mapping was verified against the synthesis JSON using cell type and D/Q
bit connections; see [mapping evidence](timing/20261024/failed_register_mapping.json).

That failing input path arrives at 30.061180 ns against 20.574280 ns required.
Its 41 combinational output arcs include 13 buffers. Loaded wide gates remain
expensive: `_17279_/Y` (`nor4_1`) contributes 3.026474 ns with 0.150432 pF load
and 3.884255 ns slew; `_20566_/Y` (`nand4_1`) contributes 2.118000 ns with
0.133304 pF load. Improving one source-level selection structure did not improve
the full distributed command/control network. No shifter diagnosis is inferred.

The complete [three-corner comparison](timing/20261024/comparison.md) includes
setup/hold WS, setup TNS/counts, electrical counts, area and utilization for all
six routed runs. All have nonnegative hold WS and zero hold TNS/counts, but none
meets setup and electrical acceptance together. Remaining Magic checks were
stopped after rejection; no new DRC/LVS/precheck pass or fabrication readiness
is claimed. The failed RTL candidate was not subjected to another full gate
regression after physical rejection; its pre-physical RTL/formal checks and the
unchanged control's gate-level result are distinguished above.

The retained deliverable is the measured diagnosis and reusable experiment/test
infrastructure, not an accepted ASIC optimization. The current 85506c6 RTL and
production settings remain intact. The next defensible trial is selective
driver sizing/buffering using **extracted** loads on the existing mapped weak
control drivers (starting with `_23246_`), followed by register/per-port replay
and all-corner extraction. Global-route estimates missed much of the actual
slew problem, and instruction-read restructuring added new host/control
failures. The clock-branch recipe separately demonstrates how to remove the
174 clock fanout violations, but still needs integration only with a candidate
that also meets setup, slew and remaining data fanout requirements.

Classification: **failed repair experiments with measured partial electrical
improvements; no verified timing closure and no accepted production change.**
