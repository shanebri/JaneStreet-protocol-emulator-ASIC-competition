> Historical checkpoint or task record. Status statements and next steps below
> apply to the named revision/date. See [current project status](project_status.md)
> for the qualified dual-engine build and remaining hardware work.

# Shared acceptance cone investigation (in progress, updated October 28)

Starting checkout: `codex/timing-connectivity-electrical`, commit
`9ad7f06284be73cf8152c84cb3662c4437a0aaa8` (full identity in `timing/20261027-cone-diagnosis/starting_commit.txt`).
The pre-existing uncommitted work is preserved in `starting.patch`, with tracked
source/tool/config hashes in `starting_hashes.json`. The final route screen now
passes and its audited flow is activated; clean GDS qualification is running.
See [production status](timing_production_closure_20261028.md). This historical
experiment record does not itself declare production closure.

## Verified starting evidence

The 236 critical-path and 291 integration manifest entries verified again.
The current timing-tool suite initially passed all 49 tests; adding the new
bounded recipe gives 50 passing tests. WSL initially returned E_ACCESSDENIED
inside the sandbox; approved escalation reaches the pinned Ubuntu-24.04/Nix
environment. This is an execution-access issue, not a design failure.

The three references remain separate: old splitting-only route (-1.184760767 ns,
fast hold +0.117363345 ns); matched no-ECO full reroute (-0.971601493 ns,
fast hold +0.118656366 ns); best setup recipe (-0.680044484 ns,
fast hold +0.010796087 ns). None passes strict signoff.

## Measured diagnosis before the next physical trial

Fresh extended slow/fast baseline replay reproduces the best recipe. It queries
16 paths per failing endpoint, each input separately (four per endpoint),
register-origin paths (eight per endpoint), 100 competing global paths, and
explicit paths through six candidate drivers. The unchanged standard replay
also retains reset rise/fall, ena, output and OE reports. Physical inputs and
all six library hashes match the previous complete replay manifest.

All 17 failing endpoints are in engine 1: ten pin bits [2:11], four direction
bits [0:3], two inferred instruction-read address bits [0,3], and RX FIFO
word 3 bit 26. D and Q connections were compared against the exact synthesis
Verilog, allowing native transparent buffer/delay cells. The original synthesis
JSON was re-emitted with and without generated names; **every emitted cell and
pin** had to match the original Verilog before using JSON state identities.
This avoids inferring RTL identity from numeric cell numbering.

The acceptance chain `_17226_ -> _17236_ -> _17238_` appears in paths to all
17 failing endpoints. `_17226_` combines host pending-address equality with
acceptance conditions; `_17236_` selects engine 1; `_17238_` qualifies the live
address. Subsequent staged-word destination decode and local/group control
commands feed stop/start/abort and running/retirement logic. The path continues
through instruction-dependent selection and architectural update priority.
It is not merely a direct host write to the terminal register.

The leading path's `_17226_` NOR3 arc is 1.058248 ns and drives 0.065684 pF;
0.050901 pF is wire capacitance. `_17236_` AND2 contributes 0.918698 ns,
driving 0.112930 pF, of which 0.093987 pF is wiring. `_17238_` NAND2 adds
0.739374 ns. These stages precede the competing terminal branches.

The `_28912_` A221OI branch is heavily loaded despite having only
two sinks: 0.066651 pF of its 0.072923 pF maximum total load is wire capacitance
(91.4%). Its two functional sinks are `_28913_/A` and `_29069_/B`, not diodes.
The reference through-path arc is 1.405217 ns, output slew 1.473380 ns.
The alternate `_28923_` branch has 0.070365 pF wire / 0.079801 pF total load
and three functional sinks. Wire *capacitance* substantially increases cell
delay even where the reported inter-pin wire *delay* is small. These must not
be conflated. Output buffering adds its own arc and changes routing and load
distribution; the prior A experiment proved that local isolation alone is
insufficient for global improvement.

The exact fast hold minimum is `_32071_/Q` (engine-1 ISR[6]) through
`eco_data_1_813094`, `_30252_` and `_30253_`, back to `_32071_/D`.
Arrival 0.747261 ns, required 0.736464 ns, slack +0.010796 ns. The clock path
is expanded, including uncertainty and reconvergence adjustment. The small
margin follows the ISR fanout repair and must be retained in every comparison.

## Ranked causal hypotheses and bounded repair

1. Shared acceptance/control drive is a better first intervention than another
   terminal buffer: all 17 failing cones contain its loaded stages. Test
   `_17226_` NOR3, `_17236_` AND2, `_17238_` NAND2 at strength 2 instead of 1.
   Prediction: reduce common host-address arrival into both late branches.
   Risks: extra upstream pin capacitance, changed legalization/routing,
   electrical regressions, and new hold minima. This does not remove logical
   depth or assert that buffer delay is free.
2. If that fails, reassess the measured post-repair paths before changing the
   mechanism. The deep staged-word/group-control/reconvergent update logic is
   a candidate for combinational restructuring; the rejected pending-word
   cache is not repeated. Its measured regression and retained patch were read.
3. Remaining slew/fanout must be repaired on the final antenna-loaded route;
   pre-route fanout counts and a setup-only pass cannot qualify an implementation.

The `upstream` suite has exactly two cases: a fresh best-recipe control and the
three-driver candidate. Both use the same prepared post-antenna input, eight
OpenROAD threads, identical legalization/routing/antenna/extraction, declared
ECO audits and nine-session replay. The detached launcher and process/status
records are retained. The unchanged strict gate decides acceptance.

## Reproduction

From the repository in Ubuntu-24.04, `python3
docs/timing/20261027-cone-diagnosis/launch_upstream.py` launches the fixed pair
inside `/home/shane/eda/librelane-3.1.0.dev3` using `nix develop --offline`.
It refuses an existing output root; completed runs must be reused, not
overwritten. The launcher records exact commands and the worker PID under
`test/sim_build/data_upstream_20261027/`. Compact comparison evidence is under
`docs/timing/20261027-data-upstream/`.

Extended cone diagnostics use `tools/timing/diagnose_cones.py --trial <trial>
--synthesis <exact-yosys-json> --out <fresh-output>` in the same Nix environment.
Completed reference diagnostics are in `test/sim_build/cone_diagnosis/reference-09`.
Earlier attempts failed before completion while resolving JSON naming, native
hold-buffer normalization, and the pinned report_net API. They are preserved
and are not qualified diagnostic runs or physical screens.

## Completed shared-drive comparison and adaptive followup

The fresh control exactly reproduces -0.680044484 ns. The three-driver repair
measures -0.469817976 ns WS, -3.995197175 ns TNS, 17 setup endpoints, 24 slow
slew pins, 11 fanout drivers/corner, and +0.012395307 ns fast hold. All 18
independent sessions complete, all annotation/capacitance/hold checks pass,
logical audits pass, and both final routes retain 2,421 clock pins and zero
overloaded clock buffers. Native routing DRC and antenna counts are zero.
Both unchanged strict gates reject setup and electrical violations. The
comparison is `timing/20261027-data-upstream/comparison.json`.

This is a measured global improvement of 0.210226509 ns WS and 2.087198029 ns
TNS, not closure. The endpoint count conceals migration: pin[3] and inferred
read-address bit[3] now pass, while two more RX FIFO storage bits become
negative. The new worst path uses the *other engine's* acceptance branch
`_17227_ -> _17229_ -> _17235_`, then shared group-command gate `_17250_`,
and ultimately engine-1 pins[8]. The source-level group register supports
commands to either engine from either selected bank, explaining this crossing.
The now-limiting `_17250_` rising arc is 2.057512 ns with 2.391227 ns slew;
its load is 0.121399 pF, including 0.098745 pF wire capacitance.

The adaptive `balanced` trial therefore adds strength 2 on `_17227_` and
`_17229_`, plus one non-inverting buffer on `_17250_`, to the measured shared-
drive recipe. This addresses the measured sibling branch and shared load
together. It is a different combination from earlier B; no additive benefit
is assumed. Its comparator is the completed audited shared-drive run, reused
with its original hashes, configuration, extraction, and full replay evidence.
Only the candidate receives a new physical run. Launcher:
`timing/20261027-cone-diagnosis/launch_balanced.py`.

The original worst path contains 29 non-buffer cell arcs totaling 16.056867 ns,
two buffer arcs totaling 1.171664 ns, 0.198312 ns explicit inter-pin wire
increments, and 0.003433 ns input-port increment, in addition to the 4 ns
external input budget. Arrival is 21.430279 ns, required 20.750235 ns.
The new worst path has 15.847659 ns non-buffer arcs, 1.166625 ns buffers,
0.193657 ns inter-pin increments, arrival 21.211905 ns and required 20.742086 ns.
These are different endpoints/branches, not a same-arc subtraction. Most
reported delay is in loaded cell arcs; the 91% wire-capacitance fraction on
`_28912_` must not be mistaken for 91% explicit wire delay. Capture-clock
effects remain in the expanded reports; no clock skew benefit is assumed.

The complete baseline electrical inventory collapses 44 slow slew violations
to eight driving nets. All 13 fanout failures include antenna loads. For
example `uio_in[3]` has three functional and 18 antenna pins; `_17026_/Y`
has seven functional and seven antenna pins. The JSON inventories list every
violating pin, its driver, and each functional/antenna load at every corner.

Baseline register-only slow setup is positive (+0.84 ns rounded); reset
rise/fall are also positive (about +6.99/+7.16 ns). Dynamic `ena` is still
negative (about -0.13 ns) to an already-failing pin endpoint. All output/OE
paths are included and positive. These diagnostics do not remove any paths
from production acceptance. The fast ISR[6] self-feedback path remains the
global minimum after shared-drive repair; the next distinct hold endpoint in
the original reference is `_32224_ -> _32213_` at roughly +0.10 ns.

## Setup-passing balanced route and electrical followups

The balanced candidate passes setup in all three corners: slow +0.252523343 ns,
typical +6.084301235 ns, fast +9.481913301 ns, with zero setup TNS/endpoints.
Hold margins are +0.371554353/+0.144785743/+0.012208623 ns respectively.
It still fails strict signoff with 40 slow slew pins and nine fanout drivers
per corner. Capacitance and filtered annotation counts are zero. All nine
replay sessions, the logical transformation audit, and the routed clock audit
pass; there are 2,421 clock pins and no clock-buffer output above eight loads.
These are post-route screens, not qualified GDS. Comparison:
`timing/20261027-data-balanced/comparison.json`; extended near-critical paths,
source mapping and all electrical loads:
`timing/20261027-cone-diagnosis/balanced-complete/`.

The next electrical candidate sizes four measured NOR drivers, isolates three
loaded compound gates, and splits the nine measured fanout drivers in groups
of at most four, allowing some room for antenna insertion. It preserves positive
setup but reduces slow margin to +0.053006490 ns; typical/fast are
+5.960971441/+9.415175572 ns. Hold is +0.368898034/+0.143257743/+0.011201429 ns.
All setup/hold TNS and violation counts remain zero. Slow slew falls to 12
pins, and fanout to five drivers/corner; capacitance and filtered annotation
remain zero. The unchanged strict checker rejects electrical violations only.
All nine replay sessions and both logical/clock audits complete successfully.
Comparison: `timing/20261027-data-electrical/comparison.json`; extended diagnosis:
`timing/20261027-cone-diagnosis/electrical-complete/`.

The residual slew drivers are `_23874_` (NOR2, seven functional sinks),
`_24421_` (O21AI, one sink), and `_24620_` (NOR3, one sink). The residual fanout
drivers are `_26939_`, `_31502_`, `_32072_`, `place6195`, and the newly inserted
buffer `eco_data_17_813111`. The last drives four functional sinks and **16 new
antenna diodes**. This is a physical routing interaction, not a missed
functional load or permission to ignore diodes.

The adaptive `sink_local` candidate adds strength on the measured NOR2/NOR3,
isolates the O21AI (no stronger pinned-library variant exists), and splits the
four new original fanout drivers. For `_17026_`, it changes the existing split
from four to two loads and places each buffer at its sink-group centroid before
legalization. The hypothesis is that reducing the long branch reduces antenna
insertion; all antenna and fanout checks remain enabled. This route could
regress the narrow setup/hold margins, so no benefit is assumed. It reuses the
completed electrical control and runs one fresh candidate from the same frozen
input. Exact recipe and launcher:
`tools/timing/data_eco_trial.py`,
`timing/20261027-cone-diagnosis/launch_sink_local.py`.

The completed sink-local route clears **all slew violations** and has setup WS
+0.239241522/+6.095105926/+9.490527743 ns (slow/typical/fast). Hold is
+0.367351826/+0.142502458/+0.010718537 ns. All setup/hold TNS/counts,
capacitance and filtered annotation counts are zero. The strict gate rejects
only four fanout drivers per corner. All nine replay sessions and both audits
pass. The formerly 16-diode branch no longer violates fanout. New residuals
are `_17916_` (seven functional + four antenna loads), `_19177_` (five + four),
`place7144` (eight + two), and `place5579` (eight + one). Their identities and
loads are in `timing/20261027-cone-diagnosis/sink-local-complete/`.

The `fanout_tail` candidate adds only four group-of-four splits to that recipe.
Its `_19177_` buffer follows the already-declared strength change: the generator
checks strength 2 at insertion, while the logical audit still checks the frozen
strength-1 original and the declared replacement. The completed sink-local route
is the reused comparator. Launcher:
`timing/20261027-cone-diagnosis/launch_fanout_tail.py`.

The four-net full reroute is rejected: slow WS/TNS -0.070352615 ns at one
endpoint (engine-1 pins[8]), zero slew/cap/gaps, five fanout drivers/corner,
and +0.013728019 ns fast hold. The failing path now starts at **ui_in[5]**
(read control), through `_17205_` (wr XOR rd), armed/ena beat qualification,
read-intent qualification `_17707_`, and bank/address-qualified snapshot read
`_17710_`. Source `host_interface.sv:20-27`, `pio_host_bank.sv:27`, and
`protocol_core.sv:99-102` establish the host RX pop / RX room dependency.
That room condition participates in instruction stall/retirement and hence pin
updates; it is not the earlier pending-address/group-write branch. The loaded
NAND3 `_17710_` contributes 1.524041 ns, drives eight functional sinks, and has
0.079980 pF wire capacitance of 0.106788 pF maximum total load. The late
`_28912_` branch still competes. Full diagnosis, including the one mapped
failure and competing global hold paths, is retained in `fanout-tail-complete`.

The `read_acceptance` candidate is prepared to strengthen `_17710_` to NAND3_2
and address the five newly measured fanout drivers. Four get group-of-four
splits; the `_17026_` split changes from two to four loads while retaining sink-
centroid placement, reducing its root from seven buffer inputs to four. That
root had acquired four additional antenna diodes. No setup benefit or final
electrical pass is assumed. The matched comparator is the completed fanout-tail
route. The original acceptance and diagnostic constraints remain unchanged.

An independent native incremental-routing comparison tests the different
mechanism of retaining existing guides/wires through the ECO and using
`global_route -start_incremental/-end_incremental`. The pinned OpenROAD source
initializes its incremental router from detailed routes and destroys dirty
wires only in `updateDirtyNets`; the normal detailed router still follows.
The no-ECO control moves zero cells and globally reroutes zero nets, **but the
subsequent detailed route preserves only 3,034 of 25,346 serialized signal
routes and changes 512 clock routes**. It measures -0.016591173 ns slow setup
and six fanout failures. Therefore the flow must not be described as preserving
final routing merely because global routing is incremental. The four-net
candidate globally reroutes 37 nets; its final measurement is still required.
Source: [pinned GlobalRouter.cpp](https://github.com/The-OpenROAD-Project/OpenROAD/blob/dcf36133a369abc8f3c5e5738cd4d82e4903c0e0/src/grt/src/GlobalRouter.cpp).
The first two incremental launch attempts failed before completing a physical
screen (omitted checker config in the screen subset, then a custom-step variable
scope issue). They are preserved as infrastructure failures; the third attempt
uses the native GlobalRouting variable set without changing its values.

## Production integration trace (not adopted)

`info.yaml` defines the 13 source files, 50 MHz and 8x4 allocation.
`.github/workflows/gds.yaml` invokes `TinyTapeout/tt-gds-action@ihp-cmos5l`,
then the unchanged repository signoff checker; precheck and gate tests depend
on that job. The action revision previously documented by this repository,
`3412659307918422f3f0727917cf9b499aaca588`, installs LibreLane 3.1.0.dev3 and
PDK `2bbec755dc67ca3db0261c3d6163e15735d66710`. Its support-tools step merges
`src/config.json` with the manifest-derived `src/user_config.json`, then calls
`python -m librelane ... src/config_merged.json`. Source:
[action](https://github.com/TinyTapeout/tt-gds-action/blob/3412659307918422f3f0727917cf9b499aaca588/action.yml).

The current workflow and support-tools ref are branch references, not immutable
commit pins. The fetched support-tools `project.py` blob
`ef41ba16219c786fa6db3970f4505a9bc883e45a` is retained as a snapshot for this
integration investigation; it is not claimed to identify the old CI checkout.
The locally measured LibreLane commit is
`ca6adb1e2982cd75445a68b632d461213d8ca421`. It discovers Python packages named
`librelane_plugin_*` and permits a registered flow in config `meta.flow`.
A clean production integration would need a packaged/installed flow step,
validated source/structural target discovery, the measured placement/clock
settings, and final-state acceptance. Numeric cells from these experimental
routes cannot simply be copied into normal CI. No failed recipe has been
enabled in production.

Preparatory integration code now exists in `tools/timing/production_flow.py`,
but no production config or workflow selects it yet. It retains the complete
Classic frontend and GDS/signoff tail, adds audited clock splitting after CTS,
reproduces the measured first-route/preparation/data-repair/final-route sequence,
and invokes the unchanged strict checker plus nine-session replay and final
clock audit before GDS. Duplicate native step IDs retain their original gating
switches on both routing passes. The candidate class imports successfully in
the pinned SDK; this API check is not a clean physical build.

`resolve_eco_targets.py` replaces numeric target dependence with bidirectional,
pin-labelled connectivity fingerprints, including actual cell strengths and
boundary port names and excluding internal instance/net names and locations.
Every target in the sink-local recipe resolves uniquely on the frozen input.
A future clean build must regenerate its operation list through this resolver;
missing/ambiguous/changed neighborhoods fail closed. Tests rename every internal
cell/net, corrupt a connection, and introduce an ambiguous target. The timing
tool suite now passes 53 tests. The structural contract is not logical/physical
equivalence and does not replace the existing ECO audit or final LVS.

The production support tools are checked out locally at immutable commit
`d66cf179e7bc4d296362ab7e2e3b344dc3c4f665`, matching the fetched project.py snapshot.
Pinned Nix provides Icarus 13.0 at
`/nix/store/nifnxfn7bcwpzxnyfbis5pdbd738pxjc-iverilog-13.0/bin/iverilog`.
These are preparation for final qualification, not completed qualification.

The frozen clean-synthesis probe now completes the actual Tiny Tapeout config
generation and `python -m librelane` entrypoint through
`Checker.NetlistAssignStatements`. Its emitted mapped Verilog is **byte for
byte identical** to the archive (SHA256
`486466d6abe660eec5b2ad08bd880d5bd08568334e8979a401b367fa1a687e4d`): all
19,349 cell/pin records match. Latches, unmapped cells, synthesis consistency
errors and lint errors are zero. Eight lint warnings match the archived count.
The production support template has identical die geometry and all 43 signal
pins. Evidence: `clean_synthesis_identity.json`; durable probe:
`test/sim_build/production_probe_20261027_02/`. The first probe failed at CLI
argument validation before synthesis because --force-run-dir requires an
existing directory; it is not a design failure. The root plugin only registers
the opt-in flow; production src/config.json still selects its existing default.

## Completed native incremental screen and final overload

The completed `data_incremental_20261027_03` pair has identical frozen inputs,
configuration and model hashes. Both logical transformation audits, both final
clock audits (2,421 sinks, no buffer output above eight), all 18 STA sessions,
baseline agreement and complete coverage passed. The unchanged strict gate
rejects both routes, for the reasons below. Evidence is
`timing/20261027-data-incremental/comparison.json`.

| Case | Slow setup ns | Typical setup ns | Fast setup ns | Fast hold ns | Slew | Fanout/corner |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Matched no-ECO incremental control | -0.016591173 | 5.913645740 | 9.375943842 | 0.012809421 | 0 | 6 |
| Four-net incremental repair | 0.305021794 | 6.122039049 | 9.517193525 | 0.012887691 | 0 | 1 |

The candidate improves slow setup by 0.321612967 ns relative to its matched
control. All setup/hold TNS and counts, capacitance and filtered annotation
counts are zero on the candidate. Its sole strict failure is `place6629/X`,
with nine loads against a limit of eight at each corner. The fast hold margin
is only 12.9 ps, not comfortable headroom. The candidate preserves 2,940 of
25,346 original serialized signal routes and changes 511 clock routes; native
incremental global routing does not imply that detailed routing preserves
unaffected geometry. No improvement is attributed to an unchanged layout.

`place6629` is a buf_1 with eight functional loads and one actual antenna diode
`ANTENNA_149`. Its net reaches engine-0 instruction-memory word mux selections
and `place6628`. The repair script includes antenna input pins in its actual
load list: a follow-up splits all nine loads into three groups of at most
four, preserving the diode connection behind a new buffer. It predicts relief
of this specific overload, with extra buffer/wire load
and global detailed-route perturbation as risks. A new no-ECO comparator uses
the identical completed four-net candidate as its input. The pair is running
in `test/sim_build/data_incremental_tail_20261028`; its outcome is not yet
credited. The previously prepared host-read acceptance recipe was not launched
because this measured alternative has positive timing and a narrower remaining
failure inventory.

Both incremental stages have uniquely resolving structural contracts checked
against their exact pre-ECO ODBs. The candidate clean-build flow now includes
these stages, with native detailed routing after each, before final extraction,
strict acceptance and the complete GDS tail. A frozen clean integration run
has started in `test/sim_build/production_candidate_20261028_01` through actual
Tiny Tapeout config generation and the LibreLane CLI. It consumes source,
contracts and pinned tools, not an archived ODB. Production src/config.json and
CI are still unmodified; the frozen candidate is not a qualified baseline.

## Clean reproduction and route-preservation follow-up

The one-net follow-up completed its 18-session matched comparison. Its target
overload was removed, but antenna repair created new overloads at `place7283/X`
(14 loads), `_20787_/Y`, `_31540_/Q` and `place6111/X` (nine each). The candidate
has slow setup +0.044533267 ns and fast hold +0.012285284 ns, zero slew/cap/gaps,
and four fanout drivers/corner. Its no-ECO comparator has +0.249125172 ns slow
setup, +0.013692159 ns fast hold, and three fanout drivers/corner. Candidate and
control preserve only 13,942 and 13,882 of 25,358 serialized signal routes and
change 247 and 252 clock routes respectively. This is another strict rejection,
not a setup/hold failure or a crashed experiment. Evidence is
`timing/20261028-data-incremental-tail/comparison.json`.

Clean candidate 01 exposed a stage-specific configuration mismatch. The original
placement screen used GRT_ADJUSTMENT=0.30 during GPL's internal routing; 0.25
was introduced only in subsequent routing screens. Applying 0.25 during clean
placement changed connectivity/placement. The input DEF before placement was
byte-identical; die and physical signal-pin geometry remained identical (the
full fingerprint differed only in an internal output-net name). Candidate 01
was stopped and retained as an interrupted configuration-mismatch attempt.

`PlacementViews` now retains 0.30 for placement and 0.25 for subsequent routing.
Clean candidate 02 exactly reproduces all 22,435 clock-repaired instances,
connections, placements, nets and pin geometry. It then resolves every data
and incremental target structurally and completes the native routing/extraction
sequence. Its final NL/SDC/ODB/DEF are **byte-identical** to the failed one-net
screen, including slow setup +0.0445332672232511 ns and fast hold
+0.0122852842487437 ns. The unchanged gate correctly stops before GDS on four
fanout violations per corner. This establishes clean-build reproducibility of
the measured recipe, not production readiness.

The next mechanism preserves unaffected wires instead of accepting another
global detailed reroute. The pinned OpenROAD DRT parser explicitly recognizes
FIXED encoded wires, marks their nets fixed, and excludes them from route
replacement/output deletion. Source:
[pinned DRT io.cpp](https://github.com/The-OpenROAD-Project/OpenROAD/blob/dcf36133a369abc8f3c5e5738cd4d82e4903c0e0/src/drt/src/io/io.cpp).
After incremental GRT has invalidated the dirty wires, the experiment marks
remaining wires FIXED and reimports only the NETS section so DRT reads the
encoded type. An exact route/placement/pin comparison must pass before routing;
the unchanged final timing/electrical, DRC, antenna, logical and clock gates
still apply. A matched no-ECO control will measure whether preservation is real.

`data_fixed_routes_20261028_01` failed before routing because a full incremental
DEF import duplicated BPins (`DRT-0302`). This is an infrastructure failure,
not a valid screen. Attempt 02 imports nets only and passed its mandatory
roundtrip geometry/placement audit; detailed routing is in progress. No credit
is assigned until extraction and all audits finish.

Subsequent inspection showed attempt 02's fixed-net list was empty: incremental
GRT had removed **all** detailed wires, including in the no-ECO control. The
roundtrip geometry audit compared two unrouted states and could not establish
preservation. This attempt was stopped and classified as an invalid mechanism
probe, not a qualified screen. The replacement helper restores source wires
only for nets with identical cell/pin/port connectivity, cell masters, physical
locations and orientations. Nets touching moved cells or changed connections
are left for routing. It checks all restored wire records, all other wire
records, cell locations, logical connectivity and signal-pin geometry exactly.

Attempt 03 failed that restoration audit before routing because OpenDB's
INCREMENTAL DEF mode ignores NETS. The pinned `defin.h` documents that mode as
COMPONENTS/PINS-only and FLOORPLAN mode as also updating NETS. A standalone
probe using FLOORPLAN update mode with a NETS-only file restored all 25,339
routed source nets; complete geometry, connectivity, cells and placements
matched. No pin/floorplan sections are imported. Attempt 04 uses this measured
mechanism and requires final detailed-route preservation of every fixed net.
Its control has +0.304442702 ns slow setup and +0.012887691 ns fast hold with
one fanout failure/corner and otherwise passing strict metrics; replay collection
and the repair candidate remain in progress. The 0.579 ps setup change is
below the existing 1 ps replay tolerance and is not credited as an optimization.

The timing-tool suite now passes 55 tests, including tests that reject route
preservation on moved cells, changed masters, rewired pins or changed boundary
connections, and tests that detect actual pin-geometry changes while allowing
internal output-net renaming. `check_signoff.py` remains unchanged. Full GDS
qualification tooling is prepared in `qualify_gds_artifact.py`; it requires the
exact final GDS extraction for LVS, matching accepted timing views, TT precheck,
and all 39 gate tests under Icarus 13. It has not qualified an artifact yet.
