# Timing experiment handoff

October 28 update: the final route screen passes the unchanged all-corner gate,
nine-session replay, clock and protected-route audits. The audited flow is now
enabled in production configuration; its clean GDS/LVS/precheck/gate-test
qualification is running. See [current production status](timing_production_closure_20261028.md)
and [the complete diagnosis](timing_cone_diagnosis_20261027.md). Production
readiness is not yet declared. The following record describes the prior checkpoint.

Branch: `codex/timing-connectivity-electrical`. Latest checkpoint contains the
completed experiments; no production RTL/configuration/constraint change or
qualified physical implementation has been adopted. Timing closure remains open.

Read these first:

- [Latest critical-cone buffer report](timing_critical_path_experiments_20261027.md)
- [Three-case matched buffer comparison](timing/20261027-data-critical-path/comparison.md)
- [Integration ladder report](timing_data_integration_experiments_20261027.md)
- [Five-case integration comparison](timing/20261027-data-integration/comparison.md)
- [Isolated data ECO report](timing_data_eco_experiments_20261027.md)
- [Fifteen-case comparison](timing/20261027-data-eco/comparison.md)
- [Clock factor report](timing_clock_factor_experiments_20261026.md)
- [Connectivity and earlier rejected trials](timing_closure_repairs_20261026.md)

## Current evidence

The splitting-only routed reference has WS -1.184760767 ns, 23 failing setup
endpoints, 28 slew and six non-clock fanout violations, with complete annotation,
positive hold, zero capacitance violations and zero overloaded clock buffers.

The data ECO suite starts from that route's post-antenna logic/placement, clears
signal wires and performs a matched full reroute. Its control is different:
WS -0.971601493 ns, 22 setup endpoints, 62 slew and twelve fanout violations.
Credit ECO deltas only against that matched control; also assess the old routed
reference before adopting an implementation.

Favorable individual data candidates:

| Recipe | WS ns | Slew | Fanout | Setup endpoints |
| --- | ---: | ---: | ---: | ---: |
| `critical_buffer` | -0.857633988 | 51 | 11 | 20 |
| `fanout_32071` | -0.962005614 | 46 | 9 | 20 |
| `fanout_16949` | -0.960557883 | 37 | 10 | 21 |
| `slew_29030` | -0.915861191 | 16 | 9 | 26 |

The critical buffer fixes the original `_33836_/D` path: -0.971601 ns to
+0.417908 ns at the same endpoint. Another path becomes critical. Stronger
terminal-gate sizing regressed global timing and was rejected.

All fifteen screens completed logical ECO audits and nine-session STA matrices
(135 sessions). All retain 2,421 clock pins, zero clock-buffer fanout failures,
positive hold, zero cap violations and zero final native DRC/antenna violations.
Reject `fanout_uio3`, `fanout_17026`, and `slew_18133` for live `uio_in[2]`
parasitic annotation gaps; do not use their raw timing as qualified improvement.
The isolated suite had 39 passing tooling tests. The integration extension had
46; the latest independent critical-cone suite has 49 passing tests.

## Five-case integration ladder, now complete

All five cases started independently from the **same prepared input**, with
fresh controls, identical native routing settings and eight threads per worker:

1. No-ECO matched control.
2. `critical_buffer` only.
3. Add `fanout_32071` to case 2.
4. Add `fanout_16949` to case 3.
5. Add `slew_29030` to case 4; watch its increased failing-endpoint count.

The explicit runner recipes and `--suite integration` scheduler selection are
implemented. All five physical attempts and their 45-session replay matrix
completed in new directories. All logical/routed-clock audits pass; all retain
2,421 clock pins, zero clock-buffer overloads, positive hold, zero capacitance
violations and zero native final DRC/antenna violations. Strict signoff remains
unchanged and rejects every case.

Case 3, `critical_buffer_fanout_32071`, is the best valid combination by setup:
WS -0.680044484 ns, TNS -6.082395204 ns, 17 setup endpoints, 44 slew and 13
fanout violations. WS improves by 0.291557009 ns versus the fresh no-ECO control,
but fanout increases from 12 to 13 and fast hold falls to +0.010796087 ns.
It is not adopted; it also has more slew/fanout failures than the old routed
reference. The fresh no-ECO and critical-buffer-only controls reproduce the
isolated suite's corresponding measurements exactly.

Adding `fanout_16949` in case 4 lowers fanout to eight but worsens WS to
-1.077669540 ns and increases setup endpoints to 31. Case 5's added `slew_29030`
produces a live `uio_in[2]` annotation gap in every corner; reject its raw timing.
The branch includes `fanout2572/A` and three antenna pins, matching the earlier
annotation signature without a new independent GDS connectivity diagnosis.

The best combination's new `ui_in[1] -> _31996_/D` critical path was tested in
three additional directed slow-corner baseline sessions against both fresh
controls. Same-endpoint slack is -0.861540 ns (no ECO), -0.727132 ns (critical
buffer), and -0.680044 ns (best combination). The new cone includes a 1.482684 ns
increment at `_28923_` (`a221oi_1`); its final `_29289_` (`nand2b_1`) contributes
only 0.136843 ns. See the integration report for full paths and hold margins.

The independent critical-cone buffer followup below now tests two targets from
that cone. No architecture addition was made.

## Three-case critical-cone buffer experiment, now complete

The fresh control applies `critical_buffer` + `fanout_32071`. Candidate A adds
one `buf_4` at `_28923_/Y`; candidate B instead adds one at `_17250_/Y`. All
three start independently from the original prepared input with the same native
routing settings and eight threads. No A+B combination was run.

| Case | Slow WS ns | Slow TNS ns | Endpoints | Slew | Fanout/corner | Fast hold ns |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Fresh control | -0.680044484 | -6.082395204 | 17 | 44 | 13 | +0.010796087 |
| A: `_28923_/Y` buffer | -0.931022397 | -10.658388251 | 19 | 39 | 14 | +0.012216617 |
| B: `_17250_/Y` buffer | -0.679804676 | -6.656352102 | 17 | 37 | 8 | +0.012199797 |

The control exactly reproduces the prior integration measurement. Reject A as
a setup repair. B offers fewer electrical violations, but its WS gain is only
0.239808 ps and its TNS worsens by 0.573956898 ns. Retain B as an electrical
tradeoff; do not claim meaningful setup closure or adopt it as a full physical
implementation. Keep the prior recipe as the setup reference.

All three have passing logical/routed-clock audits, complete annotation,
2,421 clock pins, zero overloaded clock-buffer outputs, positive all-required-
corner/all-mode hold, zero cap violations and zero native final DRC/antenna
violations. All fail strict signoff. The 27 replay sessions and six additional
directed slow baseline endpoint checks completed without a restart.

Both candidates' global critical endpoint becomes `_31995_/D` from `ui_in[1]`.
Same-endpoint setup at `_31996_/D` is -0.680044 ns (control), -0.790418 ns (A),
and -0.657293 ns (B); at `_31995_/D` it is -0.640473 ns, -0.931022 ns and
-0.679805 ns respectively. B's improvement at one endpoint is offset by the
other endpoint becoming limiting. All fast hold margins remain only about
11–12 ps; B also reduces slow target-specific hold despite that slight global
fast-minimum gain.

An alternate `_28912_` (`a221oi_1`) branch is now limiting in the inspected
candidate paths, bypassing `_28923_`: A's original-endpoint report has
1.663226 ns delay and 1.830549 ns output slew there; B's new global path has
1.712598 ns and 1.891274 ns. Next diagnose competing branches and multiple
near-critical endpoints together before choosing another bounded repair.
Preserve both physical references and every acceptance gate. No further ECO
or repair combination was applied.

## Local runtime and assets

Windows repository:
`C:/Users/shane/Projects/JaneStreet-protocol-emulator-ASIC-competition`.
WSL repository: `/mnt/c/Users/shane/Projects/JaneStreet-protocol-emulator-ASIC-competition`.

Pinned WSL distro: `Ubuntu-24.04`.
Run SDK commands from `/home/shane/eda/librelane-3.1.0.dev3` via
`nix develop --offline --command ...`. In a non-login detached shell, use
`/nix/var/nix/profiles/default/bin/nix` explicitly.
PDK: `/home/shane/eda/pdk-2bbec755`.
Original archive: `/home/shane/eda/timing-20261024/current`.

Existing physical runs:

- `test/sim_build/clock_factors/clock_split8-01/`
- `test/sim_build/data_eco_20261027/`
- Shared prepared input: `test/sim_build/data_eco_20261027/input/`
- Completed integration ladder: `test/sim_build/data_integration_20261027/`
- Integration compact evidence: `docs/timing/20261027-data-integration/`
- Critical-cone buffer runs: `test/sim_build/data_critical_path_20261027/`
- Critical-cone evidence: `docs/timing/20261027-data-critical-path/`
- Selected successful attempts are named in
  `docs/timing/20261027-data-eco/comparison.json`; several are attempt 02.

Relevant tools: `data_eco_trial.py`, `prepare_data_eco.py`, `audit_data_eco.py`,
`closure_collect.py`, `audit_clock_tree.py`, `summarize_data_eco.py` under
`tools/timing/`. `data_eco_suite.py` selects completed audited retries before
allocating another attempt. Keep long batches detached: killing/restarting the
original WSL invocation terminated its child physical workers. Interrupted,
failed API and stopped duplicate attempts are preserved and excluded from results.

Compact evidence and exact invocation snapshots are retained under
`docs/timing/`; large ODB/DEF/netlist/SPEF artifacts remain in ignored local
build directories. Verify `SHA256SUMS` before reusing compact evidence. Keep
20 ns, 8x4 boundary/pins, both PIOs, all required corners/models, dynamic enable,
reset/host acceptance edges and instruction latency unchanged.
