# Dual-PIO I/O timing investigation

Assessment date: 2026-10-21. Design: `37c74dc17c3803d30d7b225aa51da10f0809330c`.

## Decision

The measured worst setup path is **reset release through host command/control logic to engine 1's ISR**, not an identified slow host data transfer or instruction shifter. All **821 listed failing setup endpoints have `rst_n` as their selected worst startpoint**. Check reset sequencing and operating-mode constraints before changing execution latency.

This does **not** establish that all failures are false, or that ordinary host/register paths meet timing once reset is excluded. The present reset is synchronous for internal state, while pad output enables also have combinational reset gating. A blanket reset false path would hide behavior that still needs qualification.

The next implementation is a measured sequence: establish a reset/host timing contract; replay separate reset, operational, per-port and register-only queries; repair control distribution and electrical violations; then introduce a registered command boundary only if needed. See [the implementation plan](io_timing_implementation_plan.md).

## Evidence and scope

- [GitHub Actions build 39495891524](https://github.com/shanebri/JaneStreet-protocol-emulator-ASIC-competition/actions/runs/39495891524), [physical job](https://github.com/shanebri/JaneStreet-protocol-emulator-ASIC-competition/actions/runs/39495891524/job/118880709112).
- [GDS_logs artifact 12307955521](https://github.com/shanebri/JaneStreet-protocol-emulator-ASIC-competition/actions/runs/39495891524/artifacts/12307955521), 251,285,023 bytes. Download SHA-256 verified as `a81d874ee1a4e65360ed533e6b86530e3d685aa13a0d4e6434cf035e7f517e23`.
- LibreLane `3.1.0.dev3`; IHP SG13CMOS5L PDK `2bbec755dc67ca3db0261c3d6163e15735d66710`; clock target 20 ns.
- Examined all three post-route corners' `max.rpt`, the slow-corner checks/violator list, effective SDC, resolved configuration, and routed netlist. Parsed 1,000 detailed setup paths per corner and mapped the worst endpoint back to its RTL state.
- Compact source evidence and arithmetic are retained in [timing/37c74dc](timing/37c74dc/README.md). The full ZIP and extracted reports are local ignored build products under `test/sim_build/timing_review_37c74dc/`.
- These are **analyses of the completed build's STA**, not a new STA run. This machine has no OpenSTA/OpenROAD/Docker executable on PATH and WSL is not installed. The diagnostic [replay script](../tools/timing/report_io_paths.tcl) was prepared and syntax/control-flow checked, but not executed by a timing engine. No altered-constraint slack, RTL fix, new physical result, or timing closure is claimed.
- The 39 functional gate-level tests passed using `FUNCTIONAL` models. They do not check analog delay or reset release metastability.

## Measured baseline

All times below are ns. These are the flow's reported summary values, with the register-path caveat below.

| Metric | Slow 1.08 V / 125 C | Typical 1.20 V / 25 C | Fast 1.32 V / -40 C |
| --- | ---: | ---: | ---: |
| Worst setup slack | -5.885337 | +2.427593 | +7.069545 |
| Setup TNS | -2071.482472 | 0 | 0 |
| Listed setup violations | 821 | 0 | 0 |
| Worst hold slack | +0.646020 | +0.301122 | +0.112777 |
| Listed hold violations | 0 | 0 | 0 |
| Max slew violations | 19 | 0 | 0 |
| Max capacitance violations | 1 | 1 | 1 |
| Max fanout violations | 178 | 178 | 178 |

The slow-corner summary labels register-to-register setup slack as +2.705184 and lists zero register-to-register setup violations. **Do not use that field as an independent certificate for every register-launched path.** Detailed reports select endpoint-worst paths, and reset can hide a different launch path to the same endpoint. The current upstream [LibreLane corner reporting code](https://github.com/librelane/librelane/blob/main/librelane/scripts/openroad/sta/corner.tcl) classifies paths after an endpoint-based search; it is a source-level warning about interpretation, not a verified copy of this build's packaged script. The archived fast/typical summary even reports register setup as N/A. Explicit `-from` register-clock-pin / `-to` register-data-pin queries are required.

Similarly, all 821 entries being reset-launched means reset wins those reported endpoints; it does not prove there are no failing host or register paths behind them. `max.rpt` contains only the first 1,000 paths per group. The separate slow-corner violator list contains the same 821 reset-origin entries.

### Why the build was green

The resolved configuration has `TIMING_VIOLATION_CORNERS=["*typ*"]`, `SETUP_VIOLATION_CORNERS=null`, `HOLD_VIOLATION_CORNERS=["*"]`, and `MAX_SLEW_VIOLATION_CORNERS=[""]` / `MAX_CAP_VIOLATION_CORNERS=[""]`. Slow-corner setup and electrical failures were warnings in the build log. A successful GDS job is therefore consistent with these failures. Update acceptance checks once the required corners/modes are agreed; do not interpret green CI as all-corner closure.

## 1. Constraint audit: false violations first

### Constraints actually used

`PNR_SDC_FILE` and `SIGNOFF_SDC_FILE` are null. The archived configuration uses LibreLane's fallback `base.sdc`; the saved final SDC records the following settings. The FPGA-only [janestreet.xdc](../constraints/janestreet.xdc) is not the ASIC signoff constraint file.

| Item | Observed setting | Interpretation |
| --- | --- | --- |
| Clock | `clk`, period 20 ns, propagated | A clock is present; this is not a missing-clock failure. |
| External input delay | 4 ns on every non-clock input, including reset and enable | Derived from the configured 20% of the clock period; not a measured host or reset-release specification. |
| External output delay | 4 ns on all data and OE outputs | A generic external timing budget, not a demonstrated board requirement. |
| Min/max I/O delay | No separate `-min` / `-max` values | The same delay applies to both analyses; earliest-arrival/hold assumptions need review. |
| Input drive model | `sg13cmos5l_buf_4/X`, input transition arguments zero | A modeled upstream driver, not measured PCB input slew. |
| Output load | 0.006 pF on each output | A block-boundary model; do not substitute PCB capacitance without modeling the intervening pad/harness. |
| Clock uncertainty | 0.25 ns | Preserve unless the real clock budget justifies a change. |
| Timing derates | Early 0.95, late 1.05 | Already included in path arithmetic. |
| Exceptions/modes | No false paths, multicycle paths, or case analysis in saved SDC | Reset and asynchronous protocol inputs are treated like synchronous inputs. |
| Sanity checks | No messages after final `check_setup` checks | No reported missing clock/input-delay/loop issue; this does not validate the values or intended operating modes. |

The flow found 142 unannotated drivers; its filter reports **zero remaining after filtering**. Do not describe this as 142 unexplained signal paths without parasitics. Retain that coverage check when replaying STA.

### Reset: strongest candidate for a mode/sequence mismatch

The worst transition is **rising `rst_n`**, i.e. release of active-low reset. The current model permits it to launch 4 ns after a clock edge while internal host/control state takes whichever values maximize propagation.

RTL facts:

- `host_interface` sets `armed=0` and clears its phase state on a sampled reset. A subsequent enabled edge with both strobes low is needed to re-arm.
- The core resets `running=0`, scratch/shift state, and control state on a rising edge with reset low.
- The worst path passes through the `host.armed`-qualified beat logic. After a valid sampled reset, that qualifier is initially zero.
- Internal reset in `protocol_core`, `pio_host_bank`, `pio_fifo`, and the input sampler is synchronous. In the mapped worst endpoint, the cell's asynchronous `RESET_B` pin is tied high; `rst_n` reaches its **D input through logic**.
- `pio_pads` and host output enables also use raw reset combinationally to release external drive.

This makes the worst path a credible **sequentially unreachable reset-release scenario after a correctly sampled reset**, but that has not been formally proven for every affected endpoint or every permitted reset sequence. There is no numerical reset pulse/release/setup contract in the current interface specification. A short reset pulse with no clock, or a reset transition during active traffic, is a different case.

Required evidence before an exception:

1. Define how long reset is held, whether the clock runs during reset, release phase, strobes during release, and the first legal host/engine activity.
2. Prove the reset-to-armed/running sequence under that contract. Check both assertion and deassertion; show no instruction-memory/FIFO write or stale command escapes.
3. Analyze normal operation with reset held inactive in a **separate diagnostic mode**. Keep runtime `ena` behavior unless its stability is separately specified.
4. Keep reset assertion-to-OE release bounded, and check synchronous reset capture/release or any newly introduced synchronizer independently.

`set_false_path -from [get_ports rst_n]` alone is not an acceptable fix. Nor is converting the reset to asynchronous RTL and omitting recovery/removal analysis. Operating-mode case analysis only removes reset transitions from that mode; it does not qualify startup.

### Other possible false-violation sources

| Candidate | Finding / required action |
| --- | --- |
| Missing/wrong clock period | Clock is present at 20 ns. Confirm the system can supply that clock and its uncertainty. No evidence of a missing generated clock; dividers generate enables, not clocks. |
| Generic I/O budget | 4 ns is a fallback, not a validated host contract. Derive distinct min/max input and output budgets from the host launch/capture edges and harness. At unchanged delays, simply removing 4 ns from the worst path would still leave about **-1.885 ns**; this arithmetic is not a rerun. |
| `ena` treated as static | RTL explicitly supports runtime freeze/resume and host phase discard. Do not set it constant merely because the top-level template comment says it is usually high. |
| Asynchronous protocol inputs | Six inputs enter `pins_meta` then `pins_sync`. Consider exceptions only from the asynchronous ports to the first-stage D pins after mapping/CDC review. Keep stage-1-to-stage-2 paths timed and verify synchronizer placement/MTBF assumptions. These ports do not originate any of the 821 listed failures. |
| Multicycle host transactions | A byte taking four clocks does not make every combinational host path four-cycle. The first read beat and final matching write beat have specified single-edge side effects. No blanket host multicycle constraint. |
| `checks.rpt` says `report_checks -unconstrained` | This command also includes constrained paths; the heading does not prove the printed reset path is unconstrained. It has a clock, external delay and setup deadline. |
| Corner coverage | Available analyzed corners are all `nom_*` interconnect with fast/typ/slow cells. Do not claim unrun min/max-RC or other required signoff corners are covered. |

## 2. Worst-path analysis

### Exact path and RTL mapping

```text
rst_n rising
  -> input2 + reset fanout buffer tree
  -> ena/reset/strobe/armed qualification (host beat)
  -> matching WR qualification and selected-engine decode
  -> local/group command combination and control priority
  -> core execute/register-update control
  -> _32168_/D
     Q = pio.engines[1].core.isr[3]
```

The routed netlist establishes `input7` is `ui_in[4]` (WR), `input8` is `ui_in[5]` (RD), `_17300_` combines `ena` and `rst_n`, `_17317_` includes `host.armed`, and `_17320_` qualifies WR. `_17347_` incorporates engine selection. The remaining gates combine command/execute control before the ISR data mux. This trace does not pass through the variable shifter as its dominant serial chain. Flattened intermediate gates are shared; the high-level trace describes the logic cone, not a one-to-one naming of every gate as an RTL expression.

See the complete [worst-path excerpt](timing/37c74dc/worst_reset_setup.rpt), [netlist excerpt](timing/37c74dc/netlist_excerpt.v.txt), and [host](../src/host_interface.sv), [subsystem](../src/pio_subsystem.sv), [core](../src/protocol_core.sv) RTL.

### Timing budget

| Component | ns |
| --- | ---: |
| External input delay | 4.000000 |
| Modeled input-driver contribution at port | 0.003887 |
| 26 buffer cell arcs | 12.972890 |
| 22 other combinational cell arcs | 9.103974 |
| Explicit net/interconnect increments | 0.338129 |
| **Data arrival** | **26.418880** |
| Next clock edge | 20.000000 |
| Capture clock insertion | +0.970663 |
| Clock uncertainty | -0.250000 |
| Library setup requirement | -0.187122 |
| **Data required** | **20.533543** |
| **Setup slack** | **-5.885337** |

Rounding at printed precision accounts for the last few picoseconds/decimal places. The data path has **48 cell arcs**. Of the approximately 22.419 ns internal delay, buffers account for 57.9%, other cells 40.6%, and explicit net delay 1.5%.

**This is not mainly a long-wire flight-time problem.** It is a deep control path with expensive distribution/loading. However, cell arc delay depends on input slew and load, including wire capacitance: 1.5% explicit net delay does not mean placement/routing can affect only 1.5% of the path. The buffer tree is itself a physical consequence of fanout and placement. None of the 26 buffer instances on this path is named as a hold-repair delay cell; do not assume removing hold buffers will fix it.

Examples on the path include `_18524_/Y` with 0.139521 pF load, 1.344855 ns slew and 1.177684 ns arc delay, followed by another two buffer levels. The first reset distribution stages also drive significant load. Localizing/duplicating control and improving drive strength should be evaluated before pipelining the instruction datapath.

The slow-corner pre-PnR WNS was already -5.945552 ns. Its similarity to the routed -5.885337 ns supports investigating synthesis/control structure; it is not a controlled comparison because parasitic models and clock treatment differ. Intermediate timing repair reports use the typical corner. Resolved settings include `SYNTH_STRATEGY="AREA 0"`, `RUN_POST_CTS_RESIZER_TIMING=true`, and `RUN_POST_GRT_RESIZER_TIMING=false`.

### Scope of affected state

The 821 failing endpoint winners include both engines' scratch/shift registers, PC/control state, RX FIFO words, some TX FIFO words, and output/direction state. Their common origin is reset-qualified control. They are not 821 unrelated arithmetic failures. SRAM alone will not remove this reset-to-command path, and adding more shared command consumers could make distribution worse.

## 3. Electrical violations are separate work

The slow-corner [electrical excerpt](timing/37c74dc/electrical_checks.rpt) contains:

- **19 slew checks**. Worst pin `fanout1733/A`: 3.159569 ns against 2.507400 ns, a 0.652169 ns excess. Several entries are different pins on the same slow net, not 19 independent logic cones. Sources include `_24087_/Y` (host address decode) and `_23157_/Y` / `_23287_/Y` (engine 1 TX FIFO write-selection logic).
- **One capacitance check in every corner**. `_17109_/Y`: 0.310998 pF versus 0.300000 pF, excess 0.010998 pF. It is an inverter downstream of `uio_in[0]`, not the package output pad. Trace and localize its internal distribution before changing the external load model.
- **178 fanout checks**, of which 171 are clock-buffer outputs and 7 are other outputs. The printed effective fanout limit is 8 on these cells although the global configuration says 10. Respect the effective library/design constraint; do not raise the global limit to conceal violations. Review CTS leaf sizing/clustering and non-clock replication separately.

Reset case analysis might remove some timing paths, but it does not physically remove these nets or validate their drive quality. All electrical fixes require another routed build and fast-corner hold review.

## 4. Architectural implications

1. **Separate host admission from distributed command execution.** Direct combinational dependencies from external control/reset into every engine must not grow with SRAM, DMA, or more engines. Prefer local registered commands when measured paths require them, with an explicit accepted-edge/commit-edge contract.
2. **Localize decode and control.** Decode per-bank/per-engine command intent and final register enables without an unnecessarily serial global priority chain. Duplication costs area but may shorten control distribution. Synthesis must be checked for merging those cones back together.
3. **Keep pad-release safety local.** Raw reset may still need an immediate output-enable kill even if execution uses a synchronized/registered release. Data, direction, open-drain and ownership must remain coherent at the pad boundary.
4. **Avoid an instruction-pipeline change as the first fix.** The identified path is control-launched. A pipeline would alter branches, EXEC, one-tick instructions and protocol waveforms without first establishing that it addresses the limiting path.
5. **Use the available area for timing where justified.** Current routed non-filler area is 0.369174 mm2, 30.56% of the 1.208173 mm2 core. Control duplication, buffering and small command registers are plausible candidates. No timing or area savings have been measured for them yet.
6. **Do not sign off future SRAM against this baseline summary alone.** Require independent host, register, pad-data, pad-OE, reset-release and SRAM-port timing reports at each architectural milestone.

## Remaining decisions

The following cannot be inferred from passing RTL tests: the external host's launch/capture edges and min/max delays; actual reset generation and release sequence; allowed reset/enable latency; Tiny Tapeout harness timing/load requirements; whether an additional command cycle is acceptable; and the required PVT/RC signoff set. The implementation plan gives concrete experiments and acceptance criteria without silently choosing those contracts.
