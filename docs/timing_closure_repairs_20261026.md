# Connectivity, electrical repair and conditional host-decode experiments

Date: 2026-10-26 (America/Los_Angeles). Parent: `12b0f35`.
Branch: `codex/timing-connectivity-electrical`. Status: experiments complete;
no timing closure or production optimization accepted.

## Scope

Resolve the three-view placement candidate's live-input parasitic gap, then
test clock/data electrical repairs separately on a trustworthy extracted
baseline. Reassess the actual host-input path before any conditional RTL
change. Keep 20 ns, 8x4, both engines, one-cycle retirement, exact host edges,
all required corners, reset/enable semantics and every acceptance gate fixed.
Production configuration, constraints and CI gates are not edited.

The source candidate is
`test/sim_build/implementation/placement-corners-01`: reported slow setup WS
-1.440861693 ns, TNS -22.343167948 ns, 33 failing endpoints, 27 slow slew
violations, 178 fanout violations/corner, one filtered unannotated input net.
Its setup values remain unqualified until parasitic coverage is complete.

## 1. Connectivity diagnosis

Independent GDS-based LVS completed with `MAGIC_EXT_USE_GDS=true`,
`MAGIC_EXT_UNIQUE=all`, no label-based merging shortcut, zero illegal overlaps
and zero LVS differences/errors. Netgen reports **Circuits match uniquely**:
25,071 devices and 25,004 nets in each circuit. This is an actual GDS routing
connectivity check, not the earlier check for pins merely having wires.
It does not replace full Magic DRC/Tiny Tapeout qualification.

An independent OpenDB rectangle/via/pin contact graph of `uio_in[2]` also finds
one connected component and no disconnected pins. The graph uses actual layer
widths, pin geometry/orientations and DEF patch rectangles. Its limited scope
is declared in the output; GDS LVS is the independent whole-design evidence.

The four sinks disconnected in the extracted resistance graph are physically
connected. This identifies an extraction representation problem, rather than
evidence of a GDS routing open. No live net is excluded from coverage.

### Controlled extraction/import trials

| Trial | Only change | Slow setup WS (ns) | Filtered gaps/corner | Decision |
| --- | --- | ---: | ---: | --- |
| `extract-control-01` | None; same DEF/rules | -1.440861693 | 1 | Reproduced defect |
| `extract-no-merge-01` | Disable via/wire resistance merging | -1.440861693 | 1 | Reject; gap remains |
| `extract-odb-02` | Read unchanged ODB instead of DEF | -1.440861693 | 1 | Reject; gap remains |
| `extract-ordered-01` | Native wire ordering, then ODB extraction | -1.440861693 | 1 | Reject; gap remains |
| `extract-fine-01` | `-max_res 0` resistance segmentation | -1.441769411 | 1 | Reject; gap remains |
| `route_control-01` | Original DRT seed 42 | -1.440861693 | 1 | Reproduced defect |
| `route_seed43-01` | Only DRT seed 43 | -1.440861693 | 1 | Reject; no measured benefit |

The original RC rules and Liberty models remain unchanged. Finer segmentation
actually generated more resistance nodes (`max_merge_res 0.0`) but did not
restore the missing branch. Neither encoding normalization nor a new seed is
silently treated as a fix. `extract-odb-01` failed before extraction due to a
wrapper setup error (no STA corners defined); its corrected retry uses direct
ODB loading and is recorded separately as `extract-odb-02`.

A fresh global-routing control and a single-parameter capacity trial completed
from the same pre-global-route state. The candidate changes only
`GRT_ADJUSTMENT` from 0.30 to 0.25, the coarse resource-estimation reduction.
Actual routing layers, physical DRC, extraction rules, clock, I/O budgets and
electrical acceptance limits remain fixed. This tests a different physical
topology without changing models or masking annotation failures.

The 0.30 control reproduces the original gap. The 0.25 candidate has **zero
filtered annotation gaps in all three corners**, slow WS -0.981842191 ns,
TNS -13.117230340 ns and 19 failing setup endpoints. Slow slew count is 30,
fanout count 172/corner, capacitance count zero, and all-corner hold passes.
Native routing DRC and antenna counts are zero. Independent GDS LVS on this
exact new route also passes with zero errors and a unique circuit match.
The LVS proof manifest records the exact post-route state SHA256; the clock
runner refuses incomplete coverage or a proof for a different source state.

This establishes a coverage-clean **experimental baseline**, not timing closure.
The incomplete original annotation prevents treating its numerical difference
as a fully qualified timing improvement. No claim is made to have repaired the
underlying OpenRCX algorithm; a different routed topology avoids this defect.

## 2. Independent electrical experiments

The clock pair starts from the same saved post-placement/pre-CTS state, with
GRT 0.25 in both runs. The control executes the identical additional post-CTS
legalization/export step. The candidate uses sink cluster size 8 and the
existing deterministic branch splitter, with at most eight clock sinks per
buffer immediately after repair. Downstream hold/setup repair is retained.

| Trial | Slow WS (ns) | Slow TNS (ns) | Setup endpoints | Slow slew | Fanout/corner | Filtered gaps/corner |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `clock_control-01` | -0.981842191 | -13.117230340 | 19 | 30 | 172 | 0 |
| `clock_cap8-01` | -1.591100630 | -22.324372316 | 28 | 32 | 8 | 0 |

Both have zero capacitance violations and zero hold violations at every
corner. The clock recipe eliminates the clock-buffer fanout failures; eight
data/input drivers still violate fanout. It worsens setup and slew, so it is
retained as an independently measured repair option, not adopted as the best
timing baseline. Both fail the unchanged strict signoff gate.

The independent data-driver pair starts from the coverage-clean route's saved
pre-global-route state. `_19177_/Y` (`sg13cmos5l_nor3_1`) is the worst extracted
slow-corner slew driver: 3.424419 ns versus the 2.507400 ns limit. The candidate
changes only this master to `sg13cmos5l_nor3_2`, with the same legalization in
the control. Upstream loading, all-corner hold/setup, global slew/cap/fanout and
annotation are measured again after routing; local slew alone is insufficient.

| Trial | Slow WS (ns) | Slow TNS (ns) | Setup endpoints | Slow slew | Fanout/corner | Filtered gaps/corner |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `driver_control-01` | -0.981842191 | -13.117230340 | 19 | 30 | 172 | 0 |
| `driver_nor3-01` | -1.032022497 | -13.538630156 | 19 | 25 | 173 | 0 |

All-corner hold passes and capacitance violations remain zero. The local slew
repair trades five fewer slow slew violations for 50 ps worse global setup,
0.421400 ns worse TNS and one additional fanout violation/corner. It is **not
adopted**. The complete 24,983-instance post-repair topology audit confirms
that exactly `_19177_` changes master, with identical connectivity and identical
PDK functional model bodies. Downstream native repairs/routing remain enabled;
their consequences are included in the extracted comparison.

## Host-path diagnostic (not production constraints)

Separate slow-corner read/write case-analysis sessions classify the original
worst path. Read mode has +0.772236 ns worst `ui_in[1]` setup; write mode retains
-1.439723 ns to `_33836_/D`. Dynamic production signoff remains unchanged.
Further address-class diagnostics distinguish direct command writes from
staged word commits: command class 0/2 has -0.234630 ns at this endpoint,
whereas staged-word class A/8 retains -1.425910 ns. These diagnostic sessions
never modify production constraints or feed acceptance checks. The clean
route's dynamic worst path still starts at `ui_in[1]` through the same initial
host-address cone (its worst endpoint changes to `_31993_`).
Repeating the class diagnostic on the **coverage-clean baseline** gives
+0.043830 ns for command class 0/2 and -0.966724 ns for staged-word class A/8
at `_31993_`. Thus the conditional RTL hypothesis remains supported after the
annotation repair, rather than depending on the incomplete original SPEF.

## 3. Conditional host acceptance experiment

The candidate captures a redundant `pending_word` class on the **existing
first-nibble edge**. Its invariant after synchronous reset is:

```text
pending_word == pending && !pending_read && pending_address == 0xA
word_write_intent == write_intent && address == 0xA
```

The specialized pulse feeds only the existing bank-selected staged-word
consumers. Generic reads, command writes, IMEM write/reset guards, instruction
retirement, nibble acceptance edges and latency are preserved. The standalone
bank module's interface remains unchanged, including its original generic
word decode, so older frozen references remain independent and usable.

`prove_host_pending.py` proves all common host outputs, **all shared adapter
state**, the redundant class invariant and exact commit-pulse equivalence by
unbounded temporal induction after the first synchronous reset. All external
inputs remain defined and unconstrained, including reset, enable, simultaneous
strobes, address changes and read data. Only the initialized marker has an
initial value; arbitrary power-up adapter state is not silently initialized.
The proof passes. Full-chip immediate-reference differential comparison also
passes all 27,391 cycles, including reset-edge IMEM retention.

Fresh control and candidate screens each start at synthesis from frozen RTL.
Both use AREA 0 mapping, timing-driven placement with all three placement views,
the identical verified 8x4 signal-pin template, GRT 0.25 and native CTS.
Neither carries a manual cell-number ECO across a newly synthesized netlist.
This separates the host hypothesis from the independent electrical repairs.
The unchanged strict gate remains authoritative.

Fresh synthesis consistency checks report zero errors in both runs. The
control has 19,349 mapped instances and 297,279.9522 um² cell area; the candidate
has 19,425 and 297,929.4696 um² (about +0.22%). A localized source change still
changes ABC mapping beyond one cell, which is why the physical comparison
starts at synthesis and evaluates global results.

The first full-regression attempt exposed a test integration error: the older
reference intentionally shares the unchanged `pio_host_bank` module, and an
added input left that reference unconnected. The bank port change was removed;
the specialized pulse is wired only inside the new subsystem. That failed
attempt is retained as `closure_rtl_regression.log`, separately from the
corrected rerun `closure_rtl_regression_02.log`. It is not recorded as a passing
verification run.

Functional verification completed successfully:

- Unbounded reset-qualified host proof and 27,391-cycle immediate-reference
  differential comparison against frozen `85506c6`.
- Full regression: 39/39 cocotb tests; FIFO, frontend, all 4,096 host address/byte
  combinations, pad combinations and subsystem simultaneous-edge tests; the
  existing 27,391-cycle differential against `37c74dc`; three host utility tests.
- Final timing-tool suite: 32 tests. Verilator lint and Yosys hierarchy/process
  consistency checks complete without errors; warning logs are retained.
- Four FPGA simulation harnesses: UART loader, I2C bridge, 512 SPI transactions
  and diagnostic UART. Windows launch attempts failed before simulation; the
  same harness source lists pass under WSL Icarus. No hardware was programmed.

These checks establish functional behavior for the candidate RTL; they do not
replace extracted electrical/timing acceptance or final gate-level checks.
The exact candidate diff is retained as
`docs/timing/20261026-closure/host_pending_word.patch` regardless of its physical
accept/reject decision.

### Extracted result and rollback

| Fresh trial | Slow WS (ns) | Slow TNS (ns) | Setup endpoints | Slow slew | Fanout/corner | Cap violations | Filtered gaps/corner |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `host_control-01` | -0.955799023 | -7.096957889 | 21 | 17 | 179 | 0 | 0 |
| `host_pending_word-01` | -2.529187598 | -152.623503933 | 270 | 9 | 181 | 2 | 0 |

Both have positive all-corner hold slack, zero final native routing DRC and
antenna violations, and complete filtered annotation. The fresh control is the
only valid matched comparator for this RTL experiment; the saved-state repair
baseline has a different implementation history.

**Reject the pending-class RTL candidate.** Global WS worsens by 1.573388575 ns,
TNS by 145.526546044 ns and the setup endpoint count by 249. Fewer slew
violations do not compensate for this regression and the new capacitance
failures. The exact five-file candidate patch was reverse-checked and reverted;
production RTL and the two candidate-specific testbench changes are restored
to parent `12b0f35`. Candidate sources remain frozen in the ignored physical
run and the reviewable patch is retained with the proof and functional logs.

This rejects the measured implementation of the hypothesis. Formal equivalence
does not predict physical timing, and caching a class does not guarantee that
ABC/placement preserves the intended shorter cone throughout the design.
The fresh control's worst path is `ui_in[2]` to `_33837_/D`; the candidate's is
`ui_in[2]` to `_32148_/D`. The new critical path and all targeted input/reset/
register paths are retained rather than assessing only the old `ui_in[1]` cone.

## Infrastructure and reproduction

`tools/timing/closure_trial.py` resumes the actual saved state for each fixed
recipe, refuses an existing output, records state/view/script hashes and keeps
execution settings separate. `closure_collect.py` creates a replay view from
the actual netlist/SDC/new SPEF, including re-extraction runs that reuse a frozen
netlist. It requires the full nine-session matrix and verifies dynamic-reset
setup/hold against actual post-route state metrics. The original strict gate
is always retained for timing screens. GDS LVS is explicitly diagnostic only.

Runs are in `test/sim_build/closure/`; launch logs are
`test/sim_build/closure_*.log`. Original physical inputs remain untouched.
Pinned tools/PDK remain those recorded in `12b0f35`; no replacement library,
relaxed timing corner, false path, clock-period change or coverage exclusion.

```sh
cd /home/shane/eda/librelane-3.1.0.dev3
nix develop --offline --command python3 <repo>/tools/timing/closure_trial.py \
  --base <repo>/test/sim_build/implementation/placement-corners-01 \
  --archive-root /home/shane/eda/timing-20261024/current \
  --pdk-root /home/shane/eda/pdk-2bbec755 \
  --trial grt_capacity25 --out <new-output-directory> --threads 8
```

## Decision and next experiment

All three requested stages were implemented and measured. The useful retained
result is a coverage-clean GRT 0.25 baseline with independent passing GDS LVS.
The clock repair solves its targeted clock fanout but costs setup; the isolated
NOR3 repair and the host class cache are rejected as global timing regressions.
All timing screens still fail the unchanged strict gate. No final full-flow
Magic DRC, Tiny Tapeout precheck, gate-level qualification or accepted GDS is
claimed for an optimization candidate.

Next, use the clean baseline to test **clock distribution with less insertion
delay/skew cost**, independently of the host RTL. The current clock experiment
shows that eliminating clock fanout is feasible but that this recipe's timing
cost is too large. A matched trial separating native clustering from branch
splitting is more informative than stacking the rejected changes. Reinspect
the fresh dynamic critical paths and large input-buffer loads before another
host rewrite; preserve the current host edges and latency throughout.

For the clock pair, use `closure_trial.py` with `--trial clock_control` or
`clock_cap8`, `--base <closure>/grt_capacity25-01`,
`--placement-base <implementation>/placement-corners-01`, and
`--lvs-proof <closure>/grt25-gds-lvs-01`. For the isolated driver pair, use
`--trial driver_control` or `driver_nor3` with that same clean base and omit
the two clock-only arguments. Each output must be new.

For fresh RTL comparison, use `closure_rtl_trial.py` with the same archive/PDK,
`--template /home/shane/eda/timing-20261024/parallel-fetch/tt_block_8x4_pgvdd.def`,
`--design-root <frozen-baseline-root>` / `<candidate-root>`, and
`--trial host_control` / `host_pending_word`. The baseline root is an unmodified
copy of `src/` and `info.yaml` at parent `12b0f35`; the runner freezes all sources
again and records their individual SHA256 values. The template fingerprint
must match all 43 signal pins and the archived 8x4 die boundary.
The candidate design root must have the retained `host_pending_word.patch`
applied; the working checkout has been restored after rejection.

Collect a completed screen with `closure_collect.py --trial <trial-directory>
--pdk-root <pdk> --out <new-evidence-directory>`. This uses the actual state
views, requires all nine STA sessions, and verifies replay timing against the
native post-route values. Compact evidence is under `docs/timing/20261026-closure/`;
large physical views remain in the ignored run directories.

Two initial collector attempts failed on SDK SPEF-key handling and an existing
empty replay-view directory; their partial outputs are retained under
`test/sim_build/closure/failed-collection-grt25*`. The corrected collector
explicitly accepts only the single nominal RC key `nom` or `nom_*`, rejects
ambiguous corner maps, and is covered by the tooling tests. These were
collection failures, not new physical experiments or passing signoff results.

The complete comparison is indexed in
[`comparison.md`](timing/20261026-closure/comparison.md). Each of its seven rows
has nine completed replay sessions with no constraint coverage issues.
`runners/` preserves the exact clock-era and final driver/fresh-RTL runner
versions; their bytes match the corresponding invocation hashes. Earlier
extraction variants are reproducible using the final recipe superset and the
saved resolved inputs/native commands. `SHA256SUMS` covers the compact evidence,
report and timing tooling. Production sources are checked byte-for-byte against
the frozen pre-experiment tree after rollback.
