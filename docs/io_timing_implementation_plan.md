# I/O timing implementation plan

Date: 2026-10-21. Baseline: `37c74dc17c3803d30d7b225aa51da10f0809330c`.
Status: **first local-control experiment implemented and functionally validated;
new routed timing/electrical qualification pending**. See the
[implementation record](io_timing_implementation.md) for delivered work and
remaining acceptance gates. The original baseline evidence below is retained.

Read the [evidence report](io_timing_report.md) first. The measured -5.885337 ns path is rising `rst_n` through host/control logic to engine 1 ISR[3]. The first task is deciding whether that transition/state combination is legal, not assuming a 5.8 ns instruction-datapath deficit.

## Deliverables and order

| Stage | Deliverable | Exit condition |
| --- | --- | --- |
| A | Explicit reset, host and pad timing contract | Every exception or budget has a system-level justification. |
| B | Baseline and operational targeted STA | Baseline reproduces; hidden host/register/pad paths are exposed. |
| C | Constraint-only changes, if justified, plus electrical/physical experiments | All required modes remain covered; actual improvement measured. |
| D | Local control restructuring | Cycle semantics preserved and routed timing improves. |
| E | Registered host-command boundary, only if necessary | Latency/version contract and backpressure are explicit; full regression passes. |
| F | Closure checks and architectural expansion | Required timing/electrical checks pass for the new netlist and interface. |

Stages are separate changes so their effects remain attributable. Do not combine reset exceptions, a new pipeline, new SRAM and a new host protocol in one timing experiment.

## A. Resolve the interface contract before editing SDC

Record decisions in `docs/pio21_contract.md` / `docs/info.md` and a dedicated reset section:

| Question | Why it matters | Proposed starting point, subject to system confirmation |
| --- | --- | --- |
| Is reset synchronous to clk? Is clk running while reset is low? | Current internal resets are synchronous and need sampled low edges. | Require clocked reset assertion for a documented minimum interval. If reset is asynchronous in the system, design a release synchronizer rather than pretending it meets synchronous setup. |
| When can RD/WR assert after reset release? | The worst reset path traverses armed host logic. | Both strobes low across reset and through an explicit re-arm edge; no command before ready. Prove this matches existing host drivers. |
| Is immediate OE release required? | Raw reset currently releases bidirectional pads combinationally. | Preserve asynchronous disable at the boundary and specify a maximum release delay separately. |
| Can `ena` change at runtime? | Existing freeze/resume/phase-discard behavior is visible. | Keep it timed and dynamic; no default case-analysis exception. |
| What are host launch and sample edges? | Determines input arrival and output deadline. | Use actual controller/harness timing; define earliest and latest values separately. |
| Is one extra command cycle acceptable? | A registered command changes START, FIFO and read snapshot timing. | Prefer the current contract initially; version any necessary change. |
| What are the signoff corners and pad models? | Current run includes nominal RC only and warning-only electrical checks. | Confirm competition/harness requirements; archive a named required set. |

For an edge-aligned synchronous host, derive input max/min from the host's max/min clock-to-out, interconnect delay and clock relationship. Derive output setup/hold requirements from the receiving host and interconnect, using the SDC sign convention (output min may be negative). Include uncertainty/skew once, not in both the I/O delays and clock uncertainty without justification. The present generic 4 ns min/max is not a measured result.

For asynchronous PIO inputs, identify exactly the six first-stage synchronizer D pins after synthesis. Any asynchronous-input exception stops there. Preserve timing from first to second stage, input sampling latency, qualifier behavior and CDC physical checks.

### Reset disposition options

**Option A1: Keep the current externally synchronous reset contract.** Prove the sampled-reset/idle/re-arm sequence makes the long release path irrelevant to active state updates. Use a normal-operation mode with reset inactive plus separate reset assertion/release qualification. Add only narrowly justified exceptions; do not erase reset-to-OE checks. If first-cycle reset capture is required, retain its D-path checks.

**Option A2: Explicitly synchronize reset release.** Use a reviewed asynchronous-assert/synchronous-release structure where required, local release distribution, and a ready/quarantine interval. Raw assertion still kills OEs. The operational reset must not race into command logic. This changes startup latency and potentially register-reset behavior, so specify clock-stopped behavior, reset pulse width, recovery/removal, metastability assumptions and first legal transaction. Do not add an ordinary two-flop data synchronizer to all host bits independently; it would lose bus coherence.

Neither option has been selected or proven by this report. Current synchronous RTL must not be constrained as if A2 were already implemented.

## B. Targeted timing replay

### Inputs and environment

Use the archived GDS_logs for the baseline, the exact PDK revision listed in the report, and the original LibreLane/OpenSTA environment. Extract the ZIP into a fresh analysis directory. Keep these together:

```text
runs/wokwi/52-openroad-fillinsertion/tt_um_shanebri_top.nl.v
runs/wokwi/54-openroad-rcx/nom/tt_um_shanebri_top.nom.spef
runs/wokwi/final/sdc/tt_um_shanebri_top.sdc
runs/wokwi/55-openroad-stapostpnr/config.json
runs/wokwi/55-openroad-stapostpnr/nom_slow_1p08V_125C/_env_ThreadPoolExecutor-4_1.tcl
```

The saved step environment records the first two files as the actual netlist/SPEF inputs. Final SDC is the frozen constraint snapshot for replay; signoff itself used the fallback script. Reproducing the original slack is mandatory before treating a replay as equivalent. Do not source the archived environment unmodified on another machine: it contains the runner's absolute paths.

The supplied [report_io_paths.tcl](../tools/timing/report_io_paths.tcl) loads those artifacts, Liberty models and SDC, then reports the exact ISR endpoint, reset assertion/release paths, each input, each output, and separately restricted register-to-register paths. It does not modify RTL, place/route a design, or establish a new production constraint mode.

Example in the matching Linux timing environment, from the repository root:

```bash
export PIO_TIMING_RUN="/absolute/path/to/extracted/runs/wokwi"
export PDK_ROOT="/absolute/path/to/pdk-parent"
export PIO_TIMING_CORNER="nom_slow_1p08V_125C"
export PIO_TIMING_MODE="baseline"
export PIO_TIMING_OUT="/absolute/path/to/reports/slow-baseline"
sta -exit tools/timing/report_io_paths.tcl > "$PIO_TIMING_OUT.log" 2>&1

# New process: operational diagnostic only, with rst_n held at 1.
export PIO_TIMING_MODE="operational"
export PIO_TIMING_OUT="/absolute/path/to/reports/slow-operational"
sta -exit tools/timing/report_io_paths.tcl > "$PIO_TIMING_OUT.log" 2>&1
```

Create the parent report directory before shell redirection. Repeat each mode for `nom_typ_1p20V_25C` and `nom_fast_1p32V_m40C`. The PDK parent must contain `ihp-sg13cmos5l`. Check tool exit status **and** logs for errors/unresolved models; syntax checks on this Windows host do not validate timing-engine execution. Compare baseline worst slack, clock insertion, derates, loads, and annotation with the archive. If they disagree, fix replay provenance before comparing modes. No fresh replay has been run in this assessment.

For an already loaded STA session, the central queries are:

```tcl
# Baseline only: exact worst path and reset polarity, not a global top-N guess.
report_checks -rise_from [get_ports rst_n] -to [get_pins {_32168_/D}] \
    -path_delay max -fields {slew cap input net fanout} \
    -format full_clock_expanded -group_path_count 5

# Must restrict launch and capture before selecting worst paths.
report_checks -from [all_registers -clock_pins] \
    -to [all_registers -data_pins] -path_delay max \
    -fields {slew cap input net fanout} -format full_clock_expanded \
    -group_path_count 30
```

Numerical cell names are valid only for this netlist. Future revisions must rediscover the endpoint by state/net mapping. The script checks the baseline pin exists instead of quietly returning an empty exact-path report.

### Required report matrix

| Query | What it resolves |
| --- | --- |
| Baseline reset rise/fall to ISR and all endpoints | Distinguishes release from assertion and reproduces the current violation. |
| Normal operation, reset held high, enable dynamic | Exposes paths hidden by reset; diagnostic only until reset qualification is complete. |
| Each `ui_in[0:5]` and `uio_in[0:3]` separately | Host address, strobe and nibble timing without reset dominating the search. |
| `ena` separately | Freeze/resume and host phase gating. |
| Register clock pins to register D pins | True restricted register-path search; avoids endpoint-winner classification ambiguity. |
| Each `uio_out`, `uio_oe`, `uo_out` separately | Data and output-enable deadlines, including combinational reset/enable/strobe paths. |
| Setup and hold at every required corner | Prevents a setup fix from breaking the +0.112777 ns fast hold margin. |
| Max slew/cap/fanout plus annotation/sanity | Electrical quality and constraint coverage, not just WNS. |

Save startpoint, endpoint, polarity, slack, input/output budget, clock insertion/uncertainty, buffer delay, other-cell delay, explicit net delay, largest loads and slews. Treat input-driver and clock-path contributions separately. A report with no path needs an explained reason, not a pass stamp.

## C. Low-impact constraint and physical experiments

1. Add explicit project ASIC PnR/signoff SDC only after A is settled. Preserve original effective defaults initially and demonstrate equivalent baseline results. Apply a reviewed correction in its own experiment. Record min/max host delays, reset modes, synchronizer scope, and OE timing obligations.
2. Fix the baseline build's acceptance policy: required setup/hold corners, electrical failures, fanout review, annotation checks. Preserve a baseline artifact showing existing failures before making it a release gate. Do not merely change checker severity to green.
3. Experiment with timing-oriented mapping and slow-corner-aware repair using the installed flow version's supported settings. The baseline maps for `AREA 0`, repairs through CTS, and disables post-global-route timing repair. Confirm which libraries each repair stage actually uses. Timing the slow corner only at signoff can leave an avoidable gap.
4. Examine the 26-buffer worst-path chain. Try stronger legal drivers, local decode replication, and placement locality; compare the actual resulting chains. Recompute fast hold after every sizing/topology change.
5. Repair the `uio_in[0]` inverter load and host-address/TX-write decode slew sources. Review the 171 clock-buffer fanout violations with CTS constraints/library limits. Do not treat clock and data fanout identically or remove buffers indiscriminately.

Acceptance: no semantic RTL change, unchanged justified constraints, lower worst-path delay with no required-corner regression, and measured electrical improvement. A negative-slack result is still an experiment, not closure. Some corrections may require RTL despite ample empty area.

## D. First RTL experiment: localize control while preserving timing semantics

Target files: `src/host_interface.sv`, `src/pio_subsystem.sv`, `src/pio_host_bank.sv`, `src/protocol_core.sv`.

Proposed changes, only after targeted reports confirm the relevant cones:

- Separate decoded command intent from final sequential reset/enable qualification. Avoid feeding the same raw reset-qualified beat through multiple command-priority layers and then through every wide register update.
- Form per-engine START/STOP/RESUME/ABORT and per-bank write/read strobes locally. Express command priority once and use localized register enables; measure whether synthesis preserves locality or shares it back into a deep cone.
- Consider separate control qualification for live host IRQ/debug operations, stopped-state configuration, execution retirement, FIFO transfers, and pad release. Use each register's real update conditions rather than a universal wide mux chain.
- Preserve the accepted edge for first-read snapshot/pop, final-write commit, selection change, group START and FIFO old-head behavior. Preserve `ena=0` behavior, IRQ collisions and abort priority.

**Do not simply delete `rst_n` from `beat`.** Although many sequential blocks have an outer reset branch, instruction memory is deliberately unreset and uses a direct write enable. A reset-edge write could corrupt retained firmware. FIFO data storage/metadata, selected-bank staging and all side effects also need reset/disable qualification. Move guards only with an explicit proof/test for each consumer.

Write equivalence assertions or differential cycle traces for every legal transaction sequence and simultaneous host/engine operation. Then measure mapped path depth, buffering, area and all-corner post-route timing. Merely shortening the source code is not evidence of a faster circuit.

## E. Structural fallback: register accepted commands

If real operational paths still exceed the budget, add a coherent transaction register between the nibble adapter and engine command execution. This is the strongest structural candidate for breaking external-input-to-deep-control paths. It is also a visible transport change unless a proven phase-predecode scheme preserves the accepted edge.

### Suggested transaction contents

Capture valid, selected engine, byte address, operation/read-write kind, complete data, and any selector/context needed at commit. Group commands capture the complete mask and command payload. Avoid consulting live engine selection or mutable host staging a cycle later. Clear/flush pending requests on defined reset/disable/resync events.

An accepted beat at edge N enqueues one coherent request. A subsequent edge commits it once. If there is no spare service cycle, use ready/credits or a proven depth/arrival-rate bound; the existing mandatory gap is not permission to discard events. Prove throughput against the minimum legal beat spacing and engine stalls.

### Contract changes that must be solved

| Behavior | Current contract | Required decision for a registered boundary |
| --- | --- | --- |
| Word write | Commit on final high-nibble edge | Delay all associated state consistently or prove a latency-preserving predecode. |
| First read | Capture byte and perform pop/snapshot on that edge | Return delayed-valid data or stage a response; never return a stale byte. |
| Engine selection | Complete byte-F write selects bank | Subsequent requests capture the correct bank despite queued commands. |
| Group START | Both selected engines start on the same commit edge; first tick follows | One shared commit pulse; preserve inter-engine alignment and document external latency. |
| FIFO full + pop/push | Old head consumed; simultaneous operation may succeed | Queue admission and actual commit must not use stale fullness or duplicate transfers. |
| Abort/reset/disable | Defined release, priority and phase discard | Specify pending-command cancellation and preserve immediate pad-release requirements. |
| Host read direction/OE | Drive only exclusive enabled reads | Keep OE tied to external ownership and valid response; queued work must not extend drive into a write. |

A late final command-select signal can instead select among already computed candidate updates, or a registered predecode can be prepared during a protocol phase. These are possible alternatives to extra latency, not assumptions: address changes, held strobes, phase abandonment and staging atomicity must remain legal. Quantify their mux cost and fanout after synthesis.

A registered boundary does not guarantee +5.885 ns recovery: it splits paths and changes clock/input budgets, while high-fanout register-launched controls may remain too slow. Measure each new stage. Version the transport/capability contract if externally observable timing changes; migrate host wrappers and FPGA loaders together.

## F. Validation and acceptance

### Functional checks

- Existing 39 pin-level RTL and functional gate tests, FIFO/host/pad/subsystem SV tests, Python host serialization, and FPGA UART/SPI/I2C simulations.
- Reset release with correct idle/re-arm sequence; reset assertion during a partial byte/word, first read/pop, final write, group START, FIFO traffic and live pin drive. Include clock-stopped behavior if supported.
- No IMEM writes during reset; program retention; no stale command after disable/resync; no duplicate FIFO operation or wrong-bank commit.
- Group alignment, first execution tick, delayed and stalled instructions, same-edge full FIFO behavior, IRQ collision priority, abort/OE release.
- For a new boundary: min-gap sustained traffic, queue-full behavior, coherent snapshot, selection changes with queued requests, read turnaround and exact latency.

### Physical/timing checks

- On the final RTL/netlist, reproduce setup and hold for every agreed operating/reset mode and required PVT/RC corner. Independent per-port and register-only reports must exist even when the global report is green.
- Target nonnegative WNS and zero TNS/violating endpoints under the agreed constraints, with an explicit engineering margin chosen before signoff. Do not invent a margin after observing results.
- Resolve or formally disposition every max slew/cap/fanout issue; verify clock distribution and reset/enable trees. Passing setup alone is insufficient.
- Keep annotation coverage, no-latch/unmapped checks, DRC/LVS/antenna, and output-data/OE timing. Recheck fast hold after buffering/sizing.
- If asynchronous reset is introduced, include recovery/removal and reset-domain/CDC review. Phase-swept RTL tests are not metastability proof.
- SDF tests can supplement STA for reset/host transitions and waveform-sensitive behavior; the existing `FUNCTIONAL` gate run cannot replace them.

### What to carry into SRAM and further engines

Packet SRAM should connect through registered, bounded-latency request/response paths. Preserve registered FIFO heads and an explicit backpressure contract. Keep SRAM arbitration off the same-cycle pin/retirement critical cone where possible. Local command decode, reset release, queue metadata and group control must scale without global combinational fanout. Larger IMEM and pipelined fetch require their own branch/EXEC timing decision; they are not fixes for the reset control path identified here.

The implementation is accepted only when the chosen reset model is justified, diagnostic replay is reproducible, functional behavior is documented and tested, and the new routed design meets its required timing/electrical checks. Until then the specific area, latency and slack effects of each proposal remain estimates.

## References

- [Baseline report and evidence](io_timing_report.md).
- [LibreLane timing closure](https://librelane.readthedocs.io/en/stable/usage/timing_closure/index.html): project SDC and PnR/signoff separation.
- [OpenSTA reporting command definitions](https://github.com/The-OpenROAD-Project/OpenSTA/blob/master/search/Search.tcl): start/end restrictions and detailed path reporting. Use the build's actual tool version when replaying.
