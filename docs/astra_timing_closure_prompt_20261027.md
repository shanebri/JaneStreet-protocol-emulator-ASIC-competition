> Historical checkpoint or task record. Status statements and next steps below
> apply to the named revision/date. See [current project status](project_status.md)
> for the qualified dual-engine build and remaining hardware work.

# Astra prompt: diagnose and finish timing/electrical closure

Copy everything below into Astra in this project's current chat/workspace.

---

Please perform an evidence-based root-cause analysis of the remaining ASIC timing and electrical failures, implement the justified fixes, and qualify the final implementation so this project can move on to architecture development. Continue through diagnosis, repair, integration, and verification. An analysis report or another isolated successful endpoint experiment alone does not complete this task. Do not promise closure before measuring it; if a real blocker remains, identify it precisely and preserve a reproducible handoff.

## 1. Establish the actual starting state

Repository: `C:/Users/shane/Projects/JaneStreet-protocol-emulator-ASIC-competition`.
Expected branch: `codex/timing-connectivity-electrical`; inspected HEAD: `9ad7f06`.

Inspect the current checkout before acting. There are existing uncommitted timing-tool/test changes and completed integration/critical-cone evidence beyond HEAD. Preserve them. Do not reset the checkout, discard work, or analyze HEAD as though it contains all current results. Record the actual starting commit, relevant diff, and input hashes. Read applicable AGENTS.md instructions.

Read in this order:

1. `docs/timing_handoff_20261027.md`
2. `docs/timing_critical_path_experiments_20261027.md`
3. `docs/timing/20261027-data-critical-path/comparison.json` and `directed_endpoint_comparison.json`
4. `docs/timing_data_integration_experiments_20261027.md` and its comparison under `docs/timing/20261027-data-integration/`
5. `docs/timing_data_eco_experiments_20261027.md`
6. `docs/timing_clock_factor_experiments_20261026.md`
7. `docs/timing_closure_repairs_20261026.md`
8. `docs/timing_implementation_experiments_20261026.md`

Use `docs/timing_root_cause_analysis_20261025.md` as historical context, not the current failure inventory. The README's -5.885 ns reset-origin result and the historical 616-endpoint report do not describe the latest experiments. Reset was previously dominant; the current leading failures are host-address paths. Rediscover the current facts.

The latest integration and critical-path SHA256SUMS were verified during prompt preparation: 291 and 236 files respectively, zero mismatches. Verify again before reuse. The archived timing-tool log records 49 passing tests; rerun against your current tree. Prompt preparation did not rerun physical implementation or tooling tests because Windows Python and WSL access were unavailable in that session.

## 2. Keep these three different physical references distinct

All figures below are slow-corner results, except the explicitly identified fast hold margin. These are experimental references; none passes strict signoff or is an adopted production implementation.

| Reference | Setup WS ns | Setup TNS ns | Failing endpoints | Slew | Fanout/corner | Fast hold ns |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Older routed splitting-only `clock_split8-01` | -1.184760767 | -16.385711030 | 23 | 28 | 6 | positive; obtain exact value |
| Matched post-antenna full-reroute no-ECO control | -0.971601493 | -13.406668155 | 22 | 62 | 12 | +0.118656366 |
| Best useful setup recipe: `critical_buffer_fanout_32071` | -0.680044484 | -6.082395204 | 17 | 44 | 13 | +0.010796087 |

The reroute control changes physical implementation even without an ECO. Attribute candidate improvements to its matched control, then also compare the resulting implementation against the older routed reference. Do not credit common rerouting effects to a repair.

The latest independent followup adds one buffer to that third recipe:

- A, `_28923_/Y`: WS -0.931022397 ns, TNS -10.658388251 ns, 19 endpoints, 39 slew, 14 fanout. Rejected for setup regression.
- B, `_17250_/Y`: WS -0.679804676 ns, TNS -6.656352102 ns, 17 endpoints, 37 slew, eight fanout, fast hold +0.012199797 ns. Electrical tradeoff only: the 0.239808 ps WS gain is below the existing 1 ps replay-agreement tolerance and TNS worsens.

Both expose `_31995_/D` as the new worst endpoint. Do not adopt B merely because the comparator numerically ranks its WS first. A+B has not been measured; individual effects are not additive.

## 3. Diagnose the complete failing cone before choosing another repair

Create a current inventory of every failing setup endpoint and remaining electrical driver, with enough near-critical alternatives to reveal competing branches. Query multiple paths per endpoint and all relevant startpoints; a single global worst path per endpoint is insufficient. Include register-origin, host input, ena, reset rise/fall, and output/OE paths. Compare the best setup reference and electrical alternative where useful.

For the 17 current setup failures:

- Map each numeric endpoint back to its RTL register, engine, and function using the exact matching synthesis/netlist artifacts. Verify correspondence rather than inferring it from instance numbering. Explain the host-address-to-state-update dependency in source-level terms.
- Cluster paths by shared host acceptance/address decode, engine selection, staged-word destination selection, core/FIFO update logic, and reconvergent branches, as supported by mapping. Count how many endpoints each proposed repair can actually affect.
- Separate cell-arc delay, wire delay, slew-dependent delay, load, logic depth, arrival/required time, and capture-clock effects. Identify where load isolation helps and where redundant logic or reconvergence dominates. Do not count all buffer delay as removable.
- Identify the exact global fast hold path behind the roughly 11 ps margin. Carry that path and competing hold endpoints through every setup repair. A slow target-specific hold report is not the all-corner hold minimum.

Specific current leads to investigate, not predetermined fixes:

- The setup reference's worst path is `ui_in[1] -> _31996_/D`; `_31995_/D` is close behind (-0.640473 ns in its directed report).
- On the reference `_31996_/D` path, `_28923_` (`a221oi_1`) contributes 1.482684 ns, but its output buffer experiment regressed global timing.
- The competing `_28912_` (`a221oi_1`) branch bypasses `_28923_`. It contributes 1.663226 ns with 1.830549 ns output slew in A's original-endpoint path, and 1.712598 ns with 1.891274 ns slew in B's new worst path, despite only two reported loads. Determine the actual cause and affected endpoint set before buffering it.
- The reference path also includes loaded early/middle stages: `_17226_` nor3 (~1.058 ns), `_17250_` a221oi (~1.253 ns), host input distribution and several decode/control stages. The final `_29289_` nand2b contributes only ~0.137 ns. Explain whether a shared upstream correction offers more value than chasing another terminal gate.

Inspect `src/host_interface.sv`, `src/pio_subsystem.sv`, `src/pio_host_bank.sv`, `src/protocol_core.sv`, `src/execution_unit.sv`, `src/pio_fifo.sv`, and `src/frontend/` against the mapped cones. Current host acceptance includes pending-address equality and live address decode; establish which exact logic reaches the failing registers.

Classify every reported error as a current design failure, invalid coverage/connectivity evidence, infrastructure failure, or historical resolved issue. Distinguish an expected strict-signoff rejection from a crashed/incomplete experiment. Do not spend the run repairing old launcher/parser incidents unless they reproduce and block current work.

## 4. Respect measured failures and avoid repeating them unchanged

- `critical_buffer` fixes the original `_33836_/D` endpoint from -0.971601 ns to +0.417908 ns; global setup remains negative because other paths take over. Stronger terminal sizing worsened global timing.
- Adding `fanout_16949` to the best integration recipe worsened WS to -1.077669540 ns and increased failing endpoints to 31. Its isolated improvement did not survive integration.
- The earlier `pending_word` RTL cache passed formal and functional checks but physically regressed from -0.955799023 ns/21 endpoints to -2.529187598 ns/270 endpoints, with new cap violations. It was reverted. Read its retained patch and result before proposing related predecode. Reconsider only with a materially different hypothesis and fresh matched implementation.
- `DELAY 4`, timing-driven placement, placement corner selection, clock clustering, branch splitting, and several slew/driver experiments already have measured histories. Read those results; do not assume an unexplored configuration or repeat a rejected trial with a new label.
- Live `uio_in[2]` annotation gaps recur on some routes, including the integration ladder's fifth case and isolated `fanout_uio3`, `fanout_17026`, `slew_18133`. Earlier GDS LVS proved physical connectivity for specific earlier routes, not every later route. GRT adjustment 0.25 avoided one extraction representation defect; it did not repair OpenRCX generally. A new gap invalidates timing credit until diagnosed on that exact artifact. Never exclude the live net or inherit an unrelated LVS proof.
- Antenna repair adds actual loads after earlier fanout repair. Count functional pins, antenna diodes, and native clock dummy loads correctly in the final extracted/routed design. Pre-route fanout success is insufficient.

## 5. Implement a bounded, hypothesis-driven closure strategy

Write a short ranked causal diagnosis, then execute the best supported repairs. Each experiment must predict which endpoints/electrical drivers it helps, explain its mechanism and risks, and have a matched comparator. Use a small adaptive sequence; do not launch a broad blind sweep or stop after the first local improvement. If one mechanism repeatedly fails, change the mechanism based on the measured paths.

Prefer supported implementation/mapping/load-distribution repairs or localized combinational RTL restructuring. A source change may shorten shared acceptance/commit/selection logic, but must preserve every externally observable cycle and simultaneous-operation priority. Do not add a pipeline, change instruction or host latency, replace the ISA, or start unrelated architecture expansion. If evidence shows the fixed contract cannot be closed with the available approaches, identify the smallest necessary contract change with supporting measurements rather than silently making it.

Use fresh output directories, frozen inputs, actual library/configuration/runner hashes, audited transformations, and identical execution settings for comparisons. Recheck global WS, TNS, endpoint count, electrical counts, complete annotation and hold after legalization, routing, antenna repair and extraction. Preserve rejected and interrupted attempts without counting them as qualified screens. Reuse completed audited attempts.

## 6. Make a successful repair survive the normal build

This is a required deliverable. Existing gains are saved-state experiments; production RTL/configuration/constraints and normal CI have not adopted them. Do not finish with a collection of manual ECOs that only works on an ignored ODB snapshot.

Once a candidate passes, integrate the supported settings and any necessary audited repair step into the actual Tiny Tapeout/LibreLane production path. Trace `.github/workflows/gds.yaml`, `src/config.json`, `info.yaml`, and the pinned flow. A clean build must reproduce the fix. If a repair targets cells by generated number, replace that dependency with validated structural/source identification or regenerate and verify the targets for that build; never reuse numeric names across resynthesis blindly. Preserve matched controls while making this integration concrete.

Document the minimum final changes and why each is needed. Ensure the acceptance checks run on the exact final netlist, SDC, parasitics and GDS produced by that integrated flow. Update stale project status only to what this final evidence establishes.

## 7. Fixed contract and completion gates

Preserve 20 ns/50 MHz, 8x4 boundary and all signal-pin geometry, both independent PIOs, instruction memories/FIFOs, ISA/register map, divider-1 retirement, host nibble acceptance edges, simultaneous host/core operation priorities, IMEM reset-edge retention, dynamic ena freeze/resume, and reset behavior.

Preserve actual I/O budgets, uncertainty, derates, loads, pinned PDK/models and all required corners. Do not achieve a pass by slowing the clock, reducing capabilities, weakening limits, dropping corners/paths, modifying library data, disabling checkers, or turning diagnostic reset/host case analysis into production exceptions. Supported optimization configuration changes are allowed; acceptance requirements stay fixed.

The three required corners are:

- `nom_slow_1p08V_125C`
- `nom_typ_1p20V_25C`
- `nom_fast_1p32V_m40C`

Run the unchanged `tools/timing/check_signoff.py` on the final post-route state. It requires finite nonnegative setup/hold WS; zero setup/hold TNS and violation counts; zero slew, capacitance, fanout and filtered annotation violations; zero inferred latches, unmapped instances and synthesis consistency errors. Report achieved margin, especially fast hold, without treating a barely positive value as comfortable. A reproducibility tolerance is not permission to accept negative slack.

Also require the nine-session replay matrix (three corners x baseline/operational/reset-active), matching actual post-route baseline results, complete coverage and correct final routed clock connectivity. Case-analysis modes are diagnostic; dynamic baseline acceptance remains authoritative. Existing experiments have 2,421 clock pins and no overloaded clock-buffer outputs; account for any legitimate RTL-induced count change rather than hiding it.

After a successful screen, complete full-flow GDS generation, applicable physical DRC/antenna checks, independent GDS LVS, Tiny Tapeout precheck and functional gate-level tests for that exact final artifact. Native routing DRC=0 and logical ECO equivalence do not replace GDS DRC/LVS. Do not claim production closure while these are pending or failed.

For RTL changes, run the normal regression and relevant exact-edge/formal/differential checks. Use `info.yaml` as the source manifest; rerun synthesis/structural checks and FPGA wrapper regressions when affected. Gate-level testing requires the documented Icarus 13 PDK-compatible environment. Read `test/README.md`; the historical upstream results-name issue was resolved by renaming a passing testcase containing `failure`, and must not be confused with a current logic failure. Tooling tests verify tooling, not silicon timing.

## 8. Runtime and existing assets

Use pinned WSL distro `Ubuntu-24.04`. WSL repository:
`/mnt/c/Users/shane/Projects/JaneStreet-protocol-emulator-ASIC-competition`.

EDA working directory: `/home/shane/eda/librelane-3.1.0.dev3`.
Use `/nix/var/nix/profiles/default/bin/nix develop --offline --command ...`.
PDK: `/home/shane/eda/pdk-2bbec755`.
Original archive: `/home/shane/eda/timing-20261024/current`.

Existing large physical artifacts:

- `test/sim_build/clock_factors/clock_split8-01/`
- `test/sim_build/data_eco_20261027/input/` (shared prepared post-antenna input)
- `test/sim_build/data_eco_20261027/`
- `test/sim_build/data_integration_20261027/`
- `test/sim_build/data_critical_path_20261027/`

Verify availability and hashes before using them. Use existing `tools/timing/` preparation, trial, collection, audit and comparison tools where applicable; their reports include reproduction commands. For long jobs use a durable detached launcher and recorded process/status state. Avoid restarting a parent WSL invocation that owns active workers. Keep resource use bounded; prior matched runs used eight OpenROAD threads per worker.

Useful initial checks inside the working environment:

```sh
git status --short
git log -5 --oneline
python3 -m unittest discover -s test -p test_timing_tools.py -v
sha256sum -c docs/timing/20261027-data-critical-path/SHA256SUMS
sha256sum -c docs/timing/20261027-data-integration/SHA256SUMS
```

Do not blindly rerun completed suites. Gather missing cone/hold/electrical evidence first, then run only justified new comparisons.

## 9. Final handoff

Deliver:

1. A precise root-cause explanation separating measured facts, causal inference and unresolved uncertainty, including why previous local repairs failed globally.
2. The implemented production changes, source-level mapping of repaired cones and exact reproduction commands.
3. Before/after all-corner metrics, hold margins, endpoint/electrical inventory and annotation/connectivity evidence, using matched comparisons.
4. Functional, structural, physical, precheck and gate-level results tied to the final artifact hashes. Distinguish checks passed, failed and not run.
5. A candid readiness decision: either a reproducible qualified 50 MHz baseline suitable for further architecture work, or the exact remaining blockers and the smallest evidence-supported next action.

Proceed autonomously with authorized diagnosis, fixes and verification. Do not stop merely to ask whether to continue routine repair work. If closure is not achieved, say so directly; do not describe a sub-picosecond numerical gain, one passing endpoint, a waived error, or another unintegrated physical screen as completion.
