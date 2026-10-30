# SRAM supply-repair trial

Status: **rejected; not currently viable as this production integration**.
The supply repair passes its checks, but the routed candidate loses setup margin
and has timing/electrical violations. The qualified active production
implementation is unchanged; no SRAM integration was promoted.

The earlier [failed integration](failed_production_20261030.md) reached manual
placement but failed power generation. This repair connects `VDD!` and `VDDARRAY!`
to VPWR, and `VSS!` to VGND. It retains the original standard-cell power grid and
uses an OpenROAD macro perimeter ring on Metal3/Metal4, with boundary tabs to
every SRAM supply rectangle. No TopMetal1 is added: the pinned Tiny Tapeout
precheck explicitly forbids its drawing/pin/label layers for this CMOS5L project.

`repair_supply.py` derives the tabs from the actual placed LEF geometry, checks
their separation from opposite-net power geometry and adds 3x3 Via3 arrays using
the pinned rules. Horizontal buses lie outside the macro. A SPECIALNETS-only DEF
update transfers the geometry into the native PDN step; native connectivity checks
and all subsequent production checks remain enabled. Original macro views are
not changed. Source/model/constraint qualification requirements are not relaxed.

The frozen normal-production trial is
`test/sim_build/packet_sram_repair_20261030_04/`. It uses the existing pinned
`PIOClosure` production entrypoint. The fast SRAM model remains the available
-55 C model for diagnostic implementation; exact -40 C coverage remains unresolved
and prevents release approval independently of implementation results.

## Verified increment

- Native OpenROAD reports all shapes connected on both VPWR and VGND. Both native
  grid-error reports are empty. The production flow advanced into placement.
- The independent supply audit passes: all 20,428 instances retain their original
  masters, locations, orientations and signal/supply connections across the repair.
- Power geometry in the serialized production ODB exactly matches the helper's
  output, including vias. No TopMetal1 power geometry is present.
- An independent contact check over 648 local Metal3/Metal4 power shapes reports
  zero opposite-net contact groups. This does not replace full spacing DRC or LVS.
- The host SRAM portal and subsystem tests pass on `_04` against the official
  functional model. All 39 existing RTL tests, existing unit/differential checks,
  58 timing-tool tests and three host-API tests pass on the first repair snapshot.
  Only physical supply configuration and repair scripts changed afterward. The
  collector verifies byte-for-byte identity of all submitted candidate RTL and
  the macro port declaration between the tested snapshot and `_04` before
  reusing that regression. Nine SRAM-tooling tests also pass.

The repair preserves the existing buffered memory/host cycle contract. Timing
cones remain host command/readback, request registers to macro input pins, macro
output to response registers, and the added clock/reset loads. The passing
signoff parent remains `bb7c5ef3c54a7ae2733bbfae82aa940016375007`.

## Production rejection and extracted diagnostic

The initial native detailed route completes with **zero routing DRC and zero
antenna violating nets/pins**. The clock audit reaches all 2,530 clock sinks,
including the SRAM clock, with zero clock-buffer outputs above eight loads.

The normal `PIOClosure` flow then stops at `OpenROAD.DataECO`: the original
`_23190_` timing-cone fingerprint has **zero structural matches** in the new
netlist. The recipe was not forced onto another cell and the failed gate was
not bypassed. This is a production-integration rejection, even if other screens
were to pass.

To quantify the rejected artifact, `extract_trial.py` runs only native filler
insertion, RC extraction and post-route STA from the *completed detailed-route*
state. It does not reroute or resume the rejected production flow. These are
extracted diagnostics, not a completed production qualification. The baseline's
audited post-route ECOs have not been applied, so the measured difference below
is not an isolated measurement of SRAM propagation delay or supply-tab cost.

| Corner | Parent setup ns | Diagnostic setup ns | Setup headroom consumed ns | Diagnostic hold ns | Hold headroom consumed ns |
| --- | ---: | ---: | ---: | ---: | ---: |
| Slow 1.08 V / 125 C | 0.303434 | -0.756343 | **1.059776** | 0.637715 | -0.264595 |
| Typical 1.20 V / 25 C | 6.120987 | 5.444034 | **0.676953** | 0.306194 | -0.160443 |
| Fast diagnostic, standard cells -40 C / SRAM -55 C | 9.516462 | 9.043905 | **0.472557** | 0.101300 | -0.088488 |

Consumed headroom is parent minus candidate; negative values indicate increased
margin. The fast row has mixed temperature characterization and cannot establish
exact -40 C compliance. Slow and typical models match their required corners.

| Corner | Setup violations | Hold violations | Slew violations | Capacitance violations | Fanout violations |
| --- | ---: | ---: | ---: | ---: | ---: |
| Slow | **13** | 0 | **28** | **6** | **13** |
| Typical | 0 | 0 | **1** | **6** | **13** |
| Fast diagnostic | 0 | 0 | **1** | **6** | **13** |

Slow setup TNS is -3.589831 ns. The worst setup report starts at host input
`ui_in[1]` and ends at flip-flop `_35774_`; do not infer that the macro read arc
itself is the timing limiter. Filtered parasitic annotation gaps, inferred
latches, unmapped cells and synthesis consistency errors remain zero.

Both the unchanged strict metric checker and the additional no-margin-loss
comparison reject the candidate. Full GDS DRC/LVS, precheck, independent nine-mode
STA qualification and gate-level signoff were not reached or established by
this diagnostic. The supply repair is a verified increment; the SRAM feature
remains failed/unapproved under the required production acceptance rules.

## Evidence and rollback

The adjacent `supply_repair_20261030/` directory retains source hashes, exact
parent/candidate state hashes, all-corner headroom comparison, strict rejection
log, extracted state and report excerpts, native power and initial-route evidence, clock and
supply audits, and the 39-test RTL XML. `disposition.json` verifies that active
submitted RTL, source manifest, constraints, configuration, production-flow
Python/Tcl and GDS workflow still match `bb7c5ef` after Windows line-ending
normalization. Experimental SRAM sources remain outside the active manifest.
Full STA reports remain in the local ignored diagnostic run; their hashes and
sizes are recorded in `full_report_sources.json` beside the compact excerpts.

Earlier isolated repair screens are retained separately: `_01` rejected unsafe
bus positions in the grid without a perimeter ring; `_02` exposed a duplicate
native ring connection definition; `_03` generated the desired geometry but
encountered OpenROAD's restriction against loading a second populated database.
`_04` uses the supported DEF update and passes native power connectivity. None of
the failed screens is treated as a qualified parent or overwrites earlier evidence.

Reproduction helpers: `tools/packet_sram/repair_trial.py`, `repair_supply.py`,
`audit_supply.py`, and the existing functional verifiers. Use a fresh run directory.
