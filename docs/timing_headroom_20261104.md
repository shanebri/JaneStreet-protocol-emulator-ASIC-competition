# Bounded timing-headroom campaign — 2026-11-04

Status: **fully qualified locally and activated**. The fresh normal production
build improves worst setup from **393.477 to 532.950 ps** and worst hold from
**48.140 to 89.366 ps**, with every required corner minimum improved. ASIC RTL,
architectural cycles and FPGA images are unchanged. This is local qualification;
no new GitHub CI or hardware result is claimed. The campaign stops after three
routed candidate hypotheses and one unchanged matched control.

The selected implementation combines host-control load isolation with targeted
transparent minimum-delay cells. Diagnostic routes screened the hypotheses;
activation required a separate full normal production build and qualification.

## Qualified reference and diagnosis

The campaign's qualified parent is the complete combined production increment recorded in
`docs/timing/20261030-control-refactor/activation.json`. Its post-route state SHA256
is `8cda1271b19e0395f15568ac628639ba6d55d0930d80f31e93b502bd3ea26074`.
The initial audit validated the original full qualification, frozen sources,
campaign-start active inputs, exact parent recipe and pinned replay inputs. Fresh
nine-session STA replay reproduces the qualified parent; no timing constraints
or corner models are changed.

| Required corner | Setup ns | Hold ns |
| --- | ---: | ---: |
| Slow, 1.08 V / 125 C | 0.393477262 | 0.474639452 |
| Typical, 1.20 V / 25 C | 6.138193239 | 0.205702239 |
| Fast, 1.32 V / -40 C | 9.624813219 | 0.048140215 |

Native extracted reports contain 1,000 selected paths per corner/check. The
inventory maps the leading endpoints from their actual netlist Q connections;
this selected-path inventory is not an assertion that every path was enumerated.

The leading slow setup paths start at host address bit 0 and terminate at
engine-1 pin/direction state. Their shared control cone includes `_28912_/Y`, an
AOI output driving two loads with a 1.742016 ns slow arc. The nearest reported
HOST_RD-to-RX-FIFO competing family starts at about 1.02 ns slack.

The five leading fast hold endpoints are ISR[7] (48.140 ps), ISR[6] (56.790 ps),
engine-0 instruction word 20 bits 12/11 (58.938/63.943 ps), and ISR[3] (73.728 ps).
Fixing ISR[7] alone would immediately expose the 56.790 ps competing path.

## Independent hypotheses

1. **Hold cluster:** replace the already-qualified ISR[6]/ISR[3] D-boundary
   buffers with characterized `sg13cmos5l_dlygate4sd1_1` transparent delay cells;
   add that same cell at ISR[7] and the two instruction-memory D boundaries.
   Earlier repairs retain their logical purpose and connectivity. Setup costs
   at all affected endpoints must be reported.
2. **Setup load isolation:** retain the exact parent recipe and add a strong
   transparent buffer near the measured `_28912_` AOI driver. Its original
   loads and long output wire move behind that buffer. This tests physical drive
   isolation without changing logic or adding a register.
3. **Combination:** only if the independent measurements justify it, measure
   their combined implementation from the same matched source.

Contracts bind the actual pre-final-repair connectivity graph with unique
structural fingerprints. Internal numerical instance names above identify the
measured evidence; production resolution does not blindly reuse those names.

The candidate-local delay audit verifies exact declared masters, their pinned
transparent functional models, deterministic sink partitions, every original
signal connection and unchanged clock topology. The existing 58 timing-tool
tests and eleven new delay-audit/reserve/precheck-evidence tests pass. No pipeline registers,
host-pop delay, ISA change, new clock, altered reset priority or instruction
latency is introduced by these physical repairs.

## Completed independent screens

The unchanged routed control reproduces all six parent margins exactly. Its
repair Tcl and detailed-routing configuration also match the qualified run.
The two independent candidates pass strict extracted setup/hold, electrical and
annotation checks in all required corners, with zero final route DRC/antenna
counts. These are diagnostic screens, distinct from the selected successor's
subsequent full GDS qualification.

| Screen | Slow setup ns | Slow hold ns | Typical setup ns | Typical hold ns | Fast setup ns | Fast hold ns |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Matched control | 0.393477262 | 0.474639452 | 6.138193239 | 0.205702239 | 9.624813219 | 0.048140215 |
| Hold cluster | 0.393875166 | 0.561024687 | 6.138428606 | 0.264246410 | 9.625013947 | 0.089365851 |
| Setup isolation | 0.582989673 | 0.474722497 | 6.281355169 | 0.205709455 | 9.708874868 | 0.048099304 |
| Selected combination | 0.532949699 | 0.561024798 | 6.249411832 | 0.264246299 | 9.689972654 | 0.089365851 |

Setup isolation gains 189.512 ps of slow setup but consumes 0.040912 ps of fast
hold. The latter is a real measured cost, larger than the numerical-tie tolerance.
The hold cluster gains 41.226 ps of fast hold. Its new global hold minimum is
`_31502_` (engine-0 bank IMEM address bit 3) to `_33857_` (actual Q net `_00003_`).
Exact re-emission reproduces all 19,349 original synthesis cells and maps the
destination to `rdreg[0]$q[3]` in engine 0's `core.fetch.words`: inferred
instruction-memory read-address state, bit 3. The renamed and original
cell types/connections are checked before assigning this identity. This newly
limiting family is documented rather than adding a fourth repair hypothesis.

Separate baseline STA sessions query every repaired D boundary directly, even
when its setup path is absent from the global selected-path list. The hold
cluster consumes these slow setup margins against the qualified parent:

| Repaired D boundary | Setup consumed ps | Remaining slow setup ns |
| --- | ---: | ---: |
| Engine-1 ISR[3] | 43.364 | 2.528353 |
| Engine-1 ISR[6] | 60.547 | 2.784974 |
| Engine-1 ISR[7] | 238.315 | 1.483572 |
| Engine-0 IMEM word 20 bit 11 | 235.283 | 10.542225 |
| Engine-0 IMEM word 20 bit 12 | 233.773 | 10.533178 |

The combination is the third and final candidate hypothesis. It passes the same
strict extracted/electrical, annotation, zero final route-DRC/antenna and exact
connectivity/clock audits. Against the fixed qualified parent it gains **139.472 ps
slow setup** and **41.226 ps fast hold**, with all six global minima improved.
It gives up 50.040 ps of the standalone setup candidate's slow-setup gain, so
the two independent gains cannot simply be added.

The slow worst path still starts at host address bit 0 and ends at engine-1
pins[8], but now takes an alternate branch through `_28923_/Y`; the repaired
`_28912_/Y` arc is absent from that reported worst path. The alternate AOI arc
is 1.477710 ns at 0.079968 pF in the setup-only screen and 1.521507 ns at
0.083022 pF in the combination. That measured 43.797 ps arc difference explains
most of their 50.040 ps global setup difference; it is not attributed to a fixed
intrinsic cost of the distant D-delay cells. Further repair of this newly
limiting branch is outside the three-candidate campaign.

The selected recipe has four additional cells relative to the qualified parent,
with two existing transparent buffers replaced by transparent delay cells.
There are still exactly 2,421 sequential cells. Standard-cell area excluding
filler rises from 380,893 to 380,951 um2 (58 um2, approximately 0.015%). The
fresh normal production build in `timing_headroom_20261104_01/production/`
uses frozen copies of the fully qualified parent's sources and the exact
screened repair contract.

The fresh production run's pre-repair ODB reproduces the qualified prefix byte
for byte: SHA256
`0a0da10821c774b55784b5327dfc14f440432683351f226600cb1c4672a595e9`.
Its selected repair also passes the real-database transparency, sink-partition,
original-signal and clock-topology audit. These checks establish a matched
production prefix.
The production repair's output ODB is also byte-identical to the selected
diagnostic repair output, SHA256
`9e148c74403f32223f5de3320e1d236d49f714b84827185215f00852cc0223e1`.
The normal production extracted state now reproduces all six selected-screen
margins exactly. Strict setup/hold, TNS, violation counts, slew/capacitance/fanout,
annotation and structural checks pass in all three required corners. Final route
DRC and antenna counts are zero. The production state SHA256 is
`aecf268e7bda1242683b19d238f0f99ea469bf9b00b6df963e042b2d71802062`.
All nine independent replay sessions, timing coverage, clock/contact checks and
all 43 signal-pin geometries pass. The normal native flow subsequently completes
with zero Magic GDS DRC errors, zero illegal overlaps, and all seven actual-GDS
LVS difference/error fields zero. All nine distinct Tiny Tapeout prechecks pass
without skips, errors or failures, including the full SG13CMOS5L KLayout deck.
All 39 functional gate tests pass on the exact qualified netlist. The native
KLayout DRC step remains disabled, matching the parent. Gate simulation uses
functional models without SDF; extracted STA supplies timing evidence.

Direct queries on the final production netlist reproduce the combined screen's
local setup/hold values in all three corners. Its slow setup costs against the
qualified parent are:

| Repaired D boundary | Setup consumed ps | Remaining slow setup ns |
| --- | ---: | ---: |
| Engine-1 ISR[3] | 42.441 | 2.529276 |
| Engine-1 ISR[6] | 55.625 | 2.789896 |
| Engine-1 ISR[7] | 217.709 | 1.504178 |
| Engine-0 IMEM word 20 bit 11 | 242.660 | 10.534848 |
| Engine-0 IMEM word 20 bit 12 | 239.617 | 10.527334 |

## Selection and qualification

Each candidate is compared with the matched control and fixed qualified parent,
including all six global margins, local endpoint costs, electrical violations,
route DRC, antenna results and area. The numerical parent-comparison tolerance is
0.000001 ns (0.001 ps); actual signoff limits receive no tolerance.

For automatic activation in this timing-only campaign, preserve the qualified
parent's six required minima and obtain a material gain in setup or hold. This
is a campaign-specific reserve, not a new global requirement that every future
architecture addition improve all six metrics. A useful candidate with a real
reserve tradeoff remains available for a concrete budget decision.

The selected successor passes the fresh normal production build, strict extracted
timing/electrical checks, independent nine-session replay and coverage, clock and
serialized-contact audits, final routing and Magic DRC, actual-GDS LVS, complete
Tiny Tapeout precheck and all 39 exact-netlist functional gate tests. All frozen
inputs remain unchanged. The 58 existing and 11 new timing-tool tests pass.
Failed runs and the previous active implementation remain available.

## Active receipt and retained evidence

The [activation receipt](timing/20261104-headroom/activation.json) supersedes
the October 31 active receipt, which remains an immutable historical record.
Activation installs only the tested physical repair recipe and flow hook;
backups of both previous active files are retained beside the new receipt.
Independent verification checks the full qualification, parent binding, active
and frozen source identity, nine distinct precheck results, artifact hashes and
pinned timing inputs. The fixed original CI baseline comparison is also recorded.

| Qualified artifact | SHA256 |
| --- | --- |
| Active repair recipe | `8ec22791eba9c3cf59f2aa815c5b4b3ca8ddfe7132919d9b6932c25a95ac383a` |
| Active production flow | `a31773db0b3cf34120dcadba3b7aafba1eab71677e48440d84769bfee78afdb3` |
| Production extracted state | `aecf268e7bda1242683b19d238f0f99ea469bf9b00b6df963e042b2d71802062` |
| GDS | `d8bf7ec0d57b6a5ea6235848b372338148e272ed93c1d28ecdef4a0056e2e3d8` |
| Gate netlist | `49687f75688eb8870bd2b3eb2dfafdc23fb0b4c637b69a82dff289244f78589c` |
| Nominal SPEF | `c8f7622323ebb80e6c9f4f6abd3e335d6987573c96ed954f8927aa6515a70503` |

The [compact campaign evidence](timing/20261104-headroom/campaign/evidence_sha256.json)
indexes the endpoint inventory, all candidate contracts and comparisons,
executed repair audits, local endpoint reports, qualification and test receipts.
Large original GDS/SPEF outputs remain under
`test/sim_build/timing_headroom_20261104_01/`; their paths and hashes are retained.

From the repository in the original WSL/tool environment, verify the current
active implementation with:

```sh
python3 -B tools/timing/headroom_release.py --verify-active docs/timing/20261104-headroom/activation.json
```

The historical `collect_refactor.py` active-source check describes the earlier
recipe. Use the new receipt verifier for the current implementation.

[OpenROAD's repair-timing documentation](https://openroad.readthedocs.io/en/latest/main/src/rsz/README.html#repair-timing)
explains why hold insertion must consider setup: its default hold repair avoids
buffers that would create setup violations. This campaign additionally measures
local setup consumption and checks all six parent reserves. The new host-control
setup branch and instruction-memory address hold family are recorded for a
future separately bounded campaign; no fourth routing hypothesis is pursued.
