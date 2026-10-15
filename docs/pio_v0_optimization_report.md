# PIO V0 implementation and optimization report

## Delivered behavior

The ASIC core now executes protocol firmware using 32-bit OSR/ISR and independent
32-bit X/Y scratch registers. TX and RX each have a four-word, 32-bit FIFO.
IN and OUT shift any width from 1 through 32 in either direction. Automatic
threshold-based FIFO transfers, blocking/nonblocking transfers, branch conditions,
decrement loops, pin/IRQ waits, MOV/SET, EXEC, per-instruction delay, optional
side-set, entry point and zero-cost wrap are implemented.

The accumulator architecture and `uart_tx.sv` are removed. Firmware drives all
eight output pins. Two previously unused input pins feed synchronized receive
signals. A new byte-bus map supports atomic 32-bit transfers and coherent read
snapshots. The assembler, firmware examples, FPGA loader, source manifests and
documentation use the new ISA (host revision `0x20`).

At divider 1, an ordinary instruction—including shifts, taken branches and an
available automatic FIFO transfer—retires in one clock. This is an RTL latency
contract. Delays, pin/IRQ waits and blocked FIFOs deliberately stretch execution;
it is not a guarantee that an arbitrary program or empty queue can sustain a
continuous protocol stream.

The TX example emits 8N1 at exactly 434 clocks/bit using eight instructions and
one queued byte. The RX example samples into ISR and pushes the received byte
to the host. Both are firmware; no UART serializer/deserializer is instantiated.

## Validation and measured baseline

- **11/11 pin-level cocotb tests passed**, using Icarus Verilog 13.0/cocotb 2.0.1.
  Tests cover all 64 width/direction shift combinations, FIFO stalls and transfers,
  automatic thresholds, counter saturation, instruction timing, branch/EXEC,
  host snapshots, protection, faults, IRQ/input waits and stop/resume.
- **FIFO scoreboard passed** all occupancy 0–4 × push/pop combinations, concurrent
  clear, then 1,000 further transactions. Full simultaneous pop/push preserves the
  old head; empty simultaneous traffic does not fall through.
- **Firmware UART TX/RX passed** for 55, 00, FF, A6. TX is checked at every clock,
  including 434-clock bits and the stop-to-completion boundary. The RX example is
  checked at 16 clocks/bit.
- **Arty demo simulation passed** ROM comparison, boot/configuration, debounce,
  three completed frames, held-button suppression, replay and mid-frame reset.
- **Yosys 0.69 `synth -noabc; check -assert` passed**, with zero reported structural
  problems. The same flow was run on the previous HEAD sources for comparison.

| Generic synthesis metric | Previous accumulator V0 | PIO V0 |
| --- | ---: | ---: |
| Total generic logic cells | 3,662 | 9,154 |
| Multiplexers | 1,511 | 4,747 |
| Flip-flop bits, all generic variants | 794 | 1,142 |
| Instruction memory bits | 512 | 512 |
| TX+RX FIFO storage bits | 0 | 256 |

Current hierarchy counts are 5,671 local core-control cells, 1,105 shift-datapath
cells, 1,589 instruction-memory cells, 306 per FIFO, 116 decoder, 39 PC and 22 host
interface. These are unmapped generic cells, **not CMOS5L area, LUT counts or a
timing measurement**. The roughly 2.5× logic increase is a reason to prioritize
physical measurements, not a prediction that the 8×4 tile budget will fail.

No new Vivado bitstream, CMOS5L place-and-route, post-route timing, SDF simulation,
physical board capture or formal proof was produced in this update. Local RTL and
generic synthesis results do not establish those outcomes.

## Priorities for subsequent versions

### 1. Establish physical fit and close the one-cycle timing paths

Run the CMOS5L 8×4 flow at the 20 ns target and retain area, congestion, setup/hold,
fanout and critical-path reports. Also implement the updated Arty design and
measure its timing. The expected paths to investigate are asynchronous instruction
read → decode → register selection/variable shift → register or output write, and
TX-head selection → same-tick autopull → shift → destination. These are hypotheses
from the RTL, not measured critical paths.

Use those reports to simplify register-write muxes and control enables first.
The 4,747 generic muxes dominate the current count. Evaluate a shared bidirectional
shift structure, narrower operand selection, and predecoded control where it
actually shortens paths. Preserve the one-clock contract; a serial shifter or
unannounced pipeline stage would break firmware timing. If banking/prefetch is
needed, explicitly solve branches, EXEC and writable instruction-memory coherence.

**Acceptance:** routed timing and area meet the chosen target, and every existing
cycle-exact waveform test still passes on the corresponding netlist.

### 2. Increase host throughput and FIFO elasticity

Each FIFO has only 128 bits. At a hypothetical continuous eight-bit OUT every clock,
that is 16 clocks of buffered output. With the data selector already set, this host
bus needs four byte transactions × two clocks = eight clocks per 32-bit word; an
eight-bit-per-clock stream consumes a word every four clocks. A deeper FIFO absorbs
bursts but cannot solve that sustained rate mismatch.

Add a burst/stream interface, explicit ready/valid or credits, and an appropriate
DMA/host bridge before high-rate streaming. Size queues from worst-case host service
latency and required protocol rate. Consider FIFO joining/configurable depth where
one direction dominates. Preserve atomic transfer rules and expose persistent
stall/overflow diagnostics or watermarks for tuning.

**Acceptance:** the selected target workload runs for the required duration under
worst-case host service delays without an unintended FIFO stall or dropped word.

### 3. Define the Ethernet/USB interface and clock budget

Select the actual protocol variant, data rate, electrical interface, clock source
and external PHY responsibilities. A single-cycle interpreter alone does not
provide Ethernet or USB support. Budget cycles for sampling, coding/decoding,
framing, bit manipulation, response deadlines, error checks and host transfers
before committing to a link target.

The present package has eight outputs and only two protocol inputs. Its protocol
pins cannot change direction, and its host owns the bidirectional pins. Add a pad
multiplexer and direction/output-enable path if a target requires turnaround or
shared wires. Decide whether a separate transmit/receive state machine or dedicated
small datapath assists are needed for simultaneous traffic. Keep framing programmable.

**Acceptance:** a cycle budget fits the chosen clock and pad interface, followed
by protocol-level interoperability tests with the intended PHY or endpoint.

### 4. Harden clock-domain crossings and pin timing

The protocol inputs have two-flop synchronizers; the host is explicitly synchronous.
Characterize input latency, minimum detectable pulse width, synchronizer placement,
metastability assumptions and reset release in the physical flow. An asynchronous
host will need a CDC bridge; it must not drive the synchronous bus directly.

Consider a controlled synchronous-input bypass only after the external timing
contract is defined. Plan integer/fractional clocking and any shared start alignment
for future state machines. Fractional division changes individual tick lengths, so
evaluate whether its jitter is acceptable for each protocol before adopting it.

**Acceptance:** reviewed CDC constraints/reports and setup/hold margins at the
actual pins, with receive phase/jitter/pulse-width tests around protocol limits.

### 5. Reduce storage and debug-interface area after measuring it

The instruction memory and FIFOs currently synthesize to 768 storage flip-flops
plus selection logic; instruction memory alone is 1,589 generic cells. Investigate
available memory structures/macros and realistic depths against the tile budget.
The instruction read must remain compatible with one-cycle execution; converting
it blindly to synchronous RAM introduces a fetch-latency change.

Evaluate the cost of wide host snapshots, register readback and writable debug
state against their development value. Keep useful observability during bring-up,
then consider a smaller indirect debug path for a production configuration.

**Acceptance:** measured mapped area reduction without changing visible FIFO order,
atomic host semantics or instruction/waveform timing.

### 6. Strengthen firmware tools and verification before ISA freeze

The supplied assembler is intentionally small. Add a disassembler, configuration
metadata (pin mapping/wrap/divider), static timing checks and a reference execution
model. Build bounded formal properties for no duplicate FIFO transfers, stall
stability, reset/enable behavior and IRQ/EXEC interactions. Add randomized program
and host-traffic tests against that model.

Extend UART RX firmware for framing errors, break, restart/resynchronization and
baud tolerance. Add a second protocol demo to check that the ISA remains general.
Multiple state machines, relative IRQs, FIFO joining, fractional division and a
dedicated interrupt/DMA interface are deliberately deferred; fixed-direction
pin-direction operations currently fault rather than pretending to control pads.

**Acceptance:** published ISA/host conformance tests, passing physical-netlist
regression and reproducible firmware/configuration artifacts for each target.

## Reproduction

From the repository root, run `./test/run.ps1` and `./fpga/test.ps1` on Windows, or
`python test/run.py` with Python and Icarus on PATH. The generic synthesis command
is recorded in `test/README.md`. Generated local results are in `test/results.xml`,
`test/tb.fst`, and `test/sim_build/synthesis.log`; the comparison log is
`test/sim_build/baseline-synthesis.log`. Build products are intentionally ignored
by Git. The report above preserves the relevant measured counts.
