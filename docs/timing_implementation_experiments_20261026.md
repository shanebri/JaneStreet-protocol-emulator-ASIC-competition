> Historical checkpoint or task record. Status statements and next steps below
> apply to the named revision/date. See [current project status](project_status.md)
> for the qualified dual-engine build and remaining hardware work.

# Controlled placement and mapping experiments

Date: 2026-10-26 (America/Phoenix). Branch: `codex/timing-placement-mapping`.
Baseline repository commit: `3b93d70`; unchanged design RTL/archive: `85506c6`.
Status: all five routed screens and 45 diagnostic STA sessions completed;
every strict signoff gate rejected its screen. No production optimization adopted.

## Scope and controls

Continue the approved implementation hypotheses as separate comparisons.
The rejected terminal-NOR ECO is excluded from every run. Production RTL,
configuration, constraints, 8x4 allocation, host edges, 20 ns clock and required
signoff corners remain unchanged. No sequential architecture change is made.

| Trial | Comparator | Only experimental difference | Starting state |
| --- | --- | --- | --- |
| `placement-control-01` | Archived 85506c6 for reproducibility | None | Archived applied DEF template |
| `placement-timing-01` | `placement-control-01` | `PL_TIMING_DRIVEN=true` | Same archived applied template |
| `placement-corners-01` | `placement-timing-01` | Placement-only `PNR_CORNERS` includes slow, typical, fast | Same archived applied template |
| `mapping-control-01` | Independent fresh control | None; `AREA 0` | Fresh synthesis |
| `mapping-delay4-01` | `mapping-control-01` | `SYNTH_STRATEGY="DELAY 4"` | Fresh synthesis |

Run the mapping pair only if the placement comparisons leave substantial setup
deficits. The finite execution sequence uses a remaining worst setup deficit
greater than 1 ns in even the best placement screen as the trigger. This is a
triage rule, not an acceptance margin: signoff still requires WS >= 0 ns and
every mandatory check. Both mapping runs restore original placement settings and synthesis
corner so the strategy is isolated. `mapping_delay0` is also implemented as a
separate optional fallback; it is not automatically combined with `DELAY 4` or
any corner/placement change.

The third placement row intentionally compares against timing-driven placement
with the original views, even if that candidate fails: this isolates view
selection. It does not adopt either candidate as a production improvement.

All resumed placement runs use
`27-odb-applydeftemplate/state_out.json`, original mapped cells, eight OpenROAD
threads, and the unchanged downstream Classic flow through extracted STA.
Timing-driven placement may retain the pinned placer's own resizer changes;
the initial mapped netlist is common, not artificially locked during repair.

## Exact placement-view handling

Pinned LibreLane selects `PNR_CORNERS or [DEFAULT_CORNER]` for placement.
The original default is typical. For the corner experiment, a subclass copies
the configuration **only for `OpenROAD.GlobalPlacement`**, setting its
`PNR_CORNERS` to the three existing views. The flow-level value remains null.
Resizer, CTS, routing and final signoff view selection are not independently
changed by this override. Saved step `config.json` and actual library-loading
logs must confirm the effective views; inherited timing metrics cannot do so.

The collector asserts that actual `Reading timing models for corner ...` log
entries match the expected optimization views. This is independent of the
three-corner final signoff checks.

## Runner and evidence

`tools/timing/implementation_trial.py` contains fixed, reviewed trial recipes.
It rejects a different baseline clock, PDK, synthesis strategy/corner,
placement setting or acceptance-corner list. It refuses an existing output,
records input-state/config/source/runner hashes and the single experiment
change, and keeps execution overrides separate. For fresh mapping it freezes
the unchanged source tree and validates the replacement DEF template against
the archived die and all 43 signal pins, including layer geometry and placement.

`tools/timing/collect_implementation.py` requires completed post-route STA,
rejects missing/nonfinite metrics, preserves the actual state and strict gate,
then runs nine independent STA sessions per design: three corners with reset
dynamic, inactive and active. Case analysis is diagnostic only. It preserves
register/per-port/reset paths, annotation/electrical reports, coverage, source
hashes and effective placement views. It never treats a failed gate as a pass.

These are **post-route screening runs**, ending at `OpenROAD.STAPostPNR`, then
the unchanged `check_signoff.py`. A promising screen still needs full GDS,
Magic DRC, LVS, antenna, Tiny Tapeout precheck and final gate-level verification.
No acceptance gate or production setting is disabled to make the screen pass.

## Commands

Use the existing Ubuntu-24.04 environment:

```sh
cd /home/shane/eda/librelane-3.1.0.dev3
nix develop --offline --command python3 \
  /mnt/c/Users/shane/Projects/JaneStreet-protocol-emulator-ASIC-competition/tools/timing/implementation_trial.py \
  --archive-root /home/shane/eda/timing-20261024/current \
  --pdk-root /home/shane/eda/pdk-2bbec755 \
  --design-root /mnt/c/Users/shane/Projects/JaneStreet-protocol-emulator-ASIC-competition \
  --threads 8 --trial placement_timing \
  --out /mnt/c/Users/shane/Projects/JaneStreet-protocol-emulator-ASIC-competition/test/sim_build/implementation/placement-timing-01
```

Change only `--trial` and the new output directory for each listed recipe.
Mapping additionally requires
`--template /home/shane/eda/timing-20261024/parallel-fetch/tt_block_8x4_pgvdd.def`.
That template is accepted only after the die/signal-pin comparison succeeds.

Collect each completed trial in the same Nix environment:

```sh
python3 tools/timing/collect_implementation.py --trial <trial-output> \
  --pdk-root /home/shane/eda/pdk-2bbec755 \
  --out <new-compact-evidence-directory>
```

Pinned versions remain LibreLane 3.1.0.dev3
(`ca6adb1e2982cd75445a68b632d461213d8ca421`), OpenROAD
`dcf36133a369abc8f3c5e5738cd4d82e4903c0e0`, OpenSTA 2.7.0, Yosys 0.66
(`86f2ddebce7e98ce7cacc27e8a5c14cb53b51b51`), Verilator 5.046 and PDK
`2bbec755dc67ca3db0261c3d6163e15735d66710`. No tool/model substitution.

The environment was checked again: all six original Liberty hashes match and
every production source/configuration byte matches the prior verified regression.
Current version query outputs are preserved in
[`environment.json`](timing/20261026-implementation/environment.json).

## Functional validation

The fresh full regression passed all 39 cocotb tests with zero failures/skips,
FIFO/frontend/host/pad/subsystem units, three Python host tests, and the
27,391-cycle differential comparison. All three FPGA regressions passed,
including 512 SPI transfers. Additional experiment-plan, constraint-guard,
template, collection, replay-consistency and one-factor comparison tests bring
the timing-tool suite to 28 passing tests. These tool tests use fixture metrics;
their numbers are not physical results. The full regression started with 24
tool tests; subsequent focused runs include the four new collection/audit tests.

No RTL is changed. The immediate-85506c6 differential, Verilator lint and
structural/no-latch Yosys results from the prior experiment remain applicable
to the proven identical RTL source bytes. Each fresh mapping run additionally
performs native lint/synthesis/structural checks on its frozen input. Final
mapped gate-level behavior is not inferred from RTL simulation.

## Results and decision

### Trial 1: timing-driven placement, original typical optimization view

The fresh unchanged control reproduces the archived 85506c6 baseline. The
one-factor audit finds exactly `PL_TIMING_DRIVEN: false -> true` in the two
resolved configurations; sources, initial-state/config hashes and execution
settings match. Both actual placement logs load only typical models.

| Metric | Matched control | Timing-driven | Change |
| --- | ---: | ---: | ---: |
| Slow setup WS (ns) | -6.809803 | -4.019178 | +2.790625 |
| Slow setup TNS (ns) | -979.921111 | -360.433613 | +619.487498 |
| Slow setup failing endpoints | 616 | 435 | -181 |
| Slew violations slow/typical/fast | 55 / 4 / 0 | 65 / 0 / 0 | +10 / -4 / 0 |
| Fanout violations per corner | 183 | 174 | -9 |
| Standard-cell area excluding filler (um2) | 369414 | 368697 | -717 |

Hold remains positive at every corner with zero hold TNS/counts; typical/fast
setup pass, capacitance violations and filtered annotation gaps are zero.
Both strict gates reject setup/electrical failures. **Measured setup improvement
without closure; promising experimental direction, no production adoption.**

Restricted slow register setup improves to **-0.717963 ns**. The global worst
is now `ui_in[1]` -> `_33837_/D`, whose Q state maps to engine 1 inferred
instruction-read address bit 2. D and Q connections were checked against the
synthesis JSON, not inferred merely from sequential cell numbering. Reset rise
and fall setup pass at 5.836616 / 5.958825 ns. Slow `ui_in[0/1/2]` setup remains
-3.212502 / -4.019178 / -3.882885 ns. The path-family migration means the
remaining host-input deficit must stay visible alongside register-only results.

Full required-corner table and audit:
[`placement_timing_comparison.md`](timing/20261026-implementation/placement_timing_comparison.md).
Nine targeted sessions per design completed and independently reproduced the
fresh extracted setup/hold values within 0.001 ns. Constraint coverage reports
contain no reported issues. Case-analysis sessions are not production signoff.

### Trial 2: include the existing slow/typical/fast placement views

The placement-step override loaded all three intended original library views;
the flow-level configuration remains unchanged from `placement-timing-01`.
The one-factor comparison passed: no global configuration difference, only
`OpenROAD.GlobalPlacement.PNR_CORNERS` changes locally.

| Metric | Typical placement view | Three placement views | Change |
| --- | ---: | ---: | ---: |
| Slow setup WS (ns) | -4.019178 | -1.440862 | +2.578316 |
| Slow setup TNS (ns) | -360.433613 | -22.343168 | +338.090445 |
| Slow setup failing endpoints | 435 | 33 | -402 |
| Slow slew violations | 65 | 27 | -38 |
| Fanout violations per corner | 174 | 178 | +4 |
| Filtered unannotated nets per corner | 0 | 1 | +1 |
| Standard-cell area excluding filler (um2) | 368697 | 369537 | +840 |

Typical/fast setup WS is 5.122854 / 8.910012 ns. Hold WS remains positive
at 0.656217 / 0.322299 / 0.127587 ns with zero hold TNS/counts. Capacitance,
latch/unmapped/synthesis checks pass. Strict signoff rejects setup, slew,
fanout **and parasitic annotation coverage**. The reported setup improvement
is promising but cannot qualify timing with incomplete parasitic annotation.

The live `uio_in[2]` net is **partially** unannotated at `ANTENNA_34/A`,
`ANTENNA_36/A`, `ANTENNA_38/A` and `fanout2572/A`. This is not dismissed as
an unused clock-load stub: the existing native filter retains it, and the
unchanged strict gate rejects one filtered gap at every corner. Preserve
the failure; do not add a coverage exclusion for this host input.
The SPEF does contain a `uio_in[2]` section, so this is not simply a wholly
absent net. Its connections and the actual filter output are preserved under
`placement-corners-01/{uio_in_2_spef_excerpt.rpt,uio_in_2_annotation_diagnosis.json,filter_unannotated.log}`.
The SPEF resistance graph puts exactly those four sinks in components not
reachable from the input port; the other buffer branch is reachable. This
matches OpenSTA's partial-annotation report. The physical/extraction cause
still requires investigation and fresh complete annotation before accepting
this candidate. A routing open and an extraction omission must be distinguished
with physical connectivity/LVS and extraction checks; the diagnostic alone
does not prove which is responsible. No coverage filter was changed.

Full table and configuration audit:
[`placement_corners_comparison.md`](timing/20261026-implementation/placement_corners_comparison.md).
All nine independent replay sessions reproduced the reported dynamic-reset
setup/hold values; constraint coverage reported no issues. Constraint coverage
and parasitic annotation are separate checks: the latter fails.

### Trial 3: independent delay-oriented mapping

The best placement result still reports a 1.440862 ns setup deficit, exceeding
the documented 1 ns triage trigger. Fresh `AREA 0` control and `DELAY 4`
candidate runs completed using the original typical synthesis corner and
original placement settings. The fresh control again reproduces the original
routed baseline exactly. The configuration audit finds only
`SYNTH_STRATEGY: AREA 0 -> DELAY 4`, with identical frozen source bytes,
template and execution settings. Native lint/synthesis/structural checks pass.
The actual `DELAY_4.abc` includes buffering, upsizing and downsizing.

| Metric | Fresh AREA 0 | Fresh DELAY 4 | Change |
| --- | ---: | ---: | ---: |
| Slow setup WS (ns) | -6.809803 | -1.825343 | +4.984459 |
| Slow setup TNS (ns) | -979.921111 | -32.948461 | +946.972650 |
| Slow setup failing endpoints | 616 | 39 | -577 |
| Slew violations slow/typical/fast | 55 / 4 / 0 | 141 / 25 / 0 | +86 / +21 / 0 |
| Cap violations slow/typical/fast | 0 / 0 / 0 | 19 / 20 / 20 | +19 / +20 / +20 |
| Fanout violations per corner | 183 | 187 | +4 |
| Standard-cell area excluding filler (um2) | 369414 | 377158 | +7744 |

Hold WS remains positive at 0.671722 / 0.320232 / 0.117383 ns with zero hold
TNS/counts. Typical/fast setup WS is 4.644223 / 7.404213 ns; fast setup loses
0.160593 ns versus control but still passes. Filtered annotation gaps are zero.
Area/utilization increase within the unchanged die: 31.2172% standard-cell
utilization versus 30.5762%. There are no latches, unmapped cells or synthesis
check errors. **Measured setup improvement, substantially worse electrical
checks; rejected as a standalone production change.**

The new worst slow path is `ena` -> `_33196_/D`, mapped by D/Q verification
against the new synthesis JSON to `pio.engines[1].core.pins[9]`. It is an
input-to-output-state update path, not evidence for rewriting instruction
fetch or the shifter. Restricted slow register setup improves to -0.515072 ns,
but the runtime-enable input path remains -1.825343 ns. The mapping evidence
is in `delay4_register_mapping.json`.

Full all-corner table and audit:
[`mapping_delay4_comparison.md`](timing/20261026-implementation/mapping_delay4_comparison.md).
`DELAY 0` is implemented as an optional separate recipe but was not run; no
measured result or benefit is claimed for it. No synthesis-corner change or
combined mapping/placement trial was performed.

### Decision and qualification

The requested hypotheses are now measured individually. Timing-driven
placement and inclusion of the slow optimization view both produce broad
reported setup improvements. Independent delay mapping also improves setup,
but creates significant electrical penalties. These gains must not be added
together without a new controlled integration run.

All five actual post-route strict gates fail. All 45 independent diagnostic
sessions complete, reproduce their dynamic-reset setup/hold values within
0.001 ns and report no constraint-coverage issues. Native detailed-router DRC
and OpenROAD antenna violations are zero for all five screens. Those checks
do not replace full Magic DRC, LVS, final gate-level tests or Tiny Tapeout
precheck; these were not completed for the rejected screens. The live input's
disconnected SPEF branch remains an explicit failure despite native router
DRC/antenna passes.

No verified timing closure, accepted production setting or fabrication-ready
GDS is claimed. Classification: **measured implementation improvements without
closure, with failed electrical signoff; the three-view placement candidate
also has unresolved parasitic coverage**. RTL functional evidence is separate
from final mapped gate-level qualification.

Before considering adoption, resolve `uio_in[2]` physical/extracted connectivity,
then re-extract and inspect the remaining host/enable paths and electrical
violations. A later combination trial must address the delay mapper's slew/cap
penalties and the remaining clock/data fanout, while retaining all existing
functional and acceptance requirements. No production file was changed here.

The complete overview and per-pair reports are indexed in
[`comparison.md`](timing/20261026-implementation/comparison.md). Exact source,
runner, libraries, netlists/SPEFs/SDCs, state hashes and commands are preserved
in the experiment/replay/source manifests and `suite.log`. Parent commit is
`3b93d70`; the new implementation is reviewable on the dedicated branch.

### Run locations

Local run directories:
`test/sim_build/implementation/`; launch logs:
`test/sim_build/{placement_control_01,placement_timing_01}.log` and
`test/sim_build/implementation/{placement-corners-01,mapping-control-01,mapping-delay4-01}.log`.
Complete physical states and full reports remain in these ignored local build
directories; compact evidence is retained under `docs/timing/20261026-implementation/`.
