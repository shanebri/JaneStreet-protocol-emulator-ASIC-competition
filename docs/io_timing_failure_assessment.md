# GDS failure assessment: 85506c6

Assessment date: 2026-10-22 UTC (the run finished on October 21 in Arizona).
Scope: compare the failed candidate with its successful-workflow baseline;
assess causes and recovery options. No RTL, constraints, configuration or workflow
changes were made during this assessment.

**Recommendation: retain the candidate for controlled repair experiments; do not
perform a wholesale revert. It is not timing-closed.** The previous revision was
also not timing-closed under the required three-corner policy. The candidate has
better aggregate setup results but worse worst-case setup and slew. Physical
repair is a credible next experiment, not a demonstrated solution.

## 1. What actually failed

Candidate commit: `85506c60783641f7f0a14e13a7e099c9a9b9603f`,
"slow corner fix #1".
[GDS run 39707891759](https://github.com/shanebri/JaneStreet-protocol-emulator-ASIC-competition/actions/runs/39707891759),
[failed job 119592122597](https://github.com/shanebri/JaneStreet-protocol-emulator-ASIC-competition/actions/runs/39707891759/job/119592122597).

The `Build GDS` action completed the physical implementation and reached
LibreLane's final deferred-error handling. It failed on:

- Setup violations at `nom_slow_1p08V_125C`.
- Maximum slew violations at `nom_slow_1p08V_125C` and `nom_typ_1p20V_25C`.

This was not a synthesis crash, routing crash, runner timeout or failure to
understand the new RTL. Routing DRC, Magic DRC and LVS checks passed. Antenna
repair finished with zero violations. KLayout DRC was skipped by the existing
flow configuration; its missing-metric warning was not the fatal error.

The new standalone `check_signoff.py` workflow step was **skipped**, because the
preceding action had already failed. The downstream gate-level test, precheck
and viewer jobs were also skipped. Separately, the RTL test workflow passed:
[test run 39707891680](https://github.com/shanebri/JaneStreet-protocol-emulator-ASIC-competition/actions/runs/39707891680).
Passing RTL tests does not establish routed timing or gate-level correctness.

Running the standalone checker locally against the downloaded candidate
post-route state reproduces rejection of slow setup, slow/typical slew and
fanout at all three corners. Thus fixing the native action's current failures
alone would still leave the fanout gate to satisfy.

## 2. Evidence and like-for-like comparison

Baseline commit: `37c74dc17c3803d30d7b225aa51da10f0809330c`.
[Successful baseline GDS run 39495891524](https://github.com/shanebri/JaneStreet-protocol-emulator-ASIC-competition/actions/runs/39495891524).

Both runs used the same resolved Tiny Tapeout action commit
`3412659307918422f3f0727917cf9b499aaca588`, LibreLane `3.1.0.dev3`, and Yosys
`0.66` / `86f2ddebce7e98ce7cacc27e8a5c14cb53b51b51`. The archived effective
SDC files are byte-identical (SHA-256 in the evidence). Clock period remains
20 ns; existing I/O delays, loads, uncertainty and derates were preserved.

The complete resolved configuration comparison differs only in four checker
corner settings. No physical optimization setting changed in that comparison.
These checks control acceptance; they do not repair timing. This rules out a
changed I/O budget as the explanation for the numbers below. It does not isolate
each RTL edit's contribution or substitute for a controlled physical A/B run.

| Final routed metric | Baseline 37c74dc | Candidate 85506c6 | Assessment |
| --- | ---: | ---: | --- |
| Slow setup worst slack | -5.885337 ns | -6.809803 ns | Worse by 0.924466 ns |
| Typical setup worst slack | +2.427592 ns | +2.992410 ns | Improved |
| Fast setup worst slack | +7.069545 ns | +7.564806 ns | Improved |
| Slow setup total negative slack | -2071.482472 ns | -979.921111 ns | Magnitude reduced 52.7% |
| Slow setup violating endpoints | 821 | 616 | 205 fewer, about 25% |
| Slow/typical/fast slew violations | 19 / 0 / 0 | 55 / 4 / 0 | Worse |
| Slow/typical/fast capacitance violations | 1 / 1 / 1 | 0 / 0 / 0 | Cleared |
| Fanout violations per corner | 178 | 183 | Five more |
| Hold violations, every corner | 0 | 0 | Passing |
| Fast hold worst slack | +0.112777 ns | +0.122530 ns | Passing, limited margin |
| Filtered unannotated nets, every corner | 0 | 0 | No reported filtered annotation gaps |
| Standard-cell area | 369174 um² | 369414 um² | +0.065%; no area explosion |

The old green workflow did **not** mean all-corner timing passed. Its setup
acceptance covered typical only; slow setup and electrical violations could
remain warnings. The candidate changes made these failures fatal, consistently
with the user's requirement to require all three corners.

## 3. What the new critical paths say

The worst candidate path is clocked register `_33835_/Q` to `_33839_/D`, with
26.707644 ns arrival, 19.897840 ns required time and -6.809803 ns slack.
Both registers map to synthesis-generated instruction-memory read-address
registers in engine 1 (`fetch.words$rdreg[1]`, bits 0 and 4). The mapping was
checked against the Yosys JSON and netlist, rather than guessed from numeric
instance names. These names alone are not a complete RTL path-sensitization proof.

Within the 1000 detailed slow setup paths, all 616 negative-slack entries are:

- 306 launched by `_33835_` (engine 1 IMEM read-address register).
- 280 launched by `_33851_` and two by `_33852_` (engine 0 read-address registers).
- 28 launched by `ui_in[2]`; the worst of these has -1.538261 ns slack.

The candidate is therefore not solely failing the original raw-reset input
path. Its worst reported violation is internal register-to-register timing.
Relaxing external host input delays, adding a reset false path, or registering
host commands alone cannot be assumed to solve that path.

The baseline's 821 reported failing endpoint paths all started at `rst_n`.
However, these reports select endpoint winners. They do not enumerate every
alternative startpoint to each endpoint. **Do not infer that the baseline had
no internal violations, or that all candidate reset paths now pass.** Targeted
register-only and reset-specific replay is still needed for that comparison.

There is a particularly actionable electrical problem on the worst path:

| Location | Measured slow-corner value |
| --- | ---: |
| Final driver `_23246_`, `sg13cmos5l_nor4_1` | One logical load |
| Driver output load | 0.178745 pF |
| Driver cell arc delay | 3.561205 ns |
| Driver output transition | 4.579258 ns |
| Capture D-pin transition | 4.583533 ns |
| D-pin transition limit | 2.507400 ns |
| Setup requirement at capture | 1.067971 ns |

The same D-pin transition is 2.969284 ns at typical, which also violates its
2.507400 ns limit. Buffering, drive-strength selection and placement of this
loaded, weakly driven connection are justified investigation targets. A logical
fanout of one does not imply a small routed capacitive load. A passing max-cap
check also does not imply passing slew. The path contains substantial additional
logic; fixing one net is not proof of recovering the entire 6.81 ns deficit.

Fanout is a separate issue: candidate checks contain **174 clock-buffer output
violations and nine other output violations**, versus 171 and seven in the
baseline. The effective limit in the reports is eight, with candidate clock
leaf fanouts reaching 17. Data-path resynthesis alone should not be expected to
remove CTS leaf violations. Clock-tree topology/clustering needs its own trial.

## 4. Responsibility for the failure

**The changes caused the workflow to reject the result, and the physical result
also regressed in important respects.** It would be misleading to say this was
only a stricter checker exposing an unchanged design.

The acceptance-policy change explains the immediate red status. It was
intentional and consistent with the confirmed three-corner requirement. But
making the policy strict does not deliver the requested timing fix. The RTL
candidate reduced total negative slack and violation count while worsening
worst slack and slew. It cannot yet be accepted as an overall timing improvement.

The original implementation record disclosed that routed qualification and
baseline targeted replay were pending. The workflow result now provides the
missing candidate evidence and rejects closure. The implementation nevertheless
stopped short of the user's requested complete fix: functional regressions and
generic synthesis were insufficient, and the plan's measurement prerequisite
was not completed before delivering the RTL experiment.

There is also a workflow sequencing limitation: putting strict checks inside
the build path prevents downstream gate-level validation/precheck from running
when timing fails. That loses useful diagnostic coverage during closure work.
Keep strict final acceptance, but allow experimental build artifacts and
independent validation to be available despite timing failure.

The existing evidence does not isolate whether reset-intent restructuring,
per-bank decode factoring, or their combined mapping/placement caused each
physical regression. A controlled comparison is required before blaming one
specific edit. There is no observed functional failure in the completed RTL
tests, but skipped gate-level tests remain a validation gap.

## 5. Simple fixes and their limits

There are small, reversible configuration experiments worth trying before any
protocol or pipeline change. None has yet been routed and proven here.

| Experiment | Why it fits the evidence | What it does not guarantee |
| --- | --- | --- |
| Enable `RUN_POST_GRT_DESIGN_REPAIR` in an isolated trial | Currently false; adds electrical repair using global-route parasitics, relevant to the slow loaded net and slew violations | May not recover all setup; this LibreLane version labels it experimental and warns of hangs/extended runtime |
| Then trial `RUN_POST_GRT_RESIZER_TIMING` separately | Currently false; adds setup/hold repair with more realistic interconnect estimates than placement | Final extracted timing may differ; preserve fast hold and all-corner checks |
| Adjust CTS sink clustering to respect effective fanout | Most fanout violations are clock leaves, not host logic | Cluster size is a tuning input, not proof of final fanout; recheck clock skew, insertion delay and hold |
| Target remaining weak drivers/control depth if needed | Worst path identifies a specific large delay and slow transition | More RTL work may still be needed; re-run cycle equivalence and physical checks |

These repair switches and their implementation were verified against the exact
LibreLane version's [flow definition](https://github.com/librelane/librelane/blob/3.1.0.dev3/librelane/flows/classic.py),
[electrical repair Tcl](https://github.com/librelane/librelane/blob/3.1.0.dev3/librelane/scripts/openroad/repair_design_postgrt.tcl),
and [timing repair Tcl](https://github.com/librelane/librelane/blob/3.1.0.dev3/librelane/scripts/openroad/rsz_timing_postgrt.tcl).
They are proposed experiments, not settings already applied by this assessment.

An important correction to an easy assumption: `RSZ_CORNERS = null` does not
mean typical-only libraries. The pinned
[resizer implementation](https://github.com/librelane/librelane/blob/3.1.0.dev3/librelane/steps/openroad.py)
uses `RSZ_CORNERS or STA_CORNERS`, and both candidate repair logs show loading
fast, slow and typical models. Merely setting an explicit list of the same
three corners is not a remedy. The post-CTS setup repair reports no violations
under its placement estimate; that is not evidence of final extracted closure.
Intermediate state files also carry older per-corner metrics forward, so their
slow values cannot safely be treated as fresh measurements at every stage.

For CI, a separate strict signoff job can preserve failure status while allowing
completed experimental artifacts, gate-level tests and prechecks to be inspected.
That requires an explicit diagnostic build/artifact path and dependency handling;
moving the Python checker alone does not bypass LibreLane's native fatal checks.
It must not make a timing-failed design eligible for release.

Switching back to typical-only checks would address the red badge, not the
required timing problem; the standalone Python gate would still reject this
candidate. Likewise, increasing the clock period, loosening host budgets,
waiving fanout/slew or adding broad reset exceptions would change or conceal
the requirement. They are not recommended solutions under the current contract.

## 6. Keep the RTL or revert?

**A full revert is not required by these results and is not the preferred first
step.** It restores a known -5.885 ns slow-corner failure and existing electrical
violations, even if the old workflow becomes green. It also discards the new
regression tests and useful timing diagnostics.

Retain the candidate and baseline as comparison points. First try physical
repair with unchanged RTL, 20 ns clock and current I/O budgets. This can preserve
the intent/local-reset and per-bank decode changes without altering externally
visible latency. Whether it actually closes timing is still unknown.

If that does not produce adequate improvement, compare two controlled RTL
variants under the same physical settings: reset-intent/local-reset changes
only, and per-bank command-decode changes only. Keep tests, timing evidence and
strict acceptance in both. The local `imem_write && rst_n` guard is part of the
reset-intent change: removing it while keeping intent can corrupt retained IMEM
during reset. Do not undo that guard independently.

Only selectively revert an RTL portion once the A/B evidence shows it harms
closure, or a functional check identifies a defect. A registered host boundary
or execution pipeline is a later option, because it changes cycle semantics and
the present worst internal path has not yet been resolved by simpler measures.

Recommended sequence:

1. Reproduce baseline and candidate targeted STA in the matching environment;
   report reset, host inputs, outputs/OE and restricted register-to-register
   paths separately at all three corners.
2. Run the isolated physical-repair trials and record setup/TNS/counts, slew,
   cap, fanout, fast hold, area and final routed paths after each trial.
3. Address CTS fanout independently; do not assume data repair covers it.
4. If needed, isolate the two RTL changes with controlled physical A/B runs.
5. Accept only when all three required corners and electrical checks pass,
   alongside functional, gate-level, DRC/LVS and Tiny Tapeout precheck results.

No fresh place-and-route or OpenSTA replay was performed during this assessment:
the local Windows environment lacks that toolchain/PDK. This report is based on
the actual archived routed results, source inspection and local reproduction of
the signoff checker. It establishes the cause and next experiments, not a proven
repair or guarantee that RTL changes will be unnecessary.

## Evidence retained in the repository

See [comparison JSON](timing/85506c6/comparison.json),
[worst slow path](timing/85506c6/worst_slow_setup.rpt),
[remaining ui_in[2] path](timing/85506c6/worst_ui2_setup.rpt),
[register mapping](timing/85506c6/register_mapping.json),
[slow electrical checks](timing/85506c6/nom_slow_1p08V_125C_electrical.rpt),
[typical electrical checks](timing/85506c6/nom_typ_1p20V_25C_electrical.rpt),
[fast electrical checks](timing/85506c6/nom_fast_1p32V_m40C_electrical.rpt),
[STA summary](timing/85506c6/summary.rpt), and
[failure log excerpt](timing/85506c6/job_failure_excerpt.log).

Candidate `GDS_logs` artifact: ID `12401887733`, 246839328 bytes; SHA-256
`cadefda210b3853e4c90882acfd9b80a17bed253aab08dc146f21a114952a3c4`.
The downloaded ZIP hash was verified. Full artifacts remain under ignored
`test/sim_build/gds_failure_85506c6/`; baseline artifacts are under
`test/sim_build/timing_review_37c74dc/`. Small evidence files are retained above
so the conclusions do not depend solely on expiring Actions artifacts.
