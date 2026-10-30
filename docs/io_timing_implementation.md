> Historical checkpoint or task record. Status statements and next steps below
> apply to the named revision/date. See [current project status](project_status.md)
> for the qualified dual-engine build and remaining hardware work.

# I/O timing local-control experiment

Date: 2026-10-21. Reference: `37c74dc17c3803d30d7b225aa51da10f0809330c`.
This implements the compatibility-preserving first experiment from the
[plan](io_timing_implementation_plan.md). **Functional validation passed;
50 MHz routed timing closure is not yet demonstrated.**

## Decisions and implemented changes

The system decision for this experiment is to preserve current I/O budgets and
require all three existing nominal-RC corners. Reset option A1 is retained:
externally synchronous state reset, immediate raw-reset OE disable, and one
enabled idle edge after release before a command. The complete contract is in
[pio21_contract.md](pio21_contract.md#reset-and-timing-qualification).
No transport latency/version change, release synchronizer, blanket false path,
case analysis in production, or multicycle exception was added.

The host now exposes decoded write/read **intent** separately from its original
reset-qualified acceptance outputs. Top-level consumers use intent. This removes
raw reset from the host-beat/selection/group-command/retirement priority chain;
each state consumer retains its local dominant synchronous reset. Runtime enable,
arming, matching address/direction and exclusive-strobe qualification remain on
intent. Original standalone host acceptance outputs remain reset-qualified.

Reset-guard audit:

| Consumer | Protection at a reset edge |
| --- | --- |
| Adapter phase/data/read snapshot | Dominant `!rst_n || !ena` branch |
| Engine selection | Dominant `!rst_n` branch |
| Per-bank staging/selectors/snapshot | Dominant `!rst_n` branch |
| Engine state, configuration, IRQ/debug, pad shadows | Dominant `!rst_n` branch |
| Program counter | Dominant synchronous reset in `pc` |
| FIFO words, pointers and level | Dominant `rst || clear` branch includes storage writes |
| GPIO ownership | Dominant `!rst_n` branch |
| Unreset instruction memory | Explicit local `imem_write && rst_n` guard at fetch port |
| Physical host/protocol OEs | Original raw-reset combinational gating |

Thus intent may be high while reset is low, but cannot cause a stored side effect.
Removing reset from `beat` without the IMEM guard would corrupt retained firmware.
Enable remains on intent because the downstream reset branches do not implement
host disable semantics. No queue, delayed commit, stale bank selection or changed
read/pop edge is introduced.

Group and ownership command decode now forms separate per-bank source enables.
Each destination engine receives only its six masked command bits; ownership
receives twelve masked bits. This removes the redundant selected-bank 32-bit
command mux after the byte transaction was already bank-qualified. The engine
still applies the original STOP/ABORT/START/RESUME priority once. Synthesis may
merge controls again; physical benefit requires measurement.

## Timing tools and acceptance

`src/config.json` now requires setup/hold and slew/cap checks at all corners.
The GDS workflow additionally runs `tools/timing/check_signoff.py` on the unique
post-route STA `state_out.json`. It requires all three named corners, finite
nonnegative setup/hold slack, zero TNS and endpoint counts, zero electrical
violations including fanout, zero filtered annotation gaps, and structural
checks. Missing/malformed evidence fails. Running it against the original
archive rejects its slow setup, slew, capacitance and fanout failures as expected.
Future builds can therefore fail until the electrical work is complete.

`tools/timing/replay.py` runs all six reset-inclusive/operational sessions in
separate STA processes, hashes netlist/SPEF/SDC/Liberty/script inputs, saves logs
and a manifest, and refuses to reuse an output directory. With `--reference`,
all three baseline setup/hold results must match the archive within 0.001 ns;
the ISR pin `_32168_/D` is required. Candidate runs omit that historical pin
unless `--target` supplies a rediscovered endpoint. All runs report each input,
output, restricted register paths, separate reset rise/fall setup/hold paths,
electrical violations and annotation/constraint coverage. Keep `ena` dynamic.

In the original Linux LibreLane/OpenSTA/PDK environment:

```bash
python3 tools/timing/replay.py --run /archive/runs/wokwi \
  --pdk-root /path/to/pdk-parent --out /reports/reference --reference
python3 tools/timing/replay.py --run /candidate/runs/wokwi \
  --pdk-root /path/to/pdk-parent --out /reports/candidate
python3 tools/timing/check_signoff.py /candidate/runs/wokwi
```

The matching PDK parent must contain `ihp-sg13cmos5l`, revision
`2bbec755dc67ca3db0261c3d6163e15735d66710`. Use the archive's LibreLane
`3.1.0.dev3` environment. Inspect unresolved-model warnings, input hashes,
clock insertion/derates and annotation in addition to slack reproduction. An
empty reset report in operational mode is expected from case analysis; every
other empty per-port/register report needs an explained disposition. The replay
is diagnostic, not a replacement for the flow's signoff/DRC/LVS checks.

## Validation

| Check | Result |
| --- | --- |
| Existing pin-level regression | 39/39 passed |
| Existing FIFO/host/pad/subsystem SV units | Passed |
| Python host serialization | 3/3 passed |
| New differential reference test | 27,391 cycles passed |
| IMEM-guard mutation check | Removing the guard is detected at cycle 267 |
| New signoff-gate/replay unit tests | 8/8 passed |
| FPGA UART, SPI and I2C simulations | All passed; SPI includes 512 transactions |
| Generic Yosys synthesis | `synth -noabc`, `check -assert`, no-latch check passed |

The differential test uses frozen copies of the four changed behavioral modules
from the reference commit (module identifiers renamed only), with the unchanged
shared modules. It compares pins after edges and between edges, every engine's
architectural/staged state, all FIFO words and pointers, and all 64 IMEM words.
It exercises both banks, reset at all byte addresses with pending write/read/
resync/gap states, group commands, live FIFO traffic, IRQ/configuration/ownership,
disable, minimum-gap transactions and deterministic adversarial traffic.
It runs in `test/run.py`, so CI repeats the comparison without Git history or
network access. These finite traces supplement the existing tests; they are not
a formal proof of all legal transaction sequences.

Local artifacts are under ignored `test/sim_build/io_timing/`; the existing
39-test report is `test/results.xml`. Windows simulator/asyncio checks required
execution outside the sandbox. Generic cells increased from 20,467 to 20,495
(+28); mux cells decreased from 10,541 to 10,508 (-33), and storage counts are
unchanged. Both use the same `synth -noabc` flow. These are generic structural
counts, not physical area or delay measurements.

Additional flattened generic synthesis passed structural checks for both
reference and candidate. A combinational reachability inspection finds reset
removed from the ISR clock-enable cones, but reset can still reach ISR data
through FIFO reset logic. This is not path sensitization or STA; it is further
reason to inspect candidate paths rather than assuming all reset paths vanish.
The Tcl report script's reference/operational/candidate control flow was checked
with command stubs; no timing engine was executed by that check.

## Remaining measured work

OpenSTA/OpenROAD, Docker/WSL and the matching PDK are unavailable locally. No new
baseline STA replay, candidate STA, place/route, electrical repair, functional
gate/SDF simulation, DRC/LVS or measured slack improvement is claimed. The GDS
workflow has been prepared but was not dispatched from this working tree.

The plan's order requires baseline replay and targeted measurements before
accepting RTL/physical experiments. This change is a reviewable candidate for
that experiment, not satisfaction of that measurement prerequisite. Run baseline
replay first, then route the candidate with unchanged budgets and compare its
host/reset/register/OE reports and fast hold. Resolve the input-nibble load,
address/TX decode slew and CTS fanout violations against actual new results.
Only introduce a registered command boundary if those operational measurements
require it; stage E remains conditional and unimplemented. Stage F acceptance is
pending the new physical evidence.
