# Clock clustering and branch splitting experiments

Date: 2026-10-26 (America/Los_Angeles). Branch:
`codex/timing-connectivity-electrical`; committed parent `12b0f35`.
This records the controlled clock-factor experiments. Status: complete;
clock fanout repaired experimentally, timing closure still open.
Prior methodology and connectivity proof:
[`timing_closure_repairs_20261026.md`](timing_closure_repairs_20261026.md).

## Question and fixed contract

Separate the effect of explicit CTS sink clustering from the existing
post-CTS branch splitter. The previous combined recipe reduced fanout
violations from 172 to 8/corner but worsened slow setup WS by 0.609258439 ns.
The four-way comparison tests both factors independently and their interaction.

All runs start from the exact same saved pre-CTS placement from
`implementation/placement-corners-01`. GRT adjustment remains 0.25, with the
coverage-clean `closure/grt_capacity25-01` route and its exact-state GDS LVS
proof used to qualify the experimental baseline. The runner validates that
proof before starting. The clock is 20 ns; 8x4 boundary/pins, both PIOs, source
RTL, models, optimization/signoff corners, I/O budgets, reset/enable semantics,
latency and every strict acceptance gate remain fixed. No production RTL,
configuration or constraints are changed.

## Four-way design

| Trial | CTS sink cluster size | Extra branch splitting | Post-CTS legalization |
| --- | --- | --- | --- |
| `clock_control-01` | Native automatic (`null`) | None | Same control step |
| `clock_cluster8-01` | 8 | None | Same control step |
| `clock_split8-01` | Native automatic (`null`) | Maximum 8 loads | Same legalization |
| `clock_cap8-01` | 8 | Maximum 8 loads | Same legalization |

Clustering remains **enabled in all four runs**. Automatic sizing is the native
baseline, not disabled clustering. Splitting uses the previously measured
deterministic recipe: stable sink-name ordering, groups of up to eight loads,
`sg13cmos5l_buf_8` buffers initially at the parent location, then legalization.
This is the same splitter as before; no placement heuristic is changed here.
Native post-CTS setup/hold repair and downstream routing/repair stay enabled.

The control and combined recipe are rerun alongside the two new factor-only
cases. All use eight OpenROAD threads and the pinned tools/PDK from the prior
report. Each invocation saves its exact runner and repair/control script bytes
before execution. The final comparator rejects unmatched input hashes,
execution settings or configuration changes other than cluster size.

## Actual post-CTS topology and signal audit

| Trial | Clock buffers | Added split buffers | Clock outputs above 8 | Maximum fanout | Clock-pin depth distribution |
| --- | ---: | ---: | ---: | ---: | --- |
| Control | 250 | 0 | 166 | 19 | 2,421 at depth 4 |
| Clustering only | 493 | 0 | 0 | 8 | 10 at depth 4; 2,411 at depth 5 |
| Splitting only | 626 | 376 | 0 | 8 | 28 at depth 4; 2,393 at depth 5 |
| Combined | 493 | 0 | 0 | 8 | 10 at depth 4; 2,411 at depth 5 |

All 2,421 actual `CLK` pins are reached from the `clk` input in each audit.
The auditor follows clock buffers, explicitly validates unloaded inverter
dummy loads inserted by native CTS, and rejects unknown clock loads or cycles.

For each matched post-CTS step, it also checks every original instance/master,
top-level signal connection and instance signal pin. New cells must be the
expected non-inverting clock buffers; new nets must be their outputs. After
transparent buffer substitution, **all original signal connections match**.
Power/ground is outside this logical audit; it is not physical LVS.

Clustering-only and combined ODBs are byte-identical both immediately after
CTS and after the matched repair/legalization step. The combined recipe inserts
**zero** branch buffers. Thus its splitter has no additional topology effect at
this operating point; the previous combined result cannot be interpreted as a
measured penalty from branch splitting.

The first audit invocation rejected the native `clkload*` inverter dummies;
the corrected auditor explicitly validates that these are unloaded dummy
outputs. The failed diagnostic logs are retained separately. Physical runs were
not altered or restarted by this diagnostic correction. The tooling suite
passes 34 tests, including rejection of data rewiring, inversion and detached
clock sinks.

## Extracted comparison

| Trial | Slow setup WS (ns) | Slow TNS (ns) | Setup endpoints | Slow slew | Total fanout violations/corner |
| --- | ---: | ---: | ---: | ---: | ---: |
| Control | -0.981842191 | -13.117230340 | 19 | 30 | 172 |
| Clustering only | -1.591100630 | -22.324372316 | 28 | 32 | 8 |
| Splitting only | -1.184760767 | -16.385711030 | 23 | 28 | 6 |
| Combined | -1.591100630 | -22.324372316 | 28 | 32 | 8 |

All four have zero filtered annotation gaps, zero capacitance violations and
positive hold slack at every required corner. The minimum all-corner hold
slacks are 0.124545600 ns (control), 0.122341030 ns (clustering and combined),
and 0.117363345 ns (splitting). Native final routing DRC and antenna counts are
zero. Typ/fast setup meets timing in all four; slow setup remains negative.

**Splitting-only is the preferred clock-fanout repair candidate.** Relative to
the matched control it costs **0.202918577 ns** of worst setup slack, versus
**0.609258439 ns** for explicit size-8 clustering. It recovers **0.406339862 ns**
relative to the prior combined recipe, has two fewer total fanout violations
and four fewer slow slew violations than that recipe, and introduces no cap
or hold failure. Compared with the unchanged control, it still worsens TNS by
3.268480690 ns and adds four failing setup endpoints; it is not timing closure.

Clustering-only and combined timing results reproduce exactly. The measured
effect of splitting *after size-8 clustering* is zero because there are no
overloaded branches left to split. The effects are conditional, not additive.
The combined recipe's earlier 0.609 ns setup penalty belongs to the explicit
clustering intervention and its downstream implementation consequences, rather
than an inserted branch buffer. This does not attribute the entire deficit to
clock propagation delay: the global worst endpoint and data routing/repair can
change, which is why native clock reports and expanded data paths are retained.

### Final clock topology and latency

The routed audits reproduce the post-CTS clock-buffer counts and show **166
clock-buffer outputs above eight** in the control and **zero** in all three
repair cases. Every clock pin remains connected. The six residual fanout
violations in splitting-only are data/input pins: `uio_in[3]`, `_17026_/Y`,
`uio_in[2]`, `_16949_/Y`, `_32068_/Q` and `_32071_/Q`. Their actual loads are
21, 14, 10, 10, 9 and 9, respectively, against a limit of eight.

| Trial | Slow rising clock latency min (ns) | Max (ns) | Spread (ns) |
| --- | ---: | ---: | ---: |
| Control | 0.990803 | 1.291220 | 0.300417 |
| Clustering only | 0.923733 | 1.312809 | 0.389076 |
| Splitting only | 0.970103 | 1.377784 | 0.407681 |
| Combined | 0.923733 | 1.312809 | 0.389076 |

Splitting-only has a wider clock-latency spread than clustering-only despite its
better global setup result. This is a tradeoff, not evidence that every clock
quality metric improves. Native all-corner rise/fall latency and setup/hold skew
reports are retained. The splitting-only global worst path is now `ui_in[1]`
to `_33836_/D`; the control's is to `_31993_/D` and the clustering cases' is to
`_31996_/D`, so the global slack difference is not a same-endpoint delay proof.

All four input-state/view and runner hashes match; the only resolved-config
difference is `CTS_SINK_CLUSTERING_SIZE`. Each has nine completed diagnostic
STA sessions across three corners and three reset modes, with no constraint
coverage issues. Dynamic replay setup/hold matches the native extracted state.
The original unqualified route's parasitic gap is not present in any run.

All four fail the unchanged strict gate due to residual setup/electrical
violations. These are controlled post-route screens; no accepted final GDS,
full Magic DRC/Tiny Tapeout precheck or final gate-level qualification is
claimed. Keep the splitting-only recipe as the next experimental base, then
address the remaining data/input fanout and slow slew/setup paths independently.

## Reproduction and evidence

Physical runs: `test/sim_build/clock_factors/<trial>`.
Logs: `test/sim_build/clock_factor_<recipe>_01.log`.
Compact evidence: `docs/timing/20261026-clock-factors/<trial>`.
Prior closure evidence remains unchanged.

```sh
cd /home/shane/eda/librelane-3.1.0.dev3
nix develop --offline --command python3 <repo>/tools/timing/closure_trial.py \
  --base <repo>/test/sim_build/closure/grt_capacity25-01 \
  --placement-base <repo>/test/sim_build/implementation/placement-corners-01 \
  --lvs-proof <repo>/test/sim_build/closure/grt25-gds-lvs-01 \
  --archive-root /home/shane/eda/timing-20261024/current \
  --pdk-root /home/shane/eda/pdk-2bbec755 \
  --trial clock_split8 --out <new-directory> --threads 8
```

Repeat with `clock_control`, `clock_cluster8` and `clock_cap8`, each with a new
output directory. Collect each completed trial with `closure_collect.py` into
`<evidence>/<trial>/sta`, preserving the post-CTS audit alongside it. Run
`summarize_clock_factors.py --trials-root <physical-root> --evidence <evidence>`
inside the pinned environment after all four collections complete. It validates
the matched four-way inputs/configuration and nine-session replay matrices,
audits each final routed clock tree, and preserves all-corner native clock and
setup/hold skew reports.

The compact index is
[`comparison.md`](timing/20261026-clock-factors/comparison.md), with measured
rows/effects in `comparison.json`, exact invocation runners and applied scripts,
native reports, logical insertion and routed topology audits, the tooling test
log and `SHA256SUMS`. Large DEF/ODB/netlist/SPEF views remain in the ignored
physical run directories. Existing closure evidence is preserved separately.
