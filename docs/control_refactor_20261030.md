# Isolated host-control and hold increments

Status, updated October 31 (America/Phoenix): **both increments fully qualified
locally; the exact tested physical recipe is active**. Four transparent buffers
were added beyond the existing repair: two isolate host-control load groups,
and two delay the verified ISR[6]/ISR[3] D boundaries. ASIC RTL, register/cycle
boundaries, manifest, constraints and native physical flow remain unchanged.
FPGA build/programming files are untouched.

Each increment passes the complete normal production flow, all required
extracted timing/electrical checks, nine independent STA sessions, physical
checks, actual-GDS LVS, all nine Tiny Tapeout prechecks and all 39 exact-netlist
gate tests. Each improves all six required worst-corner margins against its
fully qualified immediate parent. Final production results are:

| Corner | Setup ns | Hold ns | Setup consumed vs CI baseline ns | Hold consumed vs CI baseline ns |
| --- | ---: | ---: | ---: | ---: |
| Slow | 0.393477262 | 0.474639452 | -0.090043531 | -0.101519351 |
| Typical | 6.138193239 | 0.205702239 | -0.017206681 | -0.059951934 |
| Fast | 9.624813219 | 0.048140215 | -0.108351553 | -0.035328796 |

Negative consumed values mean increased margin. Local costs also exist:
ISR[6] slow setup consumes **177.634 ps across both increments**, retaining
2.845521 ns; the second increment consumes **2.664 ps of ISR[7] fast hold**
against its immediate parent. The complete local budgets appear below. These
results preserve the six required corner minima and do not imply that every
individual path improves. The remaining worst setup/hold margins are still narrow.

The [activation receipt](timing/20261030-control-refactor/activation.json) binds
the qualified artifacts, both passing increments, 60 source/configuration
comparisons, pinned timing-input hashes and the exact active recipe. The
original recipe is preserved beside it. This is a **local qualification**;
the existing GitHub CI baseline remains `bb7c5ef`, with no new CI run claimed.

## Parent and fixed contract

The physical parent is source `bb7c5ef3c54a7ae2733bbfae82aa940016375007`,
qualified by Actions run `40938542430`. Its archived extracted STA state SHA256
is `af8ced2439790ea47598651acacfbb0eb9d9848a858972a1124358e074ec0ae5`.
The experiment freezes source files with `git archive` from that commit.

The 20 ns clock, all required corners, I/O budgets, uncertainties, derates,
loads, geometry, ISA, host nibble acceptance/commit edges, reset/enable and
instruction retirement cycles remain fixed. Production uses the same pinned
LibreLane/OpenROAD/PDK/support tools. Every final candidate must pass the
ordinary complete `PIOClosure` flow, strict extracted/electrical checks,
independent replay/coverage, physical checks, GDS LVS, precheck and all 39 gate
tests. The additional parent comparison rejects loss of either required
worst-corner setup/hold margin, including a loss that leaves positive slack.

## Affected cones and register boundaries

The qualified slow setup path begins at live `HOST_RD` (`ui_in[5]`), proceeds
through host acceptance/control, engine updates and output selection, and ends
at `_31995_/D`, engine-1 `pins[8]` (verified by its actual netlist Q connection).
The existing `_17710_` NAND3 drives eight loads and contributes
1.372590 ns on the measured slow path at 0.092676 pF. Its destinations occupy
two physical groups; the six loads east of x=550 um include the critical
`_17711_/C` branch. Register/host cycle boundaries are unchanged.

The qualified fast hold minimum is engine-1 ISR[6] feedback: `_32071_/Q`, an
existing buffer, `_30252_`, `_30253_`, and `_32071_/D`. The terminal D driver has
one load. An added D-path buffer delays all paths into that register, so its
setup cost must be measured as well as the short-path improvement.

### Source-level control and latency review

`pio_subsystem.sv` already qualifies byte intent per engine, decodes each
bank's staged-word destination locally, and combines only qualified group
commands. Ownership writes likewise combine qualified local data rather than
muxing a complete staged word through engine selection again. The common
discovery/readback selectors feed each bank's snapshot/read mux; they do not
enter the instruction operand mux. Duplicating this existing local decode at
RTL is therefore not assumed to remove the measured path.

The read-to-retirement dependency has a required simultaneous-operation
meaning: host first-nibble read acceptance can pop RX on that same edge;
`rx_room = !rx_full || (host_rx_pop && !rx_empty)` lets an executing PUSH use
the released FIFO slot. Registering that event would change a full-FIFO PUSH's
stall/retire cycle and potentially its pin update. Removing this dependency
is not a cycle-preserving readback isolation. The candidate instead isolates
the physical load groups on the measured snapshot-read control net, preserving
the exact RX pop/room expression and retirement boundary. Payload readback
and extension selection remain outside the operand-selection path.

The core's existing sequential priority also remains explicit: synchronous
reset dominates; abort releases directions and stops; stop freezes execution;
start restarts architectural state; resume precedes ordinary execution.
Host configuration, firmware IRQ updates and side-set overlap retain their
existing ordering. Replacing these priority chains with parallel muxes would
need a separate equivalence argument for simultaneous operations. No such
unmeasured RTL rewrite or pipeline register is part of these two increments.

The earlier redundant host-class predecode is a useful counterexample: its
formal and differential checks passed but its extracted implementation
regressed. Its retained [experiment and rollback](timing_closure_repairs_20261026.md)
inform this choice; its historical metrics are not used as the current parent.
The tested replication and local-buffer hypotheses below compare physical
load isolation while leaving all those priority and register boundaries intact.

The independent hypotheses are bound to the actual reference graph:

1. **Hold:** retain the existing final fanout repair and add one transparent
   buffer at the ISR[6] D-driver boundary.
2. **Host drive:** a proposed stronger NAND3 was rejected before routing:
   `sg13cmos5l_nand3_2` is absent from the pinned library. This is an availability
   failure, not a measured timing regression. Subsequent production freezing
   checks all required cell models in every required corner before launch.
3. **Host replication:** retain that repair and replicate the identical NAND3
   near the six eastern loads. All replica inputs connect to the original
   inputs, and only the declared existing load partition can move. No new
   storage, clock sink, host event or instruction latency is introduced.
4. **Host buffering:** add two available transparent buffers, with at most four
   existing loads per buffer and placement near each load group's centroid.
   This tests local drive isolation separately from gate replication.

The source gate resolves uniquely by the existing pin-labelled connectivity
fingerprint mechanism. Reference numerical names are evidence, not unverified
production lookups. Replica loads are selected from the measured current
source's attached pins by the declared physical partition, then independently
checked against the original graph. Clock loads, foreign connections, changed
functions/inputs and unexpected mutations are rejected.

Contracts and reference provenance: [evidence directory](timing/20261030-control-refactor/).

## Verification completed so far

- All 39 RTL tests pass on frozen qualified sources, with zero failures/skips.
- The existing cycle differential passes 27,391 cycles, including reset-edge
  IMEM retention. FIFO, frontend, host, pad and simultaneous subsystem tests pass.
- All 58 existing timing-tool tests, eight adversarial replica-audit tests and
  eight immutable-parent/worker/retry guard tests pass.
- The real-database replica audit passes exact function/input, load partition,
  original signal connectivity and unchanged clock-topology checks.
- The unchanged diagnostic tail reproduces **all six** parent setup/hold margins
  exactly. All strict extracted/electrical metrics pass. This is a matched
  control screen, not a new production qualification.
- The fresh normal control also reproduces the archived pre-final-repair ODB
  **byte for byte**, SHA256
  `0a0da10821c774b55784b5327dfc14f440432683351f226600cb1c4672a595e9`.
  This independently checks that the clean production prefix has not drifted.

| Corner | Parent setup ns | Parent hold ns | Control setup consumed ns | Control hold consumed ns |
| --- | ---: | ---: | ---: | ---: |
| Slow, 1.08 V / 125 C | 0.303433731 | 0.373120101 | 0 | 0 |
| Typical, 1.20 V / 25 C | 6.120986558 | 0.145750305 | 0 | 0 |
| Fast, 1.32 V / -40 C | 9.516461666 | 0.012811419 | 0 | 0 |

The hold screen passes all strict extracted/electrical checks, zero native
routing DRC/antenna counts and the unchanged no-regression comparison:

| Corner | Hold-screen setup ns | Hold-screen hold ns | Setup consumed ns | Hold consumed ns |
| --- | ---: | ---: | ---: | ---: |
| Slow | 0.304009271 | 0.401619416 | -0.000575540 | -0.028499315 |
| Typical | 6.121385350 | 0.165033769 | -0.000398792 | -0.019283464 |
| Fast | 9.516728119 | 0.025731584 | -0.000266454 | -0.012920165 |

Consumed headroom is `parent - candidate`; negative values mean more margin.
The sub-picosecond setup differences are recorded without attributing them to
a deliberate setup improvement. The fast hold improvement is about 12.9 ps;
25.7 ps remains narrow. Clean normal routing and independent nine-session
replay later reproduce this result. The original qualification fails for the
report-directory setup described below; the complete retry later passes on
the unchanged artifact. The screen itself is not a qualified successor.
The independent replay of the hold screen is complete: all nine sessions agree,
coverage is complete, all 2,421 clock sinks are reached with no overloaded clock
branch, and serialized signal-contact checks pass. The new fast minimum is
ISR[3] feedback at 0.025732 ns; repaired ISR[6] feedback is 0.056837 ns.

The replication screen is **rejected**. Its setup slack is 0.212841306 ns slow,
6.059774187 ns typical and 9.501998568 ns fast. It consumes respectively
**0.090592425 / 0.061212370 / 0.014463098 ns** of setup headroom and introduces
one fanout violation in each corner. Hold improves by only
0.000263456 / 0.000146771 / 0.000076272 ns. Positive setup slack does not satisfy
either the electrical gate or the parent-margin rule.

The extracted path still starts at `ui_in[5]` and ends at `_31995_`. Replication
reduces the NAND3 output load, but the preceding `_17707_` output capacitance
increases from 0.059266 to 0.100192 pF. Its slow arc increases from 0.939948 to
1.320967 ns, outweighing the downstream arc savings. This is an observed
upstream-load cost, not evidence that the replica's logical behavior differs.
The frozen replication production candidate will not be launched from this
rejected screen.

The local-buffer screen passes strict timing/electrical checks and improves
setup in every corner, but is **rejected by the exact no-regression rule**:

| Corner | Buffer-screen setup ns | Buffer-screen hold ns | Setup consumed ns | Hold consumed ns |
| --- | ---: | ---: | ---: | ---: |
| Slow | 0.393256994 | 0.373120323 | -0.089823262 | -0.000000222 |
| Typical | 6.138030702 | 0.145750305 | -0.017044144 | 0 |
| Fast | 9.624704861 | 0.012811363 | -0.108243195 | +0.000000055511 |

The fast hold decrease is about 0.000056 ps, at numerical representation scale;
it is not presented as a meaningful physical degradation. The comparator has
no tolerance, and no tolerance is introduced to accept this candidate. The
worst slow setup now starts at host address bit 0, rather than HOST_RD, and
ends at the same register. The competing control cone remains in scope.

A combined diagnostic screen starts again from the original qualified-parent
pre-final-repair state. It retains ISR[6] buffering, adds the measured host
buffers, and buffers the newly limiting ISR[3] D boundary. The register is
identified by its architectural Q-net name and its unique actual D driver,
not by an assumed register number. This screen cannot qualify a successor.
Its subsequent clean production increment uses the completed, immutable first
hold-production qualification as its parent, preserves all accepted parent
repairs, and compares all six margins against that exact parent. The launcher
test confirms an unfinished parent is refused before candidate creation.

The combined screen completes with zero strict timing/electrical violations,
zero native routing DRC/antenna counts, and no margin loss versus the original
passing parent. A separately labelled diagnostic comparison also loses no
margin versus the first hold screen; that screen is not treated as a qualified
production parent.

| Corner | Combined setup ns | Combined hold ns | Setup consumed vs qualified baseline ns | Hold consumed vs qualified baseline ns |
| --- | ---: | ---: | ---: | ---: |
| Slow | 0.393477262 | 0.474639452 | -0.090043531 | -0.101519351 |
| Typical | 6.138193239 | 0.205702239 | -0.017206681 | -0.059951934 |
| Fast | 9.624813219 | 0.048140215 | -0.108351553 | -0.035328796 |

This uses four new transparent buffers beyond the existing three-buffer final
fanout repair: one at ISR[6], two for host-control load groups, and one at
ISR[3]. The mutation audit preserves all original signal connections and clock
topology. Independent replay is complete: all nine sessions agree, constraint
coverage and serialized wire contacts are clean, all 43 signal-pin geometries
are unchanged, and all 2,421 clock sinks are covered with zero overloaded clock
branches. ISR[7] feedback is now the fast minimum at 0.048140 ns.
Both subsequent clean production increments complete qualification as recorded
below; diagnostic screens are never used as their passing physical parents.

## Retained runs and infrastructure

All generated runs live under ignored `test/sim_build/` with unique names;
failed and superseded attempts remain intact. No existing run is reused.

- `control_refactor_control_20261030_01`: launcher rejected before physical
  implementation because its requested run directory did not exist.
- `control_refactor_control_20261030_02`: fresh full production control build;
  it retains the initial parent-comparator wrapper's noncanonical parent path.
  The path is corrected for subsequent candidates, with an actual comparator
  self-check before launch. Extracted metrics pass and the common-prefix ODB is
  identical; the old wrapper rejects the run before GDS qualification. Frozen
  inputs remain unchanged. It is an infrastructure failure, not a qualified build.
- `control_refactor_screen_control_20261030_01`: rejected before routing because
  the diagnostic tail loaded an incomplete config schema; corrected in `_02`.
- `control_refactor_screen_control_20261030_02`: completed, exact numeric
  reproduction of the qualified parent.
- `control_refactor_clone_audit_20261030_01`: mutation/audit/legalization only;
  passed, without an extracted timing claim.
- `control_refactor_screen_hold_20261030_01`: completed hold diagnostic route;
  all strict extracted/electrical and parent-margin checks pass.
- `control_refactor_screen_clone_20261030_01`: completed; rejected for setup
  margin loss and a new fanout violation in all corners.
- `control_refactor_screen_drive_20261030_01`: rejected before routing because
  the proposed NAND3 strength is absent.
- `control_refactor_screen_buffer_20261030_01`: completed; strict electrical and
  timing checks pass, exact no-regression comparison rejects the tiny fast-hold decrease.
- `control_refactor_screen_combined_20261030_01`: completed; strict extracted
  and parent-margin checks, nine-session replay and all route audits pass.
- `control_refactor_hold_production_20261030_01`: native flow passes; the original
  qualification fails at report creation. A complete same-artifact retry later
  qualifies it; the original failure remains intact.
- `control_refactor_clone_production_20261030_01`: frozen candidate and passing
  comparator self-check; never launched because its replication screen is rejected.

The Nix gate simulator needs the already-pinned expat shared library when it
embeds the existing system-Python cocotb environment. This is a simulation-runtime
dependency, not a change to RTL, models, constraints or signoff acceptance.

## October 30 interruption checkpoint (historical)

The first clean hold production run completes the normal native flow. Its
extracted margins exactly reproduce the hold screen, all electrical/coverage
and clock checks pass, Magic DRC is zero, actual-GDS LVS passes, and final
timing-view identity/pin geometry checks pass. Its qualification attempt is
nevertheless **failed**, and all frozen inputs remain unchanged.

The local qualification wrapper omitted `precheck/reports/`. The first precheck
pin-label test had already failed when KLayout could not save its report there.
Creating the output directory later allowed the other checks to write their
results, but does not erase that earlier failure. The final precheck report
shows **SG13CMOS5L DRC and the other seven subsequent checks passing**, with only
the initial pin-label check failed for the report-path error. The 39 gate tests
are not reached. No failing check is waived or reclassified as passing.

The launcher now creates the reports directory before invoking precheck. A
fresh wrapper snapshot passes syntax and parent-comparator self-checks; its
receipt is `timing/20261030-control-refactor/wrapper_validation.json`. The
updated reference preparer also reproduces the tested hold contract exactly
and refuses to generate the unavailable NAND3-strength contract.

The first dependency queue was stopped before correcting the launcher. The
second queue, `test/sim_build/control_refactor_queue_20261030_02/`, correctly
records `parent_rejected` with `candidate_created: false`; an explicit STOP
marker also prevents further dispatch after interruption. The combined normal
production directory has not been created. All attempts and logs are retained.

Required next work is a complete qualification retry of the unchanged first
hold artifact with the corrected output-directory setup, including all precheck
checks and all 39 gate tests. Its passing-parent receipt must identify that
actual successful qualification without overwriting the failed attempt. Only
then may the combined increment start a fresh clean normal production build
against that fully qualified parent. The immutable-parent, repair-preservation
and exact no-regression guards remain mandatory.

Only after both normal production increments pass all required checks may the
tested `buffer_hold.json` recipe replace the active final-fanout contract.
Activation must verify that the active submitted RTL, manifest and physical
configuration still match the qualified candidate. The qualification report
and project status must distinguish the new local qualification from the older
GitHub CI baseline; no new CI run is claimed. FPGA sources and images stay
unchanged.

## October 31 continuation and completion

Complete qualification is retried successfully at
`test/sim_build/control_refactor_hold_requalification_20261031_01/` on the exact
unchanged native production output. The original failed job, precheck and logs
remain intact. The retry's GDS, netlist, LEF, SDC, SPEF and native evidence hashes
all match the original attempt. No rerouting, source change, constraint change
or checker waiver is involved. The corrected checker differs from the frozen
one only by creating its reports directory before precheck. The shared helper
also retains the host-tool/example dependencies required by the gate tests.

The formerly failing pin-label report now exists and contains zero violations.
All nine precheck checks have now passed, including the full SG13CMOS5L
DRC (the retained first attempt took 2,945.64 seconds for that check). The full
39-test gate regression subsequently passes on the same netlist, with zero
failures or skips. Sixteen new replica/parent/worker guard
tests pass, including refusal of failed retry receipts and changed original-job
or source-manifest hashes.

Only a fully successful retry may create `qualification_resume.json` beside
the original failed job. That receipt binds the original job and source
manifest, unchanged physical run and successful qualification hashes. The
parent validator requires the exact original physical view set, all physical
checks, complete precheck and all 39 exact-netlist gate tests before accepting
it as a passing parent. The original failed verdict is never overwritten.

The one-shot continuation queue is
`test/sim_build/control_refactor_queue_20261031_01/`. It watches the retry's
completion and then calls the same immutable-parent gate before launching the
fresh combined normal production run at
`test/sim_build/control_refactor_combined_production_20261031_01/`. It stops on
any failed qualification or changed launcher, and never uses an unfinished
screen as a parent.

The first increment's retry is now **complete and locally qualified**. Its
native extracted results equal the hold-screen table above exactly; none of
the six required setup/hold margins is consumed. All nine prechecks and all
39 exact-netlist gate tests pass (890.80 seconds, zero failures/skips). The
unchanged original failed attempt is linked to the successful qualification by
`control_refactor_hold_production_20261030_01/qualification_resume.json`.
The immutable-parent validator accepts the complete receipt and every bound
source/artifact hash. Key SHA256 values are:

| Evidence | SHA256 |
| --- | --- |
| Native post-route state | `e2734950272a286da0b07ed2fb44ce857731e60b6eb14642e99dc9ddb867a7a1` |
| Final GDS | `e24a0d81c1da96b099540dbe78890222175a0e69fa1df38db9bc5afb8f6b213b` |
| Final functional netlist | `0eff5ef8b23b21632d9c1a7500326f44e2b20012036a21789615c561b1abb28b` |
| Successful qualification manifest | `0852b5a74c0d01293c4803e7476d46522d9e72c4a6220148016805149d9a462a` |

The queue has dispatched the fresh second production increment. Its frozen
parent state is the qualified first increment's actual state above, rather
than a diagnostic screen. All accepted parent repair entries are retained.
The second run has now passed extracted timing/electrical acceptance and all
six exact margin comparisons against that parent:

| Corner | Production setup ns | Production hold ns | Setup consumed vs first increment ns | Hold consumed vs first increment ns |
| --- | ---: | ---: | ---: | ---: |
| Slow | 0.393477262 | 0.474639452 | -0.089467991 | -0.073020037 |
| Typical | 6.138193239 | 0.205702239 | -0.016807889 | -0.040668470 |
| Fast | 9.624813219 | 0.048140215 | -0.108085099 | -0.022408631 |

Its native post-route state SHA256 is
`8cda1271b19e0395f15568ac628639ba6d55d0930d80f31e93b502bd3ea26074`.
The clean pre-repair ODB again matches the archived reference byte for byte.
All seven buffers in the final stage (three existing, four added) pass the
topology audit; every original signal connection and clock branch is preserved.
The nine independent STA sessions and all route audits pass. The complete native
production flow also passes: final routing DRC, Magic DRC, antenna, illegal
overlaps and all seven actual-GDS LVS error/difference fields are zero. Final
timing-view identity and pin geometry match. All nine prechecks subsequently
pass, followed by all 39 exact-netlist tests (852.67 seconds, zero failures/skips).
The second increment is fully qualified.

| Second increment native artifact | SHA256 |
| --- | --- |
| Final GDS | `9ab35bd7e65d1cac42b33505786227137b59fa95d616f15d5caa0671bd2e185c` |
| Final functional netlist | `65b0578413c1f1b8c0ce836d2efedcded21ab807d69f7fe26bdd584cbbcdfaff` |
| Nominal extracted SPEF | `4ef69bc8781213444367561a3eac4836afabd7505d680d1dbe71ef54ecf0f7fb` |
| Complete qualification manifest | `77b09143e970229294d2b10cc92d11ec6bf83625d1fe7051a336fa9b2a9d68e5` |
| Active tested recipe | `e6048d0c1a3a0c1944b444452ec645807f02c183895f9f343b99f2e41043ce2f` |

The activation preflight compares 60 active RTL, manifest, physical configuration
and tool source files with the frozen tested inputs, allowing newline
normalization. All match. The isolated production-flow difference is the extra
parent-margin rejection gate after extracted STA; it changes no native physical
operation. The same comparator exists at its ordinary active source location.
`activation_input_preflight.json` records the hashes and explicit comparison
scope. `activate_refactor.py --apply` additionally requires complete qualification
of both increments, rechecks every input and all six parent margins, backs up
the original recipe, verifies the pinned timing models and inputs, and copies
the exact tested recipe bytes. It completes successfully with `--apply` at
06:29 UTC November 1 (23:29 October 31 in America/Phoenix). Final independent
ledger validation accepts both production parents and the active implementation
with no validation errors. Qualification jobs and failed attempts remain
immutable; later activation is recorded separately.

The next implementation increment must compare against this qualified combined
parent (`8cda1271b19e0395f15568ac628639ba6d55d0930d80f31e93b502bd3ea26074`),
preserve all accepted repairs, and maintain its six required margins. A new
feature's registered boundaries must have an explicit latency contract; the
existing host RX-pop/retirement dependency and instruction cycles remain fixed.

## Local setup/hold costs at the repaired boundaries

The required no-regression gate compares the worst setup and hold margin in
each of the three required corners. All six improve in each increment. Local
endpoint slack can still be consumed, particularly when adding minimum delay.
The native path reports expose these costs separately; they are not
rounded away or described as zero headroom consumption.

The endpoint audit reads the actual qualified CI archive (its state hash must
equal the qualified parent), the first production run, and the second production
run. Each ISR register is identified independently by its architectural Q-net
in that run's actual netlist. It selects the native worst data-pin path at that
register and retains its complete report. This is a three-register diagnostic,
not a claim that every individual path improves. Each source report contains
1,000 selected paths; all three registers occur in all 18 reports used here.
Reports have six decimal places
in ns; the exact production corner comparison retains full numeric precision.

Positive numbers below mean local slack consumed, in **ps**, versus the
increment's immediate parent:

| Increment | Register / margin | Slow | Typical | Fast |
| --- | --- | ---: | ---: | ---: |
| First hold | ISR[6] setup | +171.969 | +107.919 | +52.606 |
| Combined | ISR[3] setup | -54.490 | -3.843 | -66.108 |
| Combined | ISR[6] setup | +5.665 | +3.650 | -107.771 |
| Combined | ISR[6] hold | +0.167 | +0.093 | +0.047 |
| Combined | ISR[7] hold | +7.086 | +4.190 | +2.664 |

After the first fix, ISR[6] slow setup retains 2.851186 ns; after the combined
increment it retains 2.845521 ns. Host-control optimization more than offsets
the new ISR[3] buffer's setup cost at that endpoint in all three corners. The
unbuffered competing ISR[7] feedback path becomes the combined global hold
minimum, retaining 0.048140215 ns in the fast corner. Its 2.664 ps local loss
against the first increment is real even though the required global fast-hold
minimum improves by 22.408631 ps. These are measured net effects, not an assumed
standalone cell-delay budget.

The [local endpoint manifest](timing/20261030-control-refactor/local-endpoints/manifest.json)
contains all three registers' setup/hold values in every corner, source hashes
and both increment comparisons. Complete selected path reports and the runner
are retained beside it. These diagnostics change no constraint, exception,
library, acceptance gate or production artifact.
