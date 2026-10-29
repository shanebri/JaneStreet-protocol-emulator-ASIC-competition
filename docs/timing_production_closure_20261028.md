# 50 MHz production closure and qualification

**Superseded by the [October 29 LVS closure work](timing_lvs_closure_20261029.md).**
The clean build reproduced the route screen but failed actual-GDS LVS with
four physical shorts. The October 29 report records the repair and current
qualification status. The remainder preserves the earlier checkpoint evidence.

**October 28 status: route screen passed; clean production qualification was running.**
The active configuration selects the audited repair flow. This document does
not yet declare a qualified baseline for architecture development.

The fixed contract remains 20 ns, 8x4 tiles, both PIOs, all memories/FIFOs,
the ISA/register map and every host/reset/ena/priority cycle. RTL, info.yaml,
timing budgets, uncertainty, derates, loads, PDK models and the strict signoff
checker are unchanged. Operational/reset-active STA modes remain diagnostic.

## What caused the failures

1. **Shared acceptance logic driving long capacitive nets.** Exact synthesis
   mapping places the original 17 failing endpoints in engine 1: pin bits 2–11,
   direction bits 0–3, two inferred instruction-read address bits and one RX
   FIFO bit. Host acceptance/pending-address equality and engine/live-address
   decode feed command, stall/retirement and architectural update logic. The
   early `_17226_/_17236_/_17238_` chain reaches all 17 failures. Large wire
   capacitance slows the driving cell arcs; the explicit wire-delay number alone
   understates this cost. Both engine-selection branches and the shared abort
   branch needed correction. Buffering a terminal gate alone moved the global
   worst path to competing logic and could worsen total negative slack.
2. **Antenna repair adds real loads after fanout repair.** Functional fanout
   below eight did not establish final compliance. The remaining overloads
   included antenna diodes; every audit and repair counts these pins. Fixing
   one overloaded branch followed by global detailed rerouting repeatedly
   created new overloads elsewhere, even with no ECO in the matched control.
3. **Incremental global routing did not preserve detailed wires.** In this
   pinned flow it removed all detailed wires from its output. A subsequent
   native detailed-route pass therefore perturbed thousands of unrelated nets
   and hundreds of clock routes. The final repair restores source wires only
   where exact connectivity, masters, locations and orientations are unchanged,
   marks those wires FIXED using a supported DEF update, and lets native DRT
   route the affected nets. Every protected wire must retain its exact geometry
   in the final route. No DRC, antenna or timing limit is relaxed.

The full mapped endpoint inventory, competing paths, cell/wire/load breakdown,
source-level evidence, rejected alternatives and infrastructure incidents are
in [the diagnosis](timing_cone_diagnosis_20261027.md). Detailed electrical and
path inventories are retained under `timing/20261027-cone-diagnosis/`.

## Measured matched result

The last comparison uses the completed setup/electrically clean route with
one remaining fanout violation as its common input. The only functional-net
ECO splits the nine actual loads of the structurally identified `place6629/X`
branch into groups of at most four, using three transparent buffers. This
branch reaches engine-0 instruction-memory selection. Both cases use the same
wire-preservation mechanism, execution settings and models.

| Corner | Control setup ns | Repair setup ns | Control hold ns | Repair hold ns | Control fanout | Repair fanout |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Slow 1.08 V / 125 C | 0.304442702 | 0.303870715 | 0.373383557 | 0.373119990 | 1 | 0 |
| Typical 1.20 V / 25 C | 6.121685554 | 6.121286762 | 0.145897076 | 0.145750416 | 1 | 0 |
| Fast 1.32 V / -40 C | 9.516919078 | 9.516648183 | 0.012887691 | 0.012811419 | 1 | 0 |

All setup/hold TNS and violation counts, slew, capacitance, filtered annotation,
latch, unmapped and synthesis consistency counts are zero on the repair. All
18 STA sessions in the pair pass replay agreement and coverage. Both final
clock audits reach all 2,421 pins with no clock-buffer output above eight.
The repair preserves 25,327 source routes exactly and changes one clock route.
Native final routing DRC and antenna counts are zero. The late seven DRC
violations resolved through the ordinary router's iterations; none was waived.

The final electrical correction costs about 0.572 ps of slow setup relative
to its matched control. This is not credited as a timing improvement. The fast
hold margin is **12.811 ps**, still narrow. The global minimum remains the
engine-1 ISR[6] feedback path, with competing hold paths included in every
baseline replay. Route success is not a claim of comfortable hold headroom.

Evidence: [comparison](timing/20261028-data-fixed-routes/comparison.json),
[table](timing/20261028-data-fixed-routes/comparison.md).

The original references remain separate: older routed clock splitting had
-1.184760767 ns slow setup/23 failing endpoints; its matched no-ECO full reroute
had -0.971601493 ns/22; the best useful starting setup recipe had
-0.680044484 ns/17. The final sequence's global improvement is not attributed
to its last one-net repair or to common rerouting effects.

## Production implementation

- `src/config.json` selects `PIOClosure`, timing-driven placement, 0.25 routing
  adjustment, eight OpenROAD threads and extraction from the actual GDS for LVS.
- `librelane_plugin_pio.py` registers the flow for the normal LibreLane entrypoint.
  `production_flow.py` retains the Classic frontend and complete GDS/signoff tail.
  Placement alone retains its measured 0.30 routing adjustment; applying 0.25
  there changed GPL's timing-driven result and was rejected.
- The flow adds audited clock branching, the measured shared-drive/load repairs,
  the four-net post-antenna correction and the final preserved-route correction.
  Each operation resolves uniquely against the current build's pin-labelled
  connectivity fingerprint. Missing, changed or ambiguous targets fail closed.
- `tools/timing/production/*.json` contains the three structural contracts.
  Generated reference names are evidence, not unverified lookup targets.
- `preserve_routes.py` restores only unchanged wires. It imports a NETS-only DEF
  using the pinned OpenDB mode that actually updates wires, then checks exact
  geometry, logical connectivity, placements and all signal pins.
- `qualify_final_route.py` invokes the unchanged strict checker, nine-session
  replay, coverage, clock connectivity, pin geometry and final protected-wire
  checks before GDS. Independent GDS qualification remains mandatory afterward.
- CI pins GDS/precheck/gate actions to `3412659307918422f3f0727917cf9b499aaca588`,
  support tools to `d66cf179e7bc4d296362ab7e2e3b344dc3c4f665`, and LibreLane to
  `3.1.0.dev3`. The measured OpenROAD is
  `dcf36133a369abc8f3c5e5738cd4d82e4903c0e0`; PDK revision remains `2bbec755`.

The first clean attempt exposed the GPL capacity mismatch and was stopped.
After correction, the second clean attempt reproduced the preceding rejected
route's NL/SDC/ODB/DEF byte-for-byte and SPEF except its DATE header. This
included its four fanout violations; the strict gate correctly stopped it.
The successful final screen is now being rebuilt from the activated production
sources in `test/sim_build/production_final_20261028_01/`.

## Qualification ledger

| Required evidence | Current status |
| --- | --- |
| Successful screen: unchanged strict all-corner checker | Pass |
| Successful screen: nine sessions, coverage, exact final clock audit | Pass |
| Successful screen: native DRC/antenna, logical/route-preservation audits | Pass |
| Timing-tool tests | 55 pass |
| Clean activated production build and route acceptance | Running |
| Final GDS generation and independent GDS LVS | Pending |
| Tiny Tapeout precheck on that GDS | Pending |
| All 39 functional gate tests on that final netlist, Icarus 13 | Pending |

No new RTL or FPGA-wrapper regression is claimed; no RTL, source manifest or
FPGA wrapper changed. The exact final gate-netlist regression is still required.

## Reproduction and retained work

The durable launcher is
`docs/timing/20261027-cone-diagnosis/launch_production.py`. It records frozen
source hashes, process identity, every actual command and a completion/failure
state. It uses a fresh output directory and consumes no archived physical state.
Its current root must not be reused or deleted to start another run.

Inside the pinned Ubuntu-24.04/Nix environment, the ordinary production path is:

```sh
export PDK_ROOT=/home/shane/eda/pdk-2bbec755
# Use the pinned support-tools checkout and its installed requirements.
python tt/tt_tool.py --create-user-config --ihp
python tt/tt_tool.py --harden --ihp --no-docker
```

The recorded local build invokes the exact LibreLane command emitted by the
hardening wrapper, in its frozen project directory, with `--manual-pdk` and a
fresh run directory. The activated flow runs its route acceptance automatically.
`qualify_gds_artifact.py` then requires matching final timing views and GDS
extraction, runs the pinned TT precheck, and runs all 39 gate tests under
Icarus 13. The launcher records its full argument list.

Pre-existing uncommitted work and rejected/interrupted attempts are retained.
Nothing has been pushed, published or represented as a completed CI run.
