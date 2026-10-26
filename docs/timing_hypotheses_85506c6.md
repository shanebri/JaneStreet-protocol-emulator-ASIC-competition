# Timing diagnosis and test-only preparation

Date: 2026-10-23 (America/Phoenix). Design revision:
`85506c60783641f7f0a14e13a7e099c9a9b9603f`.

Scope: tests and hypotheses only. No RTL, production constraints, configuration,
allocation, workflow gates or physical optimization was changed. The pre-existing
untracked `io_timing_failure_assessment.md` and `timing/85506c6/` evidence were
preserved. This report independently checks their archived evidence; it does not
represent a fresh routed experiment or formal equivalence proof.

## Tests implemented

- `test/frontend_timing_tb.sv`: standalone PC/fetch contract test. Exercises all
  32 restart addresses, all 32 branch targets from each restart, independent host
  reads, restart priority, freeze, wrap, natural overflow, same-address write/read
  visibility, and program retention across PC reset. Checks fetched data immediately
  after the accepted edge, so an added fetch pipeline would fail this contract.
  Integrated into `test/run.py`.
- Six new tests in `test/test_timing_tools.py`: replay matrix/provenance,
  historical-reference and candidate endpoint selection, stale output rejection,
  missing-library rejection, process/log errors, and reference mismatch rejection.
  These use a fake STA process to test orchestration; their slack values are
  fixtures, not timing measurements. Total timing-tool tests: 14.
- Existing differential regression remains the broader architectural check:
  both engines, PC, scratch/shift state, FIFO storage and pointers, retained IMEM,
  staged host state, IRQs, pads, reset and disable/resume, against frozen 37c74dc.
  It passed 27,391 cycles. Finite simulation is not exhaustive equivalence.

## Validation performed

`./test/run.ps1` (calls `python test/run.py`) passed: 14 timing-tool tests,
3 Python host tests, FIFO/frontend/host/pad/subsystem standalone units,
27,391 differential cycles and all 39 cocotb tests, with no skips.
`./fpga/test.ps1`, `./fpga/test_spi.ps1` and `./fpga/test_i2c.ps1` all passed;
SPI covered 512 transactions. Icarus 12.0 and cocotb 2.0.1 were used; the
successful regression reports its embedded Python as 3.12.4. The sandbox's
Python command reports 3.12.14, so the runtime context is recorded explicitly.

Logs are `test/sim_build/timing_hypothesis_regression_unrestricted.log` and
`timing_hypothesis_{fpga,spi,i2c}.log` in the same directory. The initial sandbox
attempt encountered temporary-directory access errors and stalled in existing
asyncio host tests; the complete rerun outside the sandbox passed. This was an
execution-environment issue, not a waived test. `git diff --check` passed.
No new synthesis, formal, lint or gate-level run is claimed for this test-only
patch; design RTL is unchanged.

## Archived physical result, rechecked

Source: run 39707891759, artifact 12401887733. Full archive is in
`test/sim_build/gds_failure_85506c6/GDS_logs.zip`; its SHA-256 was revalidated:
`cadefda210b3853e4c90882acfd9b80a17bed253aab08dc146f21a114952a3c4`.
All nine files in `docs/timing/85506c6/SHA256SUMS.txt` matched their hashes.
Running `tools/timing/check_signoff.py` against the actual archived
`55-openroad-stapostpnr/state_out.json` reproduced rejection, with eight failed
metric checks. See `test/sim_build/timing_hypothesis_signoff.log`.

| Routed metric | Historical 37c74dc | Current 85506c6 |
| --- | ---: | ---: |
| Slow setup worst slack (ns) | -5.885337 | -6.809803 |
| Typical setup worst slack (ns) | 2.427592 | 2.992410 |
| Fast setup worst slack (ns) | 7.069545 | 7.564806 |
| Slow setup TNS (ns) | -2071.482472 | -979.921111 |
| Slow setup violating endpoints | 821 | 616 |
| Slow/typical/fast hold worst slack (ns) | .646020 / .301122 / .112777 | .666255 / .314691 / .122530 |
| Hold TNS / endpoint violations (all corners) | 0 / 0 | 0 / 0 |
| Slew violations, slow/typical/fast | 19 / 0 / 0 | 55 / 4 / 0 |
| Cap violations per corner | 1 | 0 |
| Fanout violations per corner | 178 | 183 |
| Standard cell area (um2) | 369174 | 369414 |

Current standard-cell utilization is 30.5762%; reported core area is 1,208,170
um2. Typical/fast setup TNS and violating endpoint counts are zero. Filtered
unannotated-net counts are zero in every corner. Gate-level testing and precheck
were skipped by the failed GDS workflow, so they remain unverified for this run.

The actual saved SDC specifies 20 ns, propagated clock, 4 ns input/output delays,
0.25 ns uncertainty and 0.15 ns clock transition; the archived report records
0.95/1.05 derates and 0.006 pF output load. No new exception is proposed.
Required analyzed corners remain nominal-RC slow 1.08 V/125 C, typical
1.20 V/25 C and fast 1.32 V/-40 C.

## Current path diagnosis

The [worst slow path](timing/85506c6/worst_slow_setup.rpt) starts at
`_33835_/Q` falling and ends at `_33839_/D` rising. The archived
[mapping](timing/85506c6/register_mapping.json) identifies engine 1 synthesized
IMEM read-address state bits 0 and 4. Arrival is 26.707644 ns and required time
19.897840 ns. This is a register-to-register feedback path, with no external
input delay in its data budget.

Counting the printed combinational output arcs after launch Q gives 47 gates:
17 buffers (8.783121 ns total cell delay), 30 other cells (15.954654 ns).
The remaining Q-to-D incremental net delay is approximately 0.412387 ns;
launch Q arrival is 1.557068 ns. Cell delay includes loading and input-slew
effects, so a small explicit net-delay fraction does not exonerate placement.
Capture insertion is 1.098352 ns, uncertainty -0.25 ns, reconvergence correction
+0.117457 ns, and setup requirement -1.067971 ns.

The path passes through address distribution, NAND/AOI/OAI logic, muxes and
control feedback. In particular `_23246_/Y` (`sg13cmos5l_nor4_1`) has only one
logical load but 0.178745 pF capacitance, 3.561205 ns cell delay and 4.579258 ns
output transition. Capture transition is 4.583533 ns against a 2.507400 ns limit.
This is direct evidence for drive/load repair, not proof that repairing that
single net recovers the entire 6.81 ns deficit.

Of 616 failing endpoint winners, 588 launch from mapped IMEM-address state and
28 from `ui_in[2]` (worst -1.538261 ns). None of these winners launches from
reset. The earlier local-control change therefore changed the dominant reported
bottleneck. It also reduced TNS and endpoint count while worsening WNS and slew.
Winner-only reports cannot establish whether internal violations were previously
hidden by reset, whether every reset path improved, or whether synthesis merged
local control back together. Restricted before/after STA is still required.
There is no sufficient measured basis here to change the shifter.

## Ranked repair hypotheses (not implemented)

### 1. Repair weak drivers using routed load estimates — physical

Propose an isolated trial of `RUN_POST_GRT_DESIGN_REPAIR=true`; leave RTL and
all other settings unchanged. Both post-GRT electrical and timing repair are
currently false in resolved configuration. The loaded NOR arc above and the
55/4 slow/typical slew counts are the evidence. Buffer insertion, sizing and
placement can reduce the driver's effective load and improve downstream setup.

Tradeoff: more buffer area and upstream pin load; total area/delay benefit is
unknown until routing. New critical paths may appear upstream or at other
endpoints. Faster paths can reduce fast hold margin (currently only 0.122530 ns
worst case). Functional latency should be unchanged, but gate-level regression,
connectivity/equivalence, DRC/LVS and all-corner extracted timing are required.
Confidence: high that this targets an observed electrical defect; medium that
it improves WNS; low that it alone closes timing. Do not simultaneously enable
post-GRT timing repair in this first trial.

### 2. Reduce clock-leaf fanout — physical, independent acceptance blocker

Propose a separate CTS sink-clustering trial against the effective fanout limit
of eight. Archived electrical reports classify 174 of 183 violations as clock
buffer outputs, with leaf fanouts as high as 17. The worst path itself has launch
and capture leaf fanouts 14 and 13. Changing host decode cannot repair this tree.

Tradeoff: extra clock buffers, clock power and area; potentially different skew
and insertion delay. New hold/setup problems can occur across all clocked state.
Verify every final leaf, slew/cap, clock coverage and all-corner setup/hold, then
gate-level tests. Clustering size alone does not guarantee final fanout.
Confidence: high for root-cause classification; medium for a particular tuning
value. Tune one parameter per trial, without weakening the fanout limit.

### 3. Shorten fetch-to-PC control feedback — RTL, conditional on cone mapping

The exact RTL boundaries are `instruction_fetch.words[current_pc]`, instruction
selection/decode and `retire`/`branch` in `protocol_core.sv`, then restart,
advance, branch and wrap selection in `frontend/pc.sv`. Mapped evidence includes
the 47-gate path, `_18753_` mux4 followed by mux2 cells `_18754_`/`_18872_`, and
the terminal NOR chain. The register mapping does not establish which source
expression owns each intervening gate; that attribution must precede an edit.

Propose parallel local next-PC candidate calculation with localized qualification
of retirement/branch, preserving the final priority and existing single-edge
fetch behavior. Duplicate only the measured high-fanout control cone if mapping
supports it. Do not add a fetch stage or change instruction-memory latency.
Tradeoff: duplicated decode/mux area and input fanout; synthesis may merge it
again. New critical paths may move to branch targets, EXEC selection or other
architectural register enables. Hazards include restart-versus-stop priority,
stall/delay, injected EXEC PC behavior, wrap and reset-edge IMEM retention.
Require the new frontend test, full differential and protocol suites, mapped
cone inspection, equivalence and a controlled physical A/B run.
Confidence: medium that the feedback cone matters, lower for this specific RTL
repair until individual gates are attributed. This is not the first experiment.

## Recommended next experiment and evidence still missing

First recover targeted baseline/current STA in the matching environment; then
seek approval for hypothesis 1 as the smallest defensible change surface. Keep
20 ns, 8x4, all corners and strict acceptance fixed. Compare setup/hold WS/TNS/
counts, electrical counts, annotation coverage, area and paths after routing.
A partial improvement must not be labeled closure.

Existing replay supplies baseline (unconstrained reset transitions) and
reset-inactive diagnostic sessions, register-only and per-port paths. It does
not supply a reset-held-active session; baseline is not synonymous with
reset-active. Reset-held-active analysis and reset-to-OE checks remain explicit
follow-up requirements. Operational case analysis is not production signoff.

The Windows host has no `sta`, OpenROAD or Verilator on PATH and WSL is not
installed. The current SPEF exists in the ZIP but was not extracted by the prior
assessment. No fresh STA or physical run was attempted. The archive contains
block timing models and temporary Liberty files, but the six original PDK
stdcell/IO Liberty models and exact PDK revision have not been established.
Prior evidence records LibreLane 3.1.0.dev3 and Yosys 0.66, commit
`86f2ddebce7e98ce7cacc27e8a5c14cb53b51b51`; exact STA/PDK identity still needs
recovery from the matching runner environment. Do not substitute the generated
top-level block Liberty for the cell libraries.

Verified candidate hashes:

- Fill-insertion netlist: `617e6f1a1a34082d427d59215903d37e2041f4a8b433d6dc5bd7f456b2f7fc1b`
- Nominal extracted SPEF: `47ddb3623a2110b3e65567fe9580e29b2a78e962b43eb01d97e9e20b11bb325c`
- Final SDC: `7088ce29adb0f7213b0f3ed4b76177f104819061b87b32bf4f166ff50e055d59`

To reproduce diagnostic STA, extract the full archives and obtain matching
OpenSTA and original PDK libraries, then run `tools/timing/replay.py --run
<extracted-run> --pdk-root <matching-pdk> --out <new-report-directory>` for the
candidate and separately with `--reference` for 37c74dc. Preserve the manifests
and review coverage, reset, per-port, register and electrical reports. These
commands do not perform place-and-route or qualify physical repairs.

Status: the existing candidate is a failed physical experiment with mixed
improvements; no new optimization or verified timing closure is claimed.
