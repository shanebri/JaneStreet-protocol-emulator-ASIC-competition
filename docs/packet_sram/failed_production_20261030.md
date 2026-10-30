# SRAM production trial: failed / not currently viable

2026-10-30 disposition: **reject this integration under the current production
flow; retain the qualified design.** No SRAM connections, host portal, source-list
changes, macro configuration or flow changes were promoted to active production.
The candidate was implemented in a frozen copy, so rollback consists of discarding
its promotion; the working production implementation remains unchanged.

This result does **not** establish that no SRAM can fit the ASIC or that this
macro can never work. It establishes that this particular integration failed the
normal production power-grid stage. Repairing the power design would be a new
implementation experiment, requiring a fresh run and all acceptance checks.

## Candidate and normal-flow attempt

The passing parent is `bb7c5ef3c54a7ae2733bbfae82aa940016375007`. The trial
`test/sim_build/packet_sram_production_20261030_03/` contains a frozen copy of the
host-only integration: the 64x16/128-byte SRAM, buffered request/response wrapper,
shared host portal at selected-data addresses `0x20`–`0x24`, synthesis macro port
declaration, LEF/GDS/CDL/Liberty views and explicit placement at (740, 310) um with
10 um placement halos. Engines and their instruction stores/FIFOs stay independent.

The launcher used the same Tiny Tapeout `tt_tool.py --create-user-config --ihp`
entrypoint and pinned LibreLane `3.1.0.dev3`, PDK
`2bbec755dc67ca3db0261c3d6163e15735d66710`, `PIOClosure` flow, 8x4 tile boundary,
20 ns clock, original I/O delays/loads, uncertainty and derates. No signoff check
was disabled. The candidate clock audit explicitly recognizes the macro's `A_CLK`.
No pre-existing route/ECO evidence is treated as qualification of this candidate.

The available -55 C fast SRAM model was explicitly mapped for this diagnostic
implementation attempt. The standard-cell fast model remained -40 C. This mixed
characterization could not qualify the original exact-corner requirement even
if implementation had completed. Neither the library contents nor temperature
labels were altered. This limitation remains independent of the actual PDN failure.

## Observed results

| Stage | Result |
| --- | --- |
| Lint errors / timing constructs | Zero |
| Synthesis unmapped / consistency / inferred latch counts | Zero |
| SRAM preservation | One `RM_IHPSG13_1P_64x16_c2` instance survives |
| Manual macro placement | Passed: one instance placed |
| Power-grid generation | **Failed: OpenROAD PDN-0233** |
| Global placement / CTS / detailed route / extraction | Not reached |
| Extracted setup/hold / slew/capacitance/fanout | Not available |
| Final DRC / antenna / GDS LVS / precheck / gate-level tests | Not reached |

The macro rectangle fits at the specified location inside the core in the manual
placement stage. This is only a placement observation; routability, power delivery
and complete physical fit are unproven.

The production configuration resolves to `PDN_MULTILAYER=false`, vertical straps
on Metal4, and the default macro connector between Metal4 and TopMetal1. The macro
supplies are on Metal4. With the current grid configuration, OpenROAD reports:

```text
[WARNING PDN-0189] Supply pin pio.packet.storage.memory/VDDARRAY! is not connected to any net.
[WARNING PDN-0232] The grid "macro - pio.packet.storage.memory" (Instance) does not contain any shapes or vias.
[ERROR PDN-0233] Failed to generate full power grid.
```

The candidate supplied a hook for `VDD!` and `VSS!` but omitted the separate
`VDDARRAY!` supply. That is an integration defect, not proof of macro unsuitability.
The initial availability report also omitted this third supply from its inventory;
the checker now enumerates it. The missing macro-grid shapes/vias additionally
require a power-grid design compatible with the production layer allocation.
No grid errors were waived and no alternate power scheme was promoted.

**Consumed timing headroom: unknown/unmeasured.** There is no extracted candidate
result to compare with the parent's 0.303433731 ns slow setup and 0.012811419 ns
fast hold margins. Do not report zero cost, a timing regression, or successful
electrical signoff from this run. This candidate is rejected for failure before
those checks, not because timing was measured to be worse.

## Functional verification and setup corrections

The integrated portal passed its official-model unit test across all addresses,
both shared read paths, command/rejection/status semantics, admission pause and
reset retention. The existing subsystem simultaneous FIFO/group-isolation test
also passed with the SRAM integrated. The full candidate RTL regression completed:
**39 passed, zero failed/skipped**, along with 58 timing-tool tests, three host-API
tests and the existing unit/differential checks. The eight SRAM tooling checks
also pass. The retained `rtl_results.xml` records the 39 pin-level tests. These
are functional RTL results, not extracted timing or gate-level signoff, and
cannot override the PDN failure.

Earlier attempts are retained separately: `_01` stopped on a missing launcher
run directory; `_02` stopped when Yosys parsed unsupported timing-check syntax
in the official simulation model. The final `_03` trial uses a synthesis-only
black-box port declaration, official functional model for simulation and official
Liberty for implementation. A portal simulation sensitivity defect was corrected
before freezing `_03`. These earlier failures are not physical-fit evidence.

## Retained evidence and rollback verification

The adjacent `failed_20261030/` directory retains the job/scope/input hashes,
production log, macro-placement and PDN logs, final candidate integration sources
and configuration, and functional-test evidence. Detailed intermediate ODBs,
netlists and logs remain in the local ignored trial directory. Reproduction
helpers are `tools/packet_sram/production_trial.py`, `verify_trial.py` and
`verify_full_trial.py`; use a fresh output directory for any later experiment.

After rejection, a comparison against the passing parent found no differences in
active submitted RTL, manifest, constraints, production configuration, flow
Python/Tcl or GDS workflow (excluding unrelated pre-existing bytecode). The earlier
isolated SRAM prototype remains outside the submission manifest. Experimental
host-portal source and launch helpers are retained solely for reproduction.
