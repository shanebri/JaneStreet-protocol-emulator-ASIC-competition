> Historical checkpoint or task record. Status statements and next steps below
> apply to the named revision/date. See [current project status](project_status.md)
> for the qualified dual-engine build and remaining hardware work.

# Phase C: isolated terminal-NOR sizing

Date: 2026-10-26 (America/Phoenix). Branch: `codex/timing-phase-c-nor-sizing`.
Repository baseline: `d4b0bd5508124b4bb0ce0c3092272842f1a3c760`.
RTL and physical archive baseline: `85506c60783641f7f0a14e13a7e099c9a9b9603f`.

## Hypothesis and patch

Implement the smallest mechanism test from
[the approved hypotheses](timing_hypotheses_20261025.md): increase only the
measured terminal driver `_23246_` from `sg13cmos5l_nor4_1` to
`sg13cmos5l_nor4_2`. The archived slow path reports 0.178745 pF load,
3.561205 ns cell delay and 4.579258 ns output slew at that NOR. A stronger
driver may reduce its delay and the receiving flop's slew-dependent setup
penalty. Increased input capacitance or a changed route may erase the benefit;
competing paths can dominate even if this arc improves.

This is a physical experiment; no RTL or production configuration changes.
20 ns, both engines, one-cycle retirement, 8x4 allocation, pinout, constraints,
models and acceptance checks remain unchanged. No pipeline or timing exception.

`physical_trial.py --trial nor_size` inserts the isolated sizing/legalization
step before global routing. `--trial nor_control` inserts the identical step
without the master replacement. Both resume the **same** archived
`38-openroad-stamidpnr-2/state_out.json`, with eight OpenROAD threads. Both
rerun global routing, antenna repair, detailed routing, extraction and final
three-corner STA. The old post-global-route control is historical context;
this new matched control is the primary A/B comparator.

These are explicitly post-route screening runs. The runner stops after
`OpenROAD.STAPostPNR`, then invokes the unchanged `check_signoff.py` and
preserves its rejection output. DRC/LVS/GDS/precheck and final gate-level
verification remain required before any future acceptance, even if this screen
passes. `screen_complete` never means fabrication qualification.

## Reproduction

Inside the existing Ubuntu-24.04 environment:

```sh
cd /home/shane/eda/librelane-3.1.0.dev3
nix develop --offline --command python3 \
  /mnt/c/Users/shane/Projects/JaneStreet-protocol-emulator-ASIC-competition/tools/timing/physical_trial.py \
  --archive-root /home/shane/eda/timing-20261024/current \
  --pdk-root /home/shane/eda/pdk-2bbec755 --threads 8 --trial nor_size \
  --out /mnt/c/Users/shane/Projects/JaneStreet-protocol-emulator-ASIC-competition/test/sim_build/phase_c/nor-size-01
# Same command with --trial nor_control and a distinct nor-control-01 output directory.
```

Output directories must be new. `experiment.json` records the state/config/script
hashes and physical change separately from the shared execution override.
The original OpenROAD command is `replace_cell`; its physical-database update
is asserted before legalization and export.

Pinned environment: LibreLane 3.1.0.dev3 (`ca6adb1e2982cd75445a68b632d461213d8ca421`),
PDK `2bbec755dc67ca3db0261c3d6163e15735d66710`, OpenROAD
`dcf36133a369abc8f3c5e5738cd4d82e4903c0e0`, OpenSTA 2.7.0,
Yosys 0.66 (`86f2ddebce7e98ce7cacc27e8a5c14cb53b51b51`), Verilator 5.046.
The environment was recovered successfully through WSL; older statements that
WSL/tools were unavailable do not describe this session.

## Functional and structural checks

- Verilator lint: exit 0 with existing warnings under `-Wall -Wno-fatal`.
- Yosys generic synthesis, hierarchy, `check -assert`, and no-latch selection:
  exit 0. This is structural verification, not physical timing evidence.
- Complete `test/run.py`: 39 cocotb tests passed, zero failures/skips;
  FIFO/frontend/host/pad/subsystem units and three Python host tests passed.
- Timing-tool tests: 21 passed, including three new fail-closed NOR audit tests.
- Differential: 27,391 cycles against frozen 37c74dc and separately 27,391
  against frozen immediate pre-change 85506c6. Both engines' internal state,
  FIFOs, retained IMEM, exact host edges, IRQs, pads and reset/enable are checked.
  The immediate reference SHA-256 is
  `3c4c3d338caaa86f827d1b7d0921a44a0a74cbd1488d0327dd77bc7e68e7e6b6`.
- All three FPGA regressions passed, including 512 SPI transactions.
- `audit_nor_trial.py` compared all **25,205** exported instances and the rest
  of the netlist: only the intended master changes; every named pin connection
  is preserved. The PDK NOR functional model bodies are identical. This audit
  permits port-list reordering but rejects rewiring or any second change.

The first sandboxed Windows regression failed on temporary-directory access;
the complete rerun with normal tool access passed. No assertion was waived.
The final tool-test rerun also passed with a workspace-local temporary directory.

Local logs: `test/sim_build/phase_c_rtl_regression_unrestricted.log`,
`phase_c_{fpga,spi,i2c}_unrestricted.log`, and
`test/sim_build/phase_c/{verilator,yosys,differential_85506c6}.log`.
The topology audit is `test/sim_build/phase_c/nor_topology_audit.json`.

## Physical decision

An additional **fixed archived SPEF sensitivity diagnostic** isolates the
electrical effect before the new routes finish. It reads the original routed
netlist/SPEF/SDC, then applies only `replace_cell _23246_ sg13cmos5l_nor4_2`
in OpenSTA. It neither reroutes nor re-extracts; these values are **not newly
routed signoff results** and must not fill the physical acceptance table.

| Fixed-SPEF diagnostic | Slow | Typical | Fast |
| --- | ---: | ---: | ---: |
| Original setup WS (ns) | -6.809803 | 2.992410 | 7.564806 |
| Sized-NOR setup WS (ns) | -4.759954 | 4.214398 | 8.305861 |
| Change (ns) | +2.049849 | +1.221988 | +0.741055 |
| Hold WS, unchanged (ns) | 0.666255 | 0.314691 | 0.122530 |

The same slow worst endpoint remains `_33839_/D`. At unchanged 0.178745 pF
wire load, the NOR output arc changes from 3.561205 to 1.830600 ns, with slew
changing from 4.579258 to 2.356737 ns. The diagnostic supports the mechanism
but still fails setup. It cannot predict the result of changed legalization,
routing, extraction or competing paths. Logs and six detailed report sessions
are in `test/sim_build/phase_c/fixed_spef_sensitivity/`.

Both routed screens completed. The unchanged control reproduces the archived
baseline setup/hold/electrical metrics exactly. The resolved configurations
differ only in `PIO_SIZE_TERMINAL_NOR=false/true`; the state, custom-step hash
and execution settings match. Both strict post-route gates reject their actual
`18-openroad-stapostpnr/state_out.json`.

| Metric | Matched control | Sized NOR | Change | Candidate |
| --- | ---: | ---: | ---: | --- |
| Slow setup WS (ns) | -6.809803 | -5.992693 | +0.817110 | FAIL |
| Slow setup TNS (ns) | -979.921111 | -1006.726990 | -26.805879 | FAIL |
| Slow failing setup endpoints | 616 | 632 | +16 | FAIL |
| Slew violations, slow/typical/fast | 55 / 4 / 0 | 59 / 6 / 0 | +4 / +2 / 0 | FAIL |
| Cap violations per corner | 0 | 0 | 0 | PASS |
| Fanout violations per corner | 183 | 178 | -5 | FAIL |
| Standard-cell area excluding filler (um2) | 369414 | 369365 | -49 | INFO |
| Routed standard-cell utilization | 30.5762% | 30.5722% | -0.0040 percentage points | INFO |

Area uses `design__instance__area__stdcell`, not the filler-inclusive total
`design__instance__area` (which is approximately the core area after filling).
Both runs have zero setup violations at typical/fast corners, zero hold
TNS/counts, zero filtered annotation gaps and zero latch/unmapped/synthesis
check errors. Candidate hold WS remains positive: 0.669025 / 0.313078 /
0.117578 ns. Candidate typical/fast setup WS is 3.234703 / 7.670321 ns.
Detailed-router DRC count is zero; this does not replace Magic DRC/LVS/precheck.

### Mechanism and decision

The targeted path to `_33839_/D` improves to **-3.965280 ns** after routing.
Its replaced NOR now sees 0.120348 pF, with 1.301205 ns cell delay and
1.599250 ns output slew. This is a real local improvement, stronger than the
fixed-SPEF sensitivity; route changes also altered the extracted load.

The global worst migrates to `_33835_/Q` -> `_33838_/D`, through
`_23227_/Y` (`sg13cmos5l_nor3_1`): 0.173072 pF, 2.579140 ns cell delay,
3.310848 ns output slew. Arrival is 25.959305 ns versus 19.966612 ns required.
The unchanged upstream address/control family and another weak terminal driver
still dominate. Sizing one endpoint cannot repair this distributed family.
The routed global WNS gain is smaller than the fixed-SPEF gain because the
limiting endpoint changes; aggregate TNS, endpoint count and slew get worse.

**Reject the one-cell sizing candidate as a production optimization.** Retain
its isolated recipe and evidence only. No production source or physical setting
is adopted. Classification: **failed repair experiment with measured local/WNS
improvement; no timing closure or fabrication qualification**.

The next independent experiment should enable timing-driven placement from the
original synthesis result with unchanged optimization views, then separately
test the existing slow-corner placement view. This targets the whole distributed
control family before routes are fixed. Do not combine these changes or carry
this rejected NOR ECO into their control. If electrical ECO work continues,
`_23227_` is the newly measured driver to investigate; it is not automatically
approved as a useful isolated fix by the present result.

All-corner comparison and compact evidence are in
[`timing/20261026/comparison.md`](timing/20261026/comparison.md). Actual local run directories are
`test/sim_build/phase_c/{nor-control-01,nor-size-01}/`; their strict outputs are
`post_route_signoff.log`. Independent register/per-port/reset-mode replays
completed **18 sessions** (three corners, three reset modes, two designs), with
no reported issues in any constraint-coverage report. Reset case analysis is
diagnostic only; production signoff includes dynamic reset. The slow dynamic
reset paths remain positive: rise/fall 2.933042 / 3.106177 ns for the candidate.
Host input paths still fail: `ui_in[0/1/2]` are -3.379167 / -4.265632 /
-3.860059 ns. These improvements do not establish host timing closure.
The session summaries and endpoint evidence are in
[`targeted_paths.json`](timing/20261026/targeted_paths.json); original
netlist/SPEF/SDC and six cell-library hashes are in each replay manifest.
Source hashes and the production-diff check are in `source_provenance.json`.
DRC/LVS/GDS/precheck and final gate-level tests
were not completed for this rejected screen, so none is claimed as passing.
