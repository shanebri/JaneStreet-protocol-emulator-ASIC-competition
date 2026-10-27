# Timing experiment handoff

Branch: `codex/timing-connectivity-electrical`. Latest checkpoint contains the
completed experiments; no production RTL/configuration/constraint change or
qualified physical implementation has been adopted. Timing closure remains open.

Read these first:

- [Latest data ECO report](timing_data_eco_experiments_20261027.md)
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
The final tooling suite has 39 passing tests. No combinations have been measured.

## Recommended next work, not yet started

Implement a five-case cumulative integration ladder from the **same prepared
input**, not successively routed outputs:

1. No-ECO matched control.
2. `critical_buffer` only.
3. Add `fanout_32071` to case 2.
4. Add `fanout_16949` to case 3.
5. Add `slew_29030` to case 4; watch its increased failing-endpoint count.

Use new output directories, identical native routing settings, and the same
eight-thread execution setting. Extend the explicit recipes/runner for these
combinations and adapt the bounded scheduler to select only the intended five
cases. Do not assume isolated improvements add. Keep all existing timing,
electrical, annotation and acceptance gates; test the best valid combination's
new critical path before further repairs or architecture additions.

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
- Selected successful attempts are named in
  `docs/timing/20261027-data-eco/comparison.json`; several are attempt 02.

Relevant tools: `data_eco_trial.py`, `prepare_data_eco.py`, `audit_data_eco.py`,
`closure_collect.py`, `audit_clock_tree.py`, `summarize_data_eco.py` under
`tools/timing/`. `data_eco_suite.py` selects completed audited retries before
allocating another attempt. Keep long batches detached: killing/restarting the
original WSL invocation terminated its child physical workers. Interrupted,
failed API and stopped duplicate attempts are preserved and excluded from results.

Compact evidence and exact invocation snapshots are committed under
`docs/timing/`; large ODB/DEF/netlist/SPEF artifacts remain in ignored local
build directories. Verify `SHA256SUMS` before reusing compact evidence. Keep
20 ns, 8x4 boundary/pins, both PIOs, all required corners/models, dynamic enable,
reset/host acceptance edges and instruction latency unchanged.
