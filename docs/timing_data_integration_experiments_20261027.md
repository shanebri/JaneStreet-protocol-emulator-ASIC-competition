# Cumulative data ECO integration ladder

Date: 2026-10-27 (America/Phoenix). Parent: `9ad7f06`.
Branch: `codex/timing-connectivity-electrical`.
Status: five physical screens and 45 replay sessions complete; timing closure
remains open and no implementation is adopted.

## Results and decision

The complete evidence is in
[`comparison.md`](timing/20261027-data-integration/comparison.md) and
[`comparison.json`](timing/20261027-data-integration/comparison.json).
The fresh no-ECO and critical-buffer controls reproduce their earlier WS/TNS,
endpoint and electrical counts exactly. Deltas below use this fresh no-ECO
control, not the older splitting-only routed reference.

| Case | Slow WS ns | WS gain vs control ns | Slow TNS ns | Setup endpoints | Slow slew | Fanout/corner | Complete annotation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1: no ECO | -0.971601493 | 0 | -13.406668155 | 22 | 62 | 12 | yes |
| 2: critical buffer | -0.857633988 | +0.113967505 | -9.450856365 | 20 | 51 | 11 | yes |
| 3: add `fanout_32071` | -0.680044484 | +0.291557009 | -6.082395204 | 17 | 44 | 13 | yes |
| 4: add `fanout_16949` | -1.077669540 | -0.106068046 | -16.392297761 | 31 | 41 | 8 | yes |
| 5: add `slew_29030` (REJECT raw timing) | -1.032132631 | -0.060531137 | -12.700797218 | 29 | 35 | 10 | **NO** |

Case 3 is the best valid combination by global slow setup WS. Relative to the
critical-buffer-only control, it improves WS by 0.177589504 ns and TNS by
3.368461161 ns, and reduces setup endpoints from 20 to 17 and slew from 51 to 44.
However, fanout worsens from 11 to 13; the isolated fanout repair's electrical
improvement does not carry over to this combination. Its fast-corner hold WS is
only +0.010796087 ns, versus +0.118656366 ns for the no-ECO control. Positive
hold is retained, but that smaller margin is material.

Adding `fanout_16949` in case 4 reduces fanout from 13 to eight, while regressing
WS by 0.397625055 ns, TNS by 10.309902557 ns and increasing failing endpoints
from 17 to 31. This step is rejected as a setup improvement. The favorable
isolated changes are not additive.

**Reject case 5 as an unqualified timing candidate.** It has one filtered
parasitic-annotation gap in every corner on live `uio_in[2]`, including
`fanout2572/A` and `ANTENNA_17/A`, `ANTENNA_19/A`, `ANTENNA_21/A`. This repeats
the earlier annotation signature; no independent GDS connectivity diagnosis was
performed on this new route. Its raw timing/electrical values remain in the
matrix but are not credited as qualified gains. Its raw endpoint count falls
from case 4's 31 to 29, yet remains above the control's 22.

All five have passing declared-ECO logical audits, 2,421 connected clock pins,
zero clock-buffer outputs above eight loads, positive all-corner/all-mode hold,
zero capacitance violations and zero final native routing DRC/antenna violations.
Cases 1–4 have complete filtered annotation. All five fail the unchanged strict
signoff gate. No row is a qualified full implementation.

The older splitting-only route has WS -1.184760767 ns, 23 failing setup
endpoints, 28 slew and six fanout violations. Case 3 improves WS by
0.504716283 ns and endpoints by six against that route, but worsens slew by 16
and fanout by seven. Its reroute therefore does not replace the older physical
reference as an accepted baseline. Full strict extracted signoff and subsequent
DRC/LVS, precheck and gate-level qualification remain required before adoption
or architecture additions.

## New critical-path check

The best valid combination's new worst path is `ui_in[1] -> _31996_/D`.
Three additional slow-corner baseline STA sessions explicitly query all
startpoints to that same mapped pin, with reset and enable dynamic and the exact
extracted views/constraints from each case. These sessions are separate from
the 45-session replay matrix. Input/model/script hashes, global setup/hold
agreement and empty coverage reports are checked. Results are in
[`critical_endpoint_comparison.json`](timing/20261027-data-integration/critical_endpoint_comparison.json).

| Same endpoint `_31996_/D` | Setup slack ns | Target hold slack ns |
| --- | ---: | ---: |
| Fresh no-ECO control | -0.861540 | +1.141350 |
| Critical buffer only | -0.727132 | +1.151268 |
| Critical buffer + `fanout_32071` | -0.680044 | +1.184617 |

The selected combination's explicit endpoint setup equals its independently
replayed global worst slack. The gain at this endpoint is 0.181496 ns versus
the no-ECO control and 0.047088 ns versus the critical-buffer-only control;
these differ from global WS deltas because the controls have different worst
endpoints. Target-specific hold above is not the minimum all-corner hold.

The best route has data arrival 21.430279 ns and required time 20.750235 ns.
Its terminal `_29289_` (`nand2b_1`) contributes only 0.136843 ns, with
0.072264 ns transition at D and a 0.188981 ns setup requirement. The cone's
larger increments include `_28923_` (`a221oi_1`), 1.482684 ns delay with
1.603071 ns output slew, three loads and 0.079801 pF capacitance, and `_17250_`
(`a221oi_1`), 1.253049 ns. This is a different cone from the original terminal
driver experiment. These are diagnostic observations for the next bounded
repair, not a measured repair proposal; no further ECO or architecture change
was added in this ladder.

The final timing-tool suite passes 46 tests, including exact ladder selection,
fresh controls from a common input, mismatched configurations/threads, failed
audit retry selection, deterministic sink groups and exclusion of invalid
screens from best-combination selection. Both prior evidence checksum manifests
were verified before reuse; this suite has its own `SHA256SUMS` and invocation
snapshots. All five attempts completed as attempt 01 without a restart.

## Method and fixed contract

This implements the five-case ladder from
[`timing_handoff_20261027.md`](timing_handoff_20261027.md). Each case starts
independently from the same shared prepared post-antenna state in
`test/sim_build/data_eco_20261027/input/`. No case starts from a previous case's
routed output. Both controls are newly routed in this suite: no ECO and the
previously favorable critical output buffer alone.

| Case | Recipe | Added operation |
| --- | --- | --- |
| 1 | `control` | None |
| 2 | `critical_buffer` | Buffer `_23190_/Y` through `buf_4` |
| 3 | `critical_buffer_fanout_32071` | Split `_32071_/Q` into groups of at most eight |
| 4 | `critical_buffer_fanout_32071_16949` | Split `_16949_/Y` into groups of at most eight |
| 5 | `critical_buffer_fanout_32071_16949_slew_29030` | Buffer `_29030_/Y` through `buf_4` |

The explicit cumulative recipes preserve operation order and unique inserted
instance/net names. Every case uses the same one-time legalization, native
GRT adjustment 0.25, antenna repair, detailed routing, extraction and downstream
checks, with eight OpenROAD threads per worker and at most four workers.
The scheduler selects exactly these five cases with `--suite integration`.
Its default isolated mode retains the original fifteen cases. A fresh suite
schedules its own controls without waiting on the earlier suite's directories;
resume reuses completed passing logical audits and rejects still-running
selected attempts before launch.

The data audit checks each target's deterministic sorted sink partition, in
addition to exact declared buffer count/functions, transparent original signal
connectivity, unchanged original masters and unchanged clock topology. This
prevents a cumulative recipe from appearing to pass with one repair missing
and extra buffers elsewhere. Routed clock audits include native antenna loads.

Comparison requires identical prepared state/view hashes, resolved configuration,
execution settings and PDK models. Collected metrics and gate failures must equal
the actual final state, and all nine fresh STA sessions must match that state.
The integration comparator requires the old routed reference metrics and retains
both control-relative and preceding-case deltas. It rejects incomplete annotation,
nonpositive hold, capacitance violations, native DRC/antenna failures and overloaded
clock buffers when selecting a valid combination. Setup, slew and fanout failures
remain visible under the unchanged strict gate; validity for comparison is not
acceptance of an implementation.

The 20 ns clock, 8x4 boundary/pins, both PIOs, all required corners/models,
dynamic enable, reset/host acceptance edges and instruction latency remain fixed.
Source RTL, production configuration and constraints are unchanged.

## Reproduction

Use the pinned `Ubuntu-24.04` distro and run SDK commands from
`/home/shane/eda/librelane-3.1.0.dev3` via
`/nix/var/nix/profiles/default/bin/nix develop --offline --command`.
The repository is mounted at
`/mnt/c/Users/shane/Projects/JaneStreet-protocol-emulator-ASIC-competition`.
The following paths are relative to that repository; supply absolute paths when
running from the SDK directory:

```text
python3 tools/timing/data_eco_suite.py --suite integration \
  --base test/sim_build/clock_factors/clock_split8-01 \
  --prepared test/sim_build/data_eco_20261027/input \
  --archive-root /home/shane/eda/timing-20261024/current \
  --pdk-root /home/shane/eda/pdk-2bbec755 \
  --root test/sim_build/data_integration_20261027 \
  --evidence docs/timing/20261027-data-integration --jobs 4

python3 tools/timing/summarize_data_eco.py --suite integration \
  --root test/sim_build/data_integration_20261027 \
  --evidence docs/timing/20261027-data-integration \
  --reference-metrics docs/timing/20261026-clock-factors/clock_split8-01/sta/metrics.json
```

Use new physical and compact evidence directories for a new comparison; never
overwrite prior evidence. Keep the physical batch detached. The exact launcher,
selection, runner snapshots, logical audits, extracted STA evidence and final
comparison are retained in `docs/timing/20261027-data-integration/`. Large
physical views remain in ignored `test/sim_build/data_integration_20261027/`.

For an independently mapped critical endpoint, `replay.py --target <pin>` now
writes all-startpoint `target_max.rpt` and `target_min.rpt` in each baseline-corner
session, alongside the existing reset-only target reports. This is a diagnostic
on the actual extracted views with unchanged constraints, not an exception.
