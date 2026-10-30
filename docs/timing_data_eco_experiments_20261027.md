> Historical checkpoint or task record. Status statements and next steps below
> apply to the named revision/date. See [current project status](project_status.md)
> for the qualified dual-engine build and remaining hardware work.

# Localized data-driver, fanout and slew experiments

Date: 2026-10-27 (America/Phoenix). Parent: `9ebc659`.
Branch: `codex/timing-connectivity-electrical`. Status: fifteen isolated screens
complete; no full implementation accepted and timing closure remains open.

## Scope and reference

Implement the final-driver setup experiment and independent remaining
data/input fanout and slew experiments. The committed splitting-only reference
has slow WS -1.184760767 ns, TNS -16.385711030 ns, 23 failing setup endpoints,
28 slow slew and six fanout violations/corner, zero cap violations, positive
all-corner hold, complete annotation and zero clock-buffer fanout failures.
Keep 20 ns, 8x4 boundary/pins, both PIOs, all corners/models/constraints,
reset/enable behavior, host edges, instruction latency and strict gates fixed.
Production RTL and configuration are not edited.

The reference worst path is `ui_in[1] -> _33836_/D`. Its terminal
`_23190_` (`sg13cmos5l_a21oi_1`) contributes 1.471644 ns, with 1.790041 ns
transition at the register and a 0.646512 ns setup requirement. The setup
experiments independently test `a21oi_2` and a non-inverting output `buf_4`.

## Starting-point diagnosis and matched control

The six measured fanout failures do not exist at the saved pre-global-route
point. Antenna repair subsequently adds real input loads:

| Source | Pre-global-route loads | Post-antenna loads |
| --- | ---: | ---: |
| `uio_in[3]` | 3 | 21 |
| `uio_in[2]` | 2 | 10 |
| `_17026_/Y` | 7 | 14 |
| `_16949_/Y` | 8 | 10 |
| `_32068_/Q` | 8 | 9 |
| `_32071_/Q` | 8 | 9 |

For example, `uio_in[3]` has three functional buffer loads and eighteen antenna
diodes. The test must retain these real devices and include subsequent native
antenna repair in the measured result.

All primary trials therefore start from the same **post-antenna logical and
placement snapshot**, before fill insertion. Shared preparation removes 25,301
signal wires for a full reroute, preserving every instance, master, signal
connection, placement/orientation/status and power-grid wiring. The preparer
checks those invariants and records input/output hashes. All runs use identical
legalization, native GRT 0.25, routing/antenna rules, downstream checks and eight
OpenROAD threads. The inherited splitting-only clock topology is retained.

This common reroute changes the physical result. **Only the fresh reroute
control is a matched comparator for these ECOs.** Its result is WS
-0.971601493 ns, TNS -13.406668155 ns, 22 setup endpoints, 62 slew and twelve
fanout violations, zero cap violations and complete annotation. Its setup
improvement and electrical regression versus the old routed reference are
common implementation effects, not gains credited to any ECO. A candidate
must also be evaluated against the original reference before adoption.

An auxiliary attempt to preserve existing routed shapes through the native
global/detailed-routing sequence produced incompatible routing behavior and
large intermediate DRC counts. It was stopped as a diagnostic; it supplies no
timing result and is not a passing/rejected completed screen. The primary
matched full-reroute experiments continued unaffected.

## Isolated recipes

There is one common control and fourteen individual candidates:

- `critical_size`: only `_23190_`, `a21oi_1 -> a21oi_2`.
- `critical_buffer`: only `_23190_/Y`, one `buf_4` isolating its output load.
- `fanout_uio3`, `fanout_uio2`, `fanout_17026`, `fanout_16949`, `fanout_32068`,
  `fanout_32071`: one source per trial, stable sink ordering and groups of at
  most eight loads through `buf_4`, initially at the source location.
- `slew_19177`, `slew_28038`, `slew_23931`: one `nor3`/`nor4` driver per trial,
  drive strength 1 to 2.
- `slew_24358`, `slew_29030`, `slew_18133`: one complex-gate output per trial,
  isolated through `buf_4`. The pinned library has no stronger variant of those
  `a221oi`/`a22oi` gates.

No candidate stacks a critical, fanout and slew repair. Each starts from the
same input and receives the same native processing. Buffering is combinational;
no state or cycle latency is added. Every measured consequence of legalization,
rerouting and antenna repair is included in global setup/hold and electrical
counts. Local improvement is insufficient to claim closure.

The post-ECO audit permits exactly the declared master replacements and buffer
count/functions. Pinned Verilog bodies must match for strength replacements;
`buf_4` must implement `buf(X,A)`. All original signal connections must match
after transparent buffer substitution, all original masters must match except
declared replacements, and clock topology must be identical. This is logical
ECO verification, with PG excluded; it is not routed LVS. The tooling tests pass
39 cases, including rejection of undeclared rewiring, clock modifications and
incorrect selection of a failed attempt when a completed retry already exists.

The two initial port attempts failed before routing because this OpenSTA build
does not support `get_nets -of_objects` on ports. They are preserved as attempt
01. The corrected BTerm-based lookup and port geometry were verified directly
on the frozen ODB; corrected physical attempts use new attempt-02 directories.
Restarting the WSL scheduler also stopped four physical workers. Their partial
attempt-01 outputs are explicitly marked interrupted, supply no result, and are
retained. They are restarted in fresh attempt-02 directories; the three already
completed critical/control results are retained unchanged. No interrupted
attempt is counted as a completed or rejected timing screen.
The later chat interruption ended the final four active workers too; those
partial attempts are preserved and retried separately. A detached scheduler
now survives its launching command, and its resume selection was tested against
the real suite to verify eleven completed cases were reused and only four cases
were pending at that restart. Four unintended duplicate retries were stopped before qualification
while correcting that selection rule; they supply no result. These execution
interruptions and diagnostics do not modify the original reference or any
completed audited result.

## Initial critical-driver results

| Trial | Slow WS (ns) | Slow TNS (ns) | Setup endpoints | Slow slew | Fanout/corner |
| --- | ---: | ---: | ---: | ---: | ---: |
| Matched reroute control | -0.971601493 | -13.406668155 | 22 | 62 | 12 |
| Stronger terminal gate | -1.151809347 | -16.413562529 | 24 | 60 | 10 |
| Terminal output buffer | -0.857633988 | -9.450856365 | 20 | 51 | 11 |

Upsizing worsens global WS by 0.180207854 ns and is rejected as a setup repair.
Output buffering improves WS by 0.113967505 ns and TNS by 3.955811790 ns against
the matched control, with fewer failing endpoints/electrical violations. It is
a positive isolated setup result. Its full-reroute implementation still has
more slew/fanout failures than the old routed reference, so it is not adopted
as an accepted full implementation or presented as timing closure.

### Same-endpoint diagnostic

Separate slow-corner, dynamic-reset STA sessions use the exact actual extracted
views and unchanged constraints to report directly to `_33836_/D`:

| Trial | Original endpoint slack (ns) | Global worst endpoint |
| --- | ---: | --- |
| Matched control | -0.971601 | `_33836_/D`, from `ui_in[1]` |
| Stronger terminal gate | -0.240917 | `_31995_/D`, from `ui_in[1]` |
| Terminal output buffer | +0.417908 | `_31995_/D`, from `ui_in[2]` |

Buffering gains approximately **1.389509 ns on the targeted endpoint**, which
now meets setup. Its smaller global gain reflects the next path becoming
critical. Upsizing improves the targeted endpoint by about 0.730684 ns while
worsening global timing; it must not be accepted based only on that local gain.
The fixed-endpoint data reports are preserved as `fixed_target_02/target_max.rpt`
and `target_min.rpt`. The first diagnostic used the existing template's
reset-only target reports; it was superseded with explicit all-data-to-target
reports and is not counted as a same-endpoint setup measurement.

## Completed electrical comparison and decision

The complete fifteen-row matrix is indexed in
[`comparison.md`](timing/20261027-data-eco/comparison.md), with actual measured
values and deltas in `comparison.json`. Every row has a passing declared-ECO
logical audit and nine completed replay sessions. Inputs, effective configuration
and PDK model hashes match the common control; generated applied scripts match
the declared recipe. Runner snapshots preserve the code version of each attempt.

The following are useful **individual candidates**, with values against the
matched fresh-reroute control rather than the old routed reference:

| Trial | WS (ns) | WS gain (ns) | TNS (ns) | Setup endpoints | Slow slew | Fanout/corner |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Control | -0.971601493 | 0 | -13.406668155 | 22 | 62 | 12 |
| `critical_buffer` | -0.857633988 | +0.113967505 | -9.450856365 | 20 | 51 | 11 |
| `fanout_16949` | -0.960557883 | +0.011043611 | -12.279937415 | 21 | 37 | 10 |
| `fanout_32071` | -0.962005614 | +0.009595880 | -9.198402300 | 20 | 46 | 9 |
| `slew_29030` | -0.915861191 | +0.055740303 | -11.916253210 | 26 | 16 | 9 |

The `_29030_/Y` output-buffer case is the strongest measured slew reduction,
62 to 16, with better WS/TNS and fewer fanout failures. Its setup endpoint count
increases from 22 to 26, so it remains a tradeoff despite those improvements.
The two fanout cases above improve the global counts and setup together.
Their effects have **not been combined or assumed additive**.

Other isolated sizing/buffering choices worsen setup or offer a less favorable
tradeoff. In particular, `fanout_32068` reduces fanout to seven but worsens WS to
about -1.80 ns. `fanout_uio2` halves much of the slew burden but leaves total
fanout at twelve and slightly worsens WS. The complete matrix retains those
results instead of recording only local successes.

**Reject `fanout_uio3`, `fanout_17026`, and `slew_18133` as unqualified timing
candidates.** Each has one filtered parasitic-annotation gap/corner on live
`uio_in[2]`, including the branch to `fanout2572/A` and three antenna pins. This
repeats the previously observed annotation signature; these new routes have not
received an independent GDS connectivity diagnosis. Their raw timing/count
deltas must not be treated as accepted improvements. No live net is excluded.

All fifteen have zero final native routing DRC and antenna violations, zero
capacitance violations, positive all-corner hold, 2,421 connected clock pins
and zero clock-buffer outputs over eight. The final clock auditor was extended
to explicitly recognize native single-input antenna diodes as electrical clock
loads and count them toward fanout. The initial diagnostic parser failure is
retained; physical runs and acceptance limits were not changed by that extension.

All fifteen still fail strict signoff. Twelve have complete parasitic annotation;
three fail that gate. Source RTL and production configuration/constraints are
unchanged. The old splitting-only routed reference retains six fanout and 28
slew failures; because the common reroute changes those counts, none of the
fresh-reroute candidates is silently promoted as a fully qualified replacement.

Next, measure an explicit integration of the individually favorable repairs,
with a matched integration control, before adopting a new physical baseline.
The optional `_29030_` repair needs particular attention to endpoint count and
interaction with the other candidates. Full DRC/LVS, precheck and gate-level
qualification remain required after strict extracted signoff is achieved.

## Reproduction and evidence

Physical runs and scheduler state: `test/sim_build/data_eco_20261027/`.
Compact evidence: `docs/timing/20261027-data-eco/`.
Initial critical launch logs: `test/sim_build/data_eco_<name>_01.log`.
The remaining launch/collection logs are inside the physical suite root.

Run `prepare_data_eco.py` with OpenROAD Python against the splitting-only
`11-openroad-detailedrouting/state_out.json`, into a new prepared directory.
Run `data_eco_trial.py` inside the pinned LibreLane/Nix environment with
`--base <clock_split8-01> --prepared <prepared> --archive-root <archive>
--pdk-root <pdk> --trial <recipe> --out <new-trial> --threads 8`.
Use `closure_collect.py` for each completed run's nine-session replay matrix.
`data_eco_suite.py` schedules at most four workers and retains corrected port
attempts separately. `summarize_data_eco.py` validates matched inputs/configs,
declared ECOs, model hashes, replay results and final routed clock topology.

All experiments retain the unchanged strict post-route gate. Full signoff and
fabrication qualification remain required before architecture additions.
Exact scripts, logical/routed-clock audits, source/model hashes, the 39-test
tooling log, recovery records and `SHA256SUMS` are retained in the compact
evidence. Fifteen matrices contain 135 successful replay sessions; three extra
direct endpoint diagnostics are separate from that count. Invalid/interrupted
attempts supply no timing result and are not counted in the fifteen screens.
