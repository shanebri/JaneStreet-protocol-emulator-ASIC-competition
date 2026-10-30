> Historical single-engine measurements and architecture planning estimates.
> The dual-engine ASIC is implemented and qualified at 50 MHz, with 31.52%
> non-filler core utilization. See [current measured results](project_status.md).
> The second-engine and SRAM estimates below retain their 2026-10-20 context;
> they are not measurements of an implemented SRAM design.

# Area budget for two PIO engines and SRAM

Assessment: 2026-10-20. Baseline: commit `b380b867fb49dfa43f5ff2690f182e17479a2371`,
IHP SG13CMOS5L, 8x4 tiles, 20 ns clock target.

**There is enough area headroom to start the architecture work.** A second
engine is a reasonable next step. SRAM capacity and port/latency contracts need
to be chosen before committing to the final memory architecture. The current
design has a slow-corner setup warning, so area fit must not be called 50 MHz
timing closure.

## Measured physical baseline

Source: [GDS build log](https://github.com/shanebri/JaneStreet-protocol-emulator-ASIC-competition/actions/runs/39379346181/job/118484607674)
and [layout render](https://shanebri.github.io/JaneStreet-protocol-emulator-ASIC-competition/gds_render.png).
The logs, rather than colored-pixel coverage, establish utilization.

| Measurement | Value |
| --- | ---: |
| Design block footprint | 1724.16 x 710.64 um |
| Block area | 1,225,257.06 um2 / 1.225257 mm2 |
| Core bounds | (2.88, 3.78) to (1721.28, 706.86) um |
| Core area | 1,208,172.67 um2 / 1.208173 mm2 |
| Synthesized mapped cell area | 148,888.79 um2 |
| Routed cell area before filler, including clock/repair/antenna cells | 185,105.09 um2 / 0.185105 mm2 |
| Non-filler cells | 12,652 |
| Non-filler core utilization | 15.32% |
| Filler area | 1,023,067.58 um2 / 84.68% |

The final filler-inclusive cell total equals the core area. That does not mean
the design uses 100% of its logic budget. `PL_TARGET_DENSITY_PCT=60` is a placement
setting, not the measured occupied fraction and not a guaranteed expansion limit.
Filler regions can be reclaimed when the design is placed again.

GDS generation, precheck and viewer succeeded. All **27/27 functional gate-level
tests passed**. The gate job failed afterward because the upstream action's
`grep failure results.xml` matched a passing testcase name; see
[test/README.md](../test/README.md#gate-level-ci-result-naming).
The gate simulation uses `FUNCTIONAL` cell models; it is not an SDF timing test.

After the testcase rename, `./test/run.ps1` passed the FIFO, exhaustive host/pad
unit tests and all 27 pin-level RTL tests locally. The generated `results.xml`
also passes the upstream literal-substring check. Restoring the old name in that
report reproduces the false rejection with no failing XML elements; injecting a
real `<failure>` element still triggers rejection. RTL and test assertions were
not changed. A new remote gate-level/physical run has not been performed for this
local patch; the 27/27 gate-level evidence above is from the existing baseline run.

The physical flow explicitly warns about setup violations at
`nom_slow_1p08V_125C`. Its final checker reports no hold violations. Detailed
worst slack and critical paths have not been extracted in this assessment; they
are in the `GDS_logs` artifact under `55-openroad-stapostpnr/`. The green build
therefore does not establish timing closure across all supplied corners.

## A second engine

Doubling the entire present routed non-filler design gives approximately
**0.370210 mm2, or 30.64% of the current core**. This intentionally duplicates
even the present host/pad overhead and keeps both copies of the existing small
instruction/FIFO memories. It is a planning estimate, not a synthesized
two-engine result or a bound on interconnect and timing-repair overhead.

Give each engine independent PC, X/Y/OSR/ISR, divider, delay/stall state and TX/RX
queues. For the first version, keep separate deterministic instruction stores.
Share the external host transport and pad layer through explicit selection and
per-pad ownership. Engine selection must preserve byte/word atomicity; changing
it must not retarget half a host transaction. Define synchronized start, IRQ
communication, reset/abort behavior and conflict handling before implementation.
Avoid a general crossbar unless a workload needs it.

Two engines increase concurrency, not the number of package pins or the aggregate
host throughput. The present host needs at least 16 clocks per 32-bit word, or
20 including the selector: 2.5 Mword/s at 50 MHz with selector overhead, shared
by both engines and both traffic directions. SRAM can absorb bursts; it cannot
fix a sustained host service deficit. See the
[transport contract](pio21_contract.md#ownership-and-transport).

## SRAM candidates checked against this build's PDK

The build installs IHP-Open-PDK revision
`2bbec755dc67ca3db0261c3d6163e15735d66710`. At that revision,
[`sg13cmos5l_sram`](https://github.com/IHP-GmbH/IHP-Open-PDK/blob/2bbec755dc67ca3db0261c3d6163e15735d66710/ihp-sg13cmos5l/libs.ref/sg13cmos5l_sram)
is a symlink to `../../ihp-sg13g2/libs.ref/sg13g2_sram`. Thus there are SRAM views
in the exact installed PDK; this is not an assumption based on a different process.
No SRAM macro has yet been instantiated or physically validated in this project.

The following dimensions are from the official LEF views at that revision:

| Single-port macro | Capacity | Width x height, um | Area, mm2 |
| --- | ---: | ---: | ---: |
| [64x16](https://github.com/IHP-GmbH/IHP-Open-PDK/blob/2bbec755dc67ca3db0261c3d6163e15735d66710/ihp-sg13g2/libs.ref/sg13g2_sram/lef/RM_IHPSG13_1P_64x16_c2.lef) | 128 bytes | 236.80 x 64.36 | 0.015240 |
| [512x16](https://github.com/IHP-GmbH/IHP-Open-PDK/blob/2bbec755dc67ca3db0261c3d6163e15735d66710/ihp-sg13g2/libs.ref/sg13g2_sram/lef/RM_IHPSG13_1P_512x16_c2_bm_bist.lef) | 1 KiB | 236.80 x 191.34 | 0.045309 |
| [1024x32](https://github.com/IHP-GmbH/IHP-Open-PDK/blob/2bbec755dc67ca3db0261c3d6163e15735d66710/ihp-sg13g2/libs.ref/sg13g2_sram/lef/RM_IHPSG13_1P_1024x32_c2_bm_bist.lef) | 4 KiB | 416.64 x 336.46 | 0.140183 |

For scale, two 512x16 IMEM macros (one per engine) plus one shared 1024x32 DMEM
macro occupy **0.230801 mm2**. Adding the doubled logic estimate yields
**0.601011 mm2, or 49.75% of core area**. No credit is taken for removing the
old flip-flop IMEMs. The standard-cell portion would occupy about 37.88% of the
core remaining after those macro rectangles are removed.

All three macro rectangles can geometrically fit side by side within the current
1718.4 x 703.08 um core. Illustrative 10 um halos around each increase the total
macro reservation to about 0.264189 mm2, leaving about 0.944 mm2 for cells and
routing. Those halos are an assumption, not a validated PDN/routing requirement.
Wrappers, arbitration, pin access, routing blockages and timing repair are extra.
Giving each engine its own 4 KiB DMEM instead raises the raw cells-plus-macros
estimate to **61.35%**, before those extras. That is a different, tighter budget.

## Architectural work needed before memory RTL

- **IMEM timing:** the existing 32x16 store has combinational instruction and host
  read paths. The PDK SRAM model samples addresses on a rising clock edge. A direct
  swap changes execution timing. Define next-address/prefetch behavior for taken
  branches, wrap, EXEC, stalls, START and host writes, and prove the intended
  one-instruction-per-tick contract with cycle-exact tests. Separate per-engine
  macros avoid contention between simultaneous fetches; a shared single port
  cannot service two independent fetches each core clock without a new scheme.
- **IMEM addressing:** PC, ENTRY, wrap and encoded JMP targets are five bits.
  Making 512 words reachable needs an explicit banking/addressing and host-map
  extension. Larger SRAM alone does not increase executable program capacity.
- **DMEM meaning:** there is currently no general DMEM or LOAD/STORE ISA. Decide
  whether the first SRAM is packet/FIFO backing storage or directly addressed
  engine memory. Define access latency, host/engine ownership, port arbitration,
  backpressure and simultaneous accesses. A shared single-port DMEM supplies
  one addressed access per memory clock, not one per engine plus the host.
- **Memory semantics:** keep X/Y/OSR/ISR in registers. Preserve FIFO old-head and
  full/empty rules with explicit buffering; the candidate SRAM's write-through
  behavior cannot be assumed to reproduce them. Contents are uninitialized and
  volatile; reset should invalidate metadata rather than clear every SRAM bit.
- **Physical integration:** provide functional models, Liberty corner mappings,
  LEF/GDS/CDL views, macro placement, power connections and BIST/control tie-offs.
  Verify synthesis preserves the macros and stream-out includes them. Run DRC,
  LVS, timing and gate-level tests on the actual macro-integrated build.

## Recommended order

1. Keep this measured 8x4 baseline and obtain the slow-corner critical-path/slack
   reports before freezing the new timing contract.
2. Add the second engine with existing deterministic IMEM and independent queues;
   measure its actual area/timing and verify simultaneous protocol activity.
3. Integrate a small DMEM/packet SRAM behind a defined buffered interface and
   validate a real macro through the complete physical flow.
4. Move IMEM to SRAM once fetch timing and the larger address/ISA contract are
   specified. Reserve one fetch bank per engine if independent full-rate execution
   remains a requirement.

This sequence starts the requested architecture updates with ample measured area
headroom while making SRAM latency and existing slow-corner timing explicit design
inputs. The budget supports starting work; final fit requires the updated netlist
and macro floorplan.
