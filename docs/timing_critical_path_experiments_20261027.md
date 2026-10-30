> Historical checkpoint or task record. Status statements and next steps below
> apply to the named revision/date. See [current project status](project_status.md)
> for the qualified dual-engine build and remaining hardware work.

# Independent buffering of the integration critical cone

Date: 2026-10-27 (America/Phoenix).
Branch: `codex/timing-connectivity-electrical`. This extends the uncommitted
integration work on parent `9ad7f06`.
Status: all three physical screens and 27 replay sessions complete; strict
signoff remains open and no new implementation is adopted.

## Global result and decision

The fresh control exactly reproduces the preceding integration candidate's
WS/TNS, setup endpoints, slew/fanout/cap counts, all-corner hold and filtered
annotation counts. All three share the same prepared input and execution settings.
The validated full comparison is retained in
[`comparison.md`](timing/20261027-data-critical-path/comparison.md) and
[`comparison.json`](timing/20261027-data-critical-path/comparison.json).

| Case | Slow WS ns | WS delta vs control ns | Slow TNS ns | Setup endpoints | Slow slew | Fanout/corner | Fast hold ns |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Control | -0.680044484 | 0 | -6.082395204 | 17 | 44 | 13 | +0.010796087 |
| A: buffer `_28923_/Y` | -0.931022397 | -0.250977912 | -10.658388251 | 19 | 39 | 14 | +0.012216617 |
| B: buffer `_17250_/Y` | -0.679804676 | +0.000239808 | -6.656352102 | 17 | 37 | 8 | +0.012199797 |

**Reject A as a global setup repair.** It worsens WS by 0.250977912 ns, TNS by
4.575993047 ns, adds two failing setup endpoints and one fanout violation.
Five fewer slew violations do not compensate for those regressions.

**B is an electrical tradeoff, not a meaningful setup closure result.** Its
numerical WS gain is only 0.000239808 ns (0.239808 ps), smaller than the existing
1 ps replay-agreement tolerance, and TNS worsens by 0.573956898 ns. Endpoint
count remains 17. It reduces slew by seven and fanout by five. The comparator
ranks B as the best valid candidate by measured WS, but this does not qualify
it for adoption or establish useful setup progress.

Fast-corner hold improves by 1.420530 ps for A and 1.403711 ps for B. Both
remain close to zero at roughly +12.2 ps; these are small margins, not a newly
comfortable hold budget. All required corners/modes retain positive hold.

All three pass declared-ECO logical audits, preserve the original data/clock
connectivity, retain 2,421 connected clock pins with zero overloaded clock-buffer
outputs, and have complete filtered annotation, zero capacitance violations and
zero final native routing DRC/antenna violations. The control has three inserted
buffers; each candidate has four. The extra buffer drives three original loads
for A and seven for B. Every screen still fails the unchanged strict setup and
electrical signoff gate.

Both candidates move the worst path from the control's `ui_in[1] -> _31996_/D`
to `ui_in[1] -> _31995_/D`. A and B have not been combined. Preserve the
preceding `critical_buffer_fanout_32071` recipe as the setup reference;
retain B as a measured electrical alternative. Neither is an accepted full
implementation. The next bounded diagnosis should consider the newly exposed
endpoint and other near-critical paths together before selecting another repair.

## Directed path checks

Six additional slow-corner baseline STA sessions query the two mapped endpoints
for all three cases, with reset and enable dynamic. These are separate from the
27-session matrix. Each verifies unchanged input/model/script hashes, global
setup/hold agreement with the extracted state and an empty coverage report.
The best candidate's explicit new-endpoint slack reproduces its global worst
slack. Exact commands, environments, full paths and results are retained in
[`directed_endpoint_comparison.json`](timing/20261027-data-critical-path/directed_endpoint_comparison.json).

| Case | Setup `_31996_/D` ns | Setup `_31995_/D` ns | Hold `_31996_/D` ns | Hold `_31995_/D` ns |
| --- | ---: | ---: | ---: | ---: |
| Control | -0.680044 | -0.640473 | +1.184617 | +1.131886 |
| A | -0.790418 | -0.931022 | +1.184378 | +1.125107 |
| B | -0.657293 | -0.679805 | +0.702103 | +0.711676 |

B improves the original endpoint's worst slack by 0.022751 ns, but worsens
the new endpoint by 0.039332 ns. Its global WS therefore barely changes and
its TNS worsens. A worsens both endpoint-worst slacks. These queries cover all
startpoints at the endpoint, rather than reporting only a selected favorable
branch through the buffered gate.

The alternate `_28912_` (`a221oi_1`) branch appears in A's worst path to the
original `_31996_/D` and B's new worst path to `_31995_/D`. In A's original-
endpoint report, `_28912_/Y` contributes 1.663226 ns with 1.830549 ns output
slew; B's new global path has 1.712598 ns with 1.891274 ns output slew. Both
reports show two loads at that output. The corresponding worst paths bypass
the `_28923_` gate targeted by A. This identifies a competing late branch;
it does not establish that another buffer or a combination will improve global
timing. No further repair was applied.

The target-specific hold figures above are slow-corner diagnostics, not the
minimum all-corner hold. B's target hold margins decrease even while its global
fast-corner minimum improves slightly. The full nine-session matrix remains
authoritative for each case.

The final tooling suite passes 49 tests, including separate candidate recipes,
exact three-case scheduler selection from a common input, explicit nonempty
control validation, hold deltas and candidate selection starting with A rather
than accidentally skipping it. All three attempts completed as attempt 01.
The preceding integration evidence and other referenced evidence were checksum-
verified before reuse; this suite retains its own snapshots and `SHA256SUMS`.

## Scope and method

Measure the two proposed repairs separately on the best valid integration
recipe, `critical_buffer` + `fanout_32071`. Its preceding measurement was
WS -0.680044484 ns, TNS -6.082395204 ns, 17 setup endpoints, 44 slow slew,
13 fanout violations/corner and +0.010796087 ns fast-corner hold. It remains
an experimental candidate, not an accepted physical implementation.

| Case | Runner recipe | Added repair beyond control |
| --- | --- | --- |
| Control | `critical_buffer_fanout_32071` | None |
| A | `critical_buffer_fanout_32071_buf_28923` | Isolate `_28923_/Y` with one `sg13cmos5l_buf_4` |
| B | `critical_buffer_fanout_32071_buf_17250` | Isolate `_17250_/Y` with one `sg13cmos5l_buf_4` |

All three start independently from the same original prepared post-antenna
input in `test/sim_build/data_eco_20261027/input/`. The runner applies the two
control operations, then exactly one additional operation for each candidate.
No candidate starts from a routed control output, and A and B are never stacked.
The original fifteen-case and five-case suite selections remain separate.

All cases use one common legalization/export step, the same native routing,
antenna repair, extraction and downstream checks, GRT adjustment 0.25 and eight
OpenROAD threads. The detached scheduler runs at most three workers. Output
directories are new under `test/sim_build/data_critical_path_20261027/`.

Every original signal connection/master, declared buffer function/count/sorted
sink group and pre-route clock topology is audited. Collection runs nine
independent STA sessions per case (three corners, baseline/operational/reset-active),
checks coverage and replay agreement, and preserves the actual final metrics.
Final routed clock audits count antenna loads. Comparison requires identical
input/configuration/execution/model hashes, uses this suite's fresh nonempty
control, reports fast-corner hold and its delta, and does not present B as an
incremental addition to A. Global WS/TNS, endpoint and electrical counts determine
the result; local path improvement is only diagnostic evidence.

The 20 ns clock, 8x4 boundary/pins, both PIOs, all models/corners, dynamic
enable, reset/host acceptance edges, instruction latency and strict signoff
gates remain fixed. Production RTL, configuration and constraints are unchanged.

## Reproduction and evidence

Use pinned WSL distro `Ubuntu-24.04`. Run EDA commands from
`/home/shane/eda/librelane-3.1.0.dev3` with
`/nix/var/nix/profiles/default/bin/nix develop --offline --command`.
Set `repo` to
`/mnt/c/Users/shane/Projects/JaneStreet-protocol-emulator-ASIC-competition`.

```bash
python3 "$repo/tools/timing/data_eco_suite.py" --suite critical_path \
  --base "$repo/test/sim_build/clock_factors/clock_split8-01" \
  --prepared "$repo/test/sim_build/data_eco_20261027/input" \
  --archive-root /home/shane/eda/timing-20261024/current \
  --pdk-root /home/shane/eda/pdk-2bbec755 \
  --root "$repo/test/sim_build/data_critical_path_20261027" \
  --evidence "$repo/docs/timing/20261027-data-critical-path" --jobs 3

python3 "$repo/tools/timing/summarize_data_eco.py" --suite critical_path \
  --root "$repo/test/sim_build/data_critical_path_20261027" \
  --evidence "$repo/docs/timing/20261027-data-critical-path" \
  --reference-metrics "$repo/docs/timing/20261026-clock-factors/clock_split8-01/sta/metrics.json"
```

Use new physical/evidence directories for new experiments. The exact detached
launcher, suite selection, runner and audit snapshots, compact extracted
evidence, comparison and checksums are retained under
`docs/timing/20261027-data-critical-path/`. Large physical artifacts remain in
the ignored build directories.
