# LVS closure of the 50 MHz production flow

Status update, 2026-10-29: the production repair at `bb7c5ef` is qualified by
[Actions run 40938542430](https://github.com/shanebri/JaneStreet-protocol-emulator-ASIC-competition/actions/runs/40938542430).
GDS, strict three-corner extracted timing/electrical checks, routing/Magic DRC,
antenna, LVS, Tiny Tapeout precheck, viewer and all 39 functional gate tests pass.
KLayout DRC was disabled. The [project status page](project_status.md) gives the
current margins and scope; the [coverage audit](timing_coverage_audit_20261029.md)
resolves the optional native register-setup `Infinity` metric.

The sections below retain the diagnosis and trial sequence. Intermediate
qualification states are historical; the completed CI build is the acceptance
evidence, not a claim that every local trial/launcher succeeded.

## Exact failure and cause

Checkpoint `8617565373db9f7cd351ab13db2ca456a63d0fff` failed the GitHub
[GDS run 40797631740](https://github.com/shanebri/JaneStreet-protocol-emulator-ASIC-competition/actions/runs/40797631740).
The frozen local clean production build independently reproduced nine LVS
errors after passing native route DRC, antenna and the strict timing checks.
Both compared circuits contain 25,642 devices. The layout has 25,506 nets,
versus 25,510 in the schematic. The metrics report four net-count differences,
one unmatched net group and four unmatched pins. The pin mismatches are the
four symmetric constant-low `uio_oe[3:0]` ports; they are not evidence that the
RTL pin order should be changed.

An independent conductor-rectangle audit of the actual serialized routed ODB
finds exactly four inter-net contacts, all on Metal2:

| Net | Incorrectly joined net |
| --- | --- |
| `_02546_` | engine-0 instruction memory word 18 bit 14 |
| `net10260` | the same instruction memory bit |
| `_02559_` | `net6525` |
| `net6629` | `clknet_fanoutfix_1069827` |

These contacts explain the three merged physical groups and the loss of four
independent nets. They already exist in the ODB, before GDS stream-out; this is
a physical routing defect, not a missing device model or an extraction waiver.
Exact metal coordinates and input hashes are retained in
`timing/20261029-lvs-closure/lvs_contacts_baseline.json`.

The last preservation stage restores unchanged wires as FIXED. Its geometry
identity check passes, but does not test whether newly routed wires intersect
those wires. The pinned router reports zero DRC on its internal result while
its serialized output contains these shorts. Re-reading that output as ordinary
initial routes exposes violations to native routing and repairs them. The
pinned OpenROAD writer explicitly skips updating FIXED wires; this is consistent
with an internal-versus-serialized geometry discrepancy. The precise internal
mutation responsible has not been isolated, so this report does not claim a
particular upstream source line as the proven defect. No PDK or tool binary was
patched.

## Measured repair

The repair converts wire status from FIXED to ROUTED in a NETS-only DEF update,
retaining all existing geometry as initial routing, then runs the ordinary
native detailed router and antenna checks. Its result changes only 11 of
25,361 signal routes (three clock routes), with no new or removed nets, cells,
connections, placements, pin geometry or boundary changes. A fresh independent
audit of all 557,000-plus signal-wire/via/patch rectangles reports zero contacts.
This check does not replace spacing DRC, pin connectivity or actual-GDS LVS.

| Corner | Setup before ns | Setup repaired ns | Hold repaired ns |
| --- | ---: | ---: | ---: |
| Slow | 0.303870715 | 0.303433731 | 0.373120101 |
| Typical | 6.121286762 | 6.120986558 | 0.145750305 |
| Fast | 9.516648183 | 9.516461666 | 0.012811419 |

The unchanged strict checker passes every corner: zero setup/hold TNS and
violation counts, slew/capacitance/fanout violations, filtered annotation gaps,
latches, unmapped cells and synthesis consistency errors. Fast hold remains
only 12.811 ps; this repair does not create comfortable hold headroom.

The first trial completed physical routing and strict STA, then its acceptance
wrapper stopped because the reduced trial configuration omitted the pin template
variable. This is a trial infrastructure failure. The retained repaired artifact
is being qualified in a fresh directory using the complete production config;
routing has not been repeated or its reports overwritten.

## Production integration and qualification

`PIOClosure` now includes `OpenROAD.FinalizeRoutes` after the preserved-route
pass and before extraction. The new audit requires exact logical and placement
identity and checks contacts in the actual output ODB. Preservation is checked
through the input to finalization; all subsequent route changes are separately
enumerated and audited. Final acceptance requires the extracted routes to match
the audited finalization output and independently checks wire contacts again.
The original strict timing checker and all native physical checks remain intact.

The normal pinned Tiny Tapeout GitHub Actions entrypoint loads this production
flow. RTL, clock period, I/O budgets, PDK, corner set, die/pin geometry, memories,
ISA, reset/ena behavior and cycle-level priorities are unchanged.

Timing tooling: 58 tests pass, including spatial-index comparison against
exhaustive geometry and a regression using the actual clock/data short.

Retained local trial/build directories (historical work products):

- Failing clean baseline: `test/sim_build/production_final_20261028_01/`.
- Localized routing trial: `test/sim_build/lvs_repair_20261029_01/`.
- Fresh GDS qualification of that trial: `test/sim_build/lvs_repair_tail_20261029_01/`.
- Clean integrated production build: `test/sim_build/production_final_20261029_01/`.
- Durable clean launcher: `timing/20261029-lvs-closure/launch_production.py`.

Independent GDS LVS, Tiny Tapeout precheck, all 39 exact-netlist gate tests and
the integrated production result were mandatory acceptance gates. The completed
CI run now supplies the production result. The earlier route-only screen alone
was not a physically qualified baseline.

Independent LVS has now completed in `test/sim_build/lvs_independent_20261029_01/`
using the exact GDS from the repaired trial's KLayout stream-out. All seven LVS
metric fields are zero, and Netgen reports that circuits match uniquely.
`timing/20261029-lvs-closure/repaired-lvs.rpt` retains the report. This early
independent check does not substitute for the ongoing full production checks.
Repair commit `bb7c5ef3c54a7ae2733bbfae82aa940016375007` completed successfully in
[Tiny Tapeout Actions](https://github.com/shanebri/JaneStreet-protocol-emulator-ASIC-competition/actions/runs/40938542430),
including the previously pending precheck job. Preserve the exact artifacts;
qualify subsequent ASIC implementation changes independently.
