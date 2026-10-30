# Packet SRAM increment 0: interface candidate and availability gate

The later [buffered-portal repair record](buffered_portal_20261030.md) tracks the
host/control diagnosis, registered integration, actual-netlist repair contracts
and clean production qualification. This page retains the initial increment's
measurements and availability decision. No SRAM integration has been promoted.

The subsequent [supply-repair trial](supply_repair_20261030.md) passes native power
connectivity and independent supply serialization/contact audits, but is rejected
by the normal production recipe and extracted timing/electrical diagnostics.
Slow setup loses 1.059776 ns of headroom. No integration has been promoted.

Update, 2026-10-30: the [normal production integration attempt](failed_production_20261030.md)
failed at power-grid generation and was rejected. Active production remains the
qualified parent. Placement alone succeeded; extracted timing was not reached.
The trial also identified `VDDARRAY!` as a third supply pin omitted from the
initial inventory below; all future integrations must connect it explicitly.

Status, 2026-10-29: **incomplete, blocked before physical integration, not approved**.
The isolated wrapper is implemented and functionally tested. It is intentionally
absent from `info.yaml`, the production top, the engine connections and the
production configuration. No candidate GDS or extracted timing result exists.

The availability gate fails because the pinned PDK has no fast SRAM library at
1.32 V / -40 C. Its fast library explicitly declares `nom_temperature : -55`.
There is no evidence here that substituting it bounds both setup and hold at
-40 C. Renaming it or treating a mixed-temperature screen as production signoff
would not meet the preserved qualification contract. An approved characterization
covering the required corner is needed before proceeding with physical promotion.

## Passing parent and change limits

The passing physical parent is `bb7c5ef3c54a7ae2733bbfae82aa940016375007`,
[production run 40938542430](https://github.com/shanebri/JaneStreet-protocol-emulator-ASIC-competition/actions/runs/40938542430).
The working checkout starts at `51be3fe`; its submitted ASIC RTL, constraints,
configuration, source list and flow Python/Tcl match that qualified parent.
Pre-existing bytecode and historical LVS work products are unrelated local changes.

| Corner | Parent overall setup ns | Parent overall hold ns |
| --- | ---: | ---: |
| Slow 1.08 V / 125 C | 0.303433731 | 0.373120101 |
| Typical 1.20 V / 25 C | 6.120986558 | 0.145750305 |
| Fast 1.32 V / -40 C | 9.516461666 | 0.012811419 |

**Consumed timing headroom: unmeasured for the candidate.** No physical candidate
has run. The currently submitted design has no SRAM addition and retains its
existing qualification evidence; that is not a measurement of zero SRAM cost.

Each next physical increment must have a passing parent. The new
`tools/packet_sram/compare_timing.py` additionally rejects *any* decrease in
overall setup or hold slack in *any* required corner, even if slack stays positive.
It reports signed consumed headroom as `parent_ns - candidate_ns`. It first applies
the unchanged strict signoff metric checks to both inputs, so a failing parent,
missing corner or electrical error cannot be accepted. This is an additional
numeric check, not an approval of constraints, model coverage or physical checks.

## Macro availability

The installed PDK is a clean SRAM-view checkout at
`2bbec755dc67ca3db0261c3d6163e15735d66710`. Its CMOS5L SRAM directory links to the
SG13G2 SRAM views. `macro_availability.json` records paths and SHA256 hashes.

| Property | Selected candidate |
| --- | --- |
| Macro | `RM_IHPSG13_1P_64x16_c2` |
| Capacity | 64 halfwords / 128 bytes; six-bit halfword address |
| Ports | One clocked read/write port, one operation per active edge |
| Geometry | 236.80 x 64.36 um; 15,240.448 um2 before halo/PDN/routing |
| Enables | Active-high `A_MEN`, `A_WEN`, `A_REN`; `A_DLY` tied high |
| Writes | Full 16-bit word; no byte mask |
| Reads | Synchronous output; retained until another enabled read |
| Collision | Native simultaneous REN/WEN is write-through; wrapper never asserts both |
| Reset | No memory reset; power-up data unspecified, reset preserves committed words |
| Power | LEF `VDD!` and `VSS!`; require explicit PDN/global-connection qualification |
| Test controls | No BIST port on this macro |
| Views present | Functional wrapper/core, Liberty, LEF, GDS, CDL |
| Exact slow / typical | Available at 1.08 V / 125 C and 1.20 V / 25 C |
| Exact fast | **Missing at 1.32 V / -40 C**; available model is -55 C |

View existence and geometric fit are prerequisites, not DRC/LVS/PDN or timing
proof. No inferred-memory or flip-flop fallback substitutes for this macro.

## Implemented buffered interface

`src/packet/packet_sram.sv` instantiates the real macro. It accepts one stream of
requests: `req_valid/req_ready`, `req_write`, `req_addr[5:0]`, `req_wdata[15:0]`.
Every read and write returns one response through `rsp_valid/rsp_ready` and
`rsp_rdata[15:0]`. Writes return zero. A request is accepted only on an edge with
both valid and ready asserted. Producers hold request fields until acceptance.

| Edge | Action without pauses |
| --- | --- |
| N | Accept and register address, direction and data |
| N+1 | Issue the registered request to the macro |
| N+2 | Register the macro read result, or zero for write acknowledgement; assert response valid after the edge |
| N+3 | Earliest response consumption; return to idle |
| N+4 | Earliest next request acceptance |

There is no combinational request-to-macro or macro-to-consumer data path.
Response data and valid remain stable under backpressure. There is no same-edge
response-drain/request-accept bypass. A simultaneously offered request while busy
is not accepted; its producer must retain it until ready. Read/write requests to
the same location are strictly ordered by acceptance and completion. This is raw
data storage, with no FIFO replacement, packet-length metadata or ownership yet.

`enable=0` stops request acceptance and macro issue. A request already captured
waits in the issue state. An access already issued still captures its result and
can drain its response while disabled; conventional valid/ready handshakes remain
consistent. This candidate-local admission control is not wired to engine `ena`.

Synchronous active-low reset cancels queued requests and held responses. The
macro enables are gated by `rst_n`, preventing a queued write from committing on
a reset edge. A write issued before reset remains committed; its acknowledgement
may be canceled. Reset does not clear SRAM bits. Reading an unwritten location
returns unspecified data and does not imply packet validity.

Only one logical master is admitted in the first integration: the host portal
described below. Both engines remain disconnected. There is no hidden promise
of concurrent host/engine ports, arbitration fairness or engine memory throughput.
Any later multiple-client adapter needs its own buffered arbitration contract
and separate physical increment. Existing FIFO old-head/full/empty behavior and
one-instruction-per-tick execution remain requirements.

## Host portal contract for the next integration

This map is **specified, not connected or advertised as a working feature**.
The first full-design physical candidate should add a host-only shared portal
using currently unused selected-data addresses. Existing host byte staging and
snapshot semantics remain intact; no new direct nibble-to-SRAM path is allowed.

| Selected-data address | Word access |
| --- | --- |
| `0x20` STATUS | Read: bit 0 busy, bit 1 done, bit 2 rejected; other bits zero |
| `0x21` ADDRESS | Read/write: six-bit halfword address; reject writes with upper bits set |
| `0x22` WDATA | Read/write: full 16-bit write data; reject writes with upper bits set |
| `0x23` COMMAND | Write exactly 1 for read, 2 for write, 4 for acknowledgement; reads zero |
| `0x24` RDATA | Read last completed 16-bit result, zero-extended; no read side effect |

Portal state is shared regardless of selected engine; existing partial host words
and snapshots remain per bank. Only the final host word commit changes a portal
register or submits a command. A command captures ADDRESS/WDATA atomically into
the buffered request. Later staging writes cannot retarget it. Busy starts at
command acceptance and ends when the response is captured by the portal. Done
holds the result until COMMAND=4 acknowledges it. New read/write commands while
busy or done, malformed commands and out-of-range address/data writes are rejected
without changing the in-flight request; rejection is sticky. COMMAND=4 clears
done/rejected only while not busy. Neither reads nor engine selection clear flags.
Reset clears portal control/result metadata and cancels outstanding acknowledgement,
while retaining SRAM contents. Protocol engines can continue operating throughout
host accesses because no engine resource or execution path is shared with SRAM.

## Affected timing cones and register boundaries

Before any production change, enumerate these cones from the newly synthesized
netlist and compare path groups against the parent, including the new SRAM pins:

- Host-input acceptance/pending-address and selected-engine decode to host-bank
  staging, portal command/request registers and host readback. The parent's worst
  overall slow setup path is host-input driven. New selector loads can consume
  its 303 ps margin even though the SRAM itself is buffered.
- Request address/data/control registers to macro address, DIN, MEN, WEN and REN.
  The issue state gives one full clock between request capture and macro sampling.
- Macro `A_CLK` to `A_DOUT`, then response-data capture registers on the following
  edge. Check read delay, input setup/hold and clock pulse-width requirements.
- Response register to portal result register, then selected-data read mux to
  host snapshot/transport. Existing host read timing and snapshots must survive.
- Clock, reset and admission-control fanout. New macro/register sinks can change
  unrelated placement, clock skew, capacitance and short hold paths. The parent
  has only 12.811 ps of fast hold margin.

Engine IMEM/decoder and FIFO data paths have no intended new combinational arcs.
That isolation must be demonstrated by netlist connectivity, not assumed from RTL.

The current flow needs explicit macro support before physical qualification:
`report_io_paths.tcl`/`replay.py` load only standard-cell/I/O libraries, and
`audit_clock_tree.py` recognizes `CLK` sinks rather than `A_CLK`.
`qualify_final_route.py` fixes the old sink count at 2,421. Add exact macro models
and source-derived sink expectations with coverage tests; preserve checks for
every old sink and the new macro clock. Existing structural ECO recipes must
resolve and audit the new netlist or fail; never waive a mismatch or reuse old
numerical cell names. These changes are not implemented in this blocked increment.

## Qualification sequence and evidence

1. Resolve exact-corner macro availability. Current gate **fails**.
2. Freeze and physically qualify a host-only full-design candidate using the
   normal pinned production entrypoint. Confirm exactly one macro survives
   synthesis, correct placement/halo/PDN, views included at stream-out/LVS,
   complete macro arc/parasitic coverage and functional gate tests with its model.
3. Require all existing signoff checks: 20 ns clock, original I/O budgets,
   uncertainty, derates, loads, all three corners, dynamic reset/enable baseline,
   zero setup/hold/electrical errors, coverage, clock connectivity, final serialized
   geometry, routing/Magic DRC, antenna, GDS LVS, precheck and gate regressions.
   KLayout DRC remains outside the established qualified-flow scope.
4. Compare every corner against the passing parent using the additional numeric
   gate. Report setup/hold headroom consumption explicitly; reject any regression
   or electrical error. A green ordinary gate with lower positive margin is
   insufficient under this request. Do not proceed to engine connections until
   the host-only production candidate passes all gates.

Completed local checks:

- Official PDK functional-model regression: **384 accesses passed** including all
  addresses, random data, backpressure, pause, reset cancellation and retention.
- Eight availability/comparison tests pass, including a relabeled -55 C library,
  missing GDS, unavailable PDK provenance, positive-slack loss in each corner,
  new slew error and failing/missing parent rejection.
- Existing production RTL regression: **39 passed, zero failed/skipped**, plus
  all existing FIFO/frontend/host/pad/subsystem and 27,391-cycle differential
  timing unit checks, 58 timing-tool tests and three host-API tests. This is a
  regression of the unchanged submitted design, not coverage of an integrated
  SRAM. The Windows launcher first encountered sandbox temporary-directory
  permission errors; the complete regression then passed in the existing Linux
  test environment using `/home/shane/eda/pio-test-venv/bin/python -B test/run.py`.

Reproduce from the repository root in the existing Linux EDA/test environment:

```sh
python3 -B tools/packet_sram/check_macro.py \
  --pdk-root /home/shane/eda/pdk-2bbec755 --out NEW_availability.json
# Expected exit 1 with the current pinned views: fast -40 C is missing.
python3 -B tools/packet_sram/run_unit.py \
  --pdk-root /home/shane/eda/pdk-2bbec755 --out test/sim_build/NEW_packet_unit
python3 -B -m unittest discover -s test -p test_packet_sram_tools.py
python3 -B tools/packet_sram/compare_timing.py \
  --parent PARENT_RUN --candidate CANDIDATE_RUN --out NEW_comparison.json
```

All evidence outputs use fresh paths. Retained unit evidence is in
`functional_manifest.json` and `functional_simulation.log`; availability evidence
is in `macro_availability.json`. No passing physical-parent successor is claimed.
