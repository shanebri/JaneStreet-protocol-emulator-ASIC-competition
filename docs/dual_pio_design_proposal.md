> Historical checkpoint or task record. Status statements and next steps below
> apply to the named revision/date. See [current project status](project_status.md)
> for the qualified dual-engine build and remaining hardware work.

# Second independent PIO engine: design proposal

Status: **implemented**; the original design was approved on 2026-10-20.
The current implemented contract is [dual_pio.md](dual_pio.md); validation and
completed physical qualification are in [dual_pio_verification.md](dual_pio_verification.md).
The review findings and staged plan below record the pre-implementation assessment.
Review date: 2026-10-20.
Reviewed checkout: `54a6ff25a568b7a32a9fad6cef11812e5628345e`.

## Recommendation and scope

Instantiate two complete execution engines, each with its own 32x16
combinational-read instruction store and two 4x32 FIFOs. Share the synchronous
nibble host adapter, physical input sampling/qualification, and final pad
boundary. Use a static, host-configured owner bit for each of the twelve output
indices. Engine 0 owns every output after reset; engine 1 starts stopped.

Both engines can execute an ordinary instruction on every 50 MHz clock.
Neither instruction fetch nor FIFO transfer is arbitrated between engines.
Keep the ISA, five-bit PC, integer divider, branch/EXEC timing, firmware binaries,
pad capabilities, tile allocation, and 20 ns target unchanged.

Proposed additions are engine selection, capability discovery, output ownership,
aggregate status, and a masked group-control command. IRQ flags remain local;
initial inter-engine coordination is through the host and simultaneous START.
Direct firmware-to-firmware event signaling is an explicit alternative requiring
a separate decision, described below.

This proposal does not add SRAM, deeper/joined FIFOs, DMA, packet RAM, new
instructions, fractional division, USB or Ethernet protocol logic, clock domains,
pin multiplexing with the host, or a general crossbar.

## Repository findings and evidence limits

| Evidence | Implication |
| --- | --- |
| `src/project.sv` has one `host_interface`, one `protocol_core`, one `pio_pads` | Preserve the external top-level ports and nibble adapter; insert a subsystem below it. |
| `src/protocol_core.sv` combines execution, host staging, sampling, configuration, IRQs, and two FIFOs | Do not simply duplicate the entire top level. Extract the shared sampler and a reusable host-register bank. |
| `src/frontend/instruction_fetch.sv` has asynchronous PC and host reads | Two engine fetches must remain simultaneously available, including unrelated taken branches. |
| `src/pio_fifo.sv` provides old-head reads, full pop+push, and no empty fall-through | Shared storage or SRAM must not silently change these rules. |
| `tools/i2c_driver.py:74`, several cocotb assertions, and `fpga/tb_arty_i2c_bridge.sv:50` require VERSION `0x21` | A simple version bump breaks existing I2C software even with identical waveforms. |
| `examples/i2c.asm` occupies 24 words; SPI occupies 10 | A shared 32-word store cannot hold both existing images separately without program changes or overlap analysis. |
| `docs/architecture_area_budget.md` records the physical baseline at `b380b86` | Its 15.32% utilization is historical measured evidence, not a new two-engine result. |

The saved `test/sim_build/synth_final/src/` snapshot matches every current
submission RTL source after newline normalization. Its saved generic synthesis
report has 10,030 cells, 5,207 mux cells and 1,218 flip-flop cells. These are
unmapped structural counts, not physical area or timing.

The repository records 27 passing functional gate-level tests and a slow-corner
setup warning at `nom_slow_1p08V_125C`. Detailed worst slack and paths have not
been established in this review. Functional gate simulation is not SDF timing
validation.

Fresh baseline testing was attempted using `test/run.ps1`, then the alternate
project-local Icarus installation. Both stopped at the first FIFO compilation:
`iverilog` exited with 3221225477 (`0xC0000005`, access violation). No simulation
test ran in either attempt. Logs are in
`test/sim_build/dual_pio_review_baseline.log` and
`test/sim_build/dual_pio_review_alternate.log`. The cause is not diagnosed here.
This review does not claim a fresh regression pass.

## 1. State and logic replicated per engine

| Per-engine resource | Why it cannot be coupled |
| --- | --- |
| PC, ENTRY, wrap bounds | Independent control flow, zero-cost branches and wrap. |
| X, Y, OSR, ISR; IN/OUT counts | Independent data, scratch counters, shift direction/threshold behavior. |
| `running`, `fault`, divider and divider countdown, delay countdown | A wait, STOP, fault, or different rate on one engine must not delay the other. |
| Pending EXEC word/valid bit and IRQ-wait handshake state | Injected instructions and acknowledgments must stay associated with their originating engine. |
| SHIFTCTRL, EXECCTRL, PINCTRL, ROUTE, FILTER enable | Protocol and pin mapping differ between engines. |
| Programmed PINS, DIRS, OD | Each engine retains its own intended outputs and electrical configuration; final ownership selects which reach pins. |
| Eight IRQ flags and four DEBUG flags | Existing local IRQ indices, W1C behavior, and error attribution remain independent. |
| TX/RX words, read/write pointers and levels | Independent blocking, clear, overflow/underflow, and ordering. |
| IMEM and host IMEM address/low-byte staging | Independent programs and loading one stopped engine while the other runs. |
| DATA_ADDR, 24-bit write staging and 32-bit read snapshot | Engine switches cannot mix bytes or expose the other engine's popped RX word. |
| Decoder, shift datapath, operand/write muxes and retirement logic | Both engines must be able to execute different instructions on the same edge. |

Replicating the datapath is necessary even though much of it is combinational.
Time-sharing a shifter, decoder or register-write path at 50 MHz would prevent
two simultaneous ordinary instructions. Multipumping introduces a different
clock/timing architecture and is outside this design.

Keep the current lifecycle independently for each engine: START clears execution
state but preserves pins/configuration/FIFOs/IRQ/errors; STOP freezes; RESUME
preserves state; HALT holds its PC; ABORT_RELEASE stops and clears that engine's
four direction bits. FIFO_CLEAR keeps its existing stopped-or-stop/abort rule.
The external `ena` still freezes both engines; physical input sampling continues.
There is no new per-engine reset instruction. Global reset clears both sets of
metadata and host contexts, preserves unreset memory contents, and restores
engine-0 ownership.

## 2. Resources safely shared

Use one `host_interface.sv` instance, keeping its framing, accepted-byte strobes,
read capture, reset/disable behavior, and host-only `uio[3:0]` ownership intact.
Host activity is serialized already, so an engine read mux/write demux does not
reduce existing transport throughput.

Move the six two-stage synchronizers and four continuously running four-sample
qualifiers into one input module. Export both synchronized and qualified vectors.
Each engine applies its own FILTER enable to those vectors. The qualifier runs
even when FILTER is disabled today, so sharing its history preserves the same
sampling semantics without coupling filter configuration. Preserve the exact
register boundaries, reset values and previous-edge consumption: do not insert
an extra register between the sampler and execution.

Share `clk`, `rst_n`, the global selection/ownership/control registers, and one
`pio_pads` instance. Keep OD selection at the output ownership boundary.
Reuse module definitions and assembler code, while instantiating separate
execution hardware.

Retain separate host contexts initially: each source-level context is only
77 bits (5 IMEM address + 8 IMEM low + 8 DATA_ADDR + 24 write stage + 32 snapshot,
before synthesis pruning). Sharing these would save a small amount but require
transaction tags, cancellation rules, or restricted engine switching. It would
also lose useful interleaving of read snapshots. The physical nibble transaction
state remains shared.

## 3. Instruction memory alternatives

| Organization | Capacity and ports | Advantages | Costs and restrictions | Recommendation |
| --- | --- | --- | --- | --- |
| Two independent 32x16 stores | 1,024 storage bits; each has one engine read plus host read and stopped-state write | Unrelated simultaneous fetches; unchanged PC/ISA; independent load and protection | Duplicates 512 program bits and fetch muxing relative to baseline | **Use for first integration.** |
| One shared 32x16 store with two execution read ports | 512 bits; two execution reads plus selected host read, one host write | Saves 512 storage bits; useful when both engines run the same image | Additional read mux; only 32 total slots; program placement couples engines; writes must be blocked while either engine runs | Viable area alternative only if reduced total capacity and coupled loading are approved. |
| One shared 64x16 store with two execution reads | 1,024 bits plus two wider reads and host read | Could offer flexible placement | No storage-bit saving; five-bit PC/JMP cannot address arbitrary 64 words without a new bank contract | Reject flexible addressing in this scope. |
| A 64x16 array split into fixed 32-word engine banks | 1,024 bits; simultaneous bank-local reads | Same logical behavior as independent stores | Mainly a coding/layout choice; a true single-port macro still cannot serve both banks simultaneously | Accept only if physical implementation preserves independent access. |
| Shared single-read-port memory with arbitration | One fetch per memory clock | Small port structure | Cannot supply two unrelated fetches per 20 ns; stalls become workload-dependent | Reject. |
| Synchronous SRAM, shared or separate | Macro-dependent capacity/ports/latency | Potential future storage efficiency | Adds a fetch-latency problem for START, branches, wrap, PC writes, EXEC and host readback | Separate architecture project. |

Even a shared flip-flop array needs separate combinational read selection for
both PCs; sharing the stored bits does not eliminate both decode/datapath paths.
Do not make shared-IMEM writes legal merely because the selected engine is
stopped: the other engine could be executing that same word.

For independent memories, host writes are protected by the target engine's
`running` bit only; reading either memory while running remains supported.
High-byte commit increments only that engine's IMEM_ADDR modulo 32. Neither
memory is initialized by reset. START still requires software to have loaded
every reachable word.

## 4. FIFO alternatives and bandwidth

| Organization | Storage | Independence and timing |
| --- | --- | --- |
| Four independent 4x32 FIFOs | 512 total data bits, plus four sets of seven pointer/level bits | Two engines can consume TX or produce RX concurrently; one selected host access can coincide. Preserves every existing queue boundary rule. |
| One untagged shared TX and one shared RX queue | 256 bits if current depths retained | Engines compete for TX head; RX producer identity is lost; clear/full/empty state couples them. Incompatible with independent behavior. |
| Shared dynamically allocated/tagged pool | Capacity selectable; tags, allocation and per-engine queues needed | Requires simultaneous read/write capability, quotas and arbitration; otherwise one engine can starve or stall the other. Too much control overhead for four-word queues. |
| Shared array statically partitioned into four queues | Same 512 bits | Equivalent to independent FIFOs only with independent access paths; no inherent storage saving. |

Use four unchanged `pio_fifo` instances. Preserve old-head reads, simultaneous
full dequeue/enqueue, zero on empty, no same-edge empty bypass, and metadata-only
clear/reset. In particular, `rx_room` must use only the same engine's accepted
host pop; a pop from RX0 must never unblock a full RX1.

The host still needs at least 16 clocks per word with DATA_ADDR already set,
20 clocks including that selector, and 24 clocks if an engine-select byte is
also needed. At 50 MHz those ideal aggregate rates are 3.125, 2.5 and about
2.083 Mword/s respectively, before status polling and gaps. A selected engine's
DATA_ADDR persists, so switching back need not always rewrite it.

At two bits per clock, one engine consumes a 32-bit word every 16 clocks.
Two such streams need one word every eight clocks in aggregate, exceeding this
host interface even at its best rate. Four words buffer 64 such clocks per
direction, excluding OSR/ISR elasticity. Two engines improve concurrency, not
sustained host bandwidth. Queue depth and service deadlines must be evaluated
for each workload.

## 5. Proposed host ABI and compatibility

Keep existing byte addresses `0x0..0xE` banked by selected engine, including
CONTROL, STATUS, PC, IMEM, FIFO_LEVEL, IRQ, DEBUG and INPUT. Keep existing
data selectors `0x00..0x19` unchanged within each bank.

Use the previously unused **write** side of byte register `0xF` for SM_SELECT:
complete byte value 0 selects engine 0, value 1 selects engine 1, and other
values are ignored. Reset selects engine 0. Reading `0xF` still returns `0x21`,
defined as the compatible ISA/transport revision. Capability discovery supplies
the extension revision instead of changing the existing version check.

This preserves the existing I2C driver, metadata, waveform tests and FPGA loader
in the default engine-0 environment. Software that deliberately wrote formerly
unused addresses or expected every unmapped selector to stay zero is not covered
by that compatibility claim. Existing unmodified clients also cannot safely
coexist with a second independent host client without serialization.

Proposed common data selectors, accessible from either bank:

| Selector | Name | Definition |
| --- | --- | --- |
| `0x1A` | CAPABILITIES | Read-only `0x50490102`: high 16 bits discovery signature, bits15:8 extension revision 1, bits7:0 engine count 2. Old hardware reads zero. |
| `0x1B` | GPIO_OWNER | Low 12 bits: 0 selects engine 0, 1 engine 1; remaining bits zero. Reset zero. Atomic stopped-state write with release checks below. |
| `0x1C` | GROUP_CONTROL | Write-only command; reads zero. Two-bit masks for START[1:0], STOP[3:2], RESUME[5:4], ABORT_RELEASE[7:6], FIFO_CLEAR[9:8], CLEAR_ERRORS[11:10]. Upper bits ignored. |
| `0x1D` | GLOBAL_STATUS | Snapshot: STATUS0[7:0], STATUS1[15:8], IRQ0[23:16], IRQ1[31:24], using existing STATUS encodings. Read-only. |
| `0x1E` | SELECTED_ENGINE | Read-only selected engine index, zero-extended. |

All common selectors use the same `6,7,9,A` word staging/snapshot mechanism.
Their writes are intercepted by subsystem decode, not sent as local configuration
writes. Capability/status reads cause no FIFO side effects. GPIO_OWNER rejection
is detected by readback; there is no new sticky error register in this proposal.

**Transaction identity:** selection changes only on the accepted second write
nibble of `0xF`. Changing address to `0xF` abandons an unfinished nibble transaction
under the existing adapter rules. There is no asynchronous way to change selection.
The first read nibble still captures a complete byte, so its high nibble cannot
come from another engine.

For multi-byte words, bank the contexts themselves. If engine 0 has staged bytes,
selecting engine 1 leaves those bytes in bank 0; a DATA_3 commit uses only bank 1's
staging and selector. Returning to engine 0 can finish its word. The same rule
applies to IMEM low-byte staging and saved RX snapshots. Reading DATA_0 pops only
the selected RX queue once; switching away cannot undo that pop or pop the other
queue. Reset clears both contexts. `ena=0` discards adapter phase, but preserves
engine selection and bank contexts, matching existing staging retention.

As today, hardware does not track which staging bytes are valid; software must
write all four bytes before committing each new word. Bank isolation prevents
cross-engine mixing, not malformed same-bank writes. Host clients must lock the
physical transport across selection plus the complete logical transaction;
same-bank writers must also serialize selector and staging use.

If an externally visible hardware revision bump is preferred, choose `0x22`
instead and explicitly update version checks in the driver, tests and metadata.
That is an alternative, not the recommended strict compatibility path.

## 6. GPIO ownership and arbitration

Retain all logical pin numbers and the permanent host/protocol split:
output0..7 are dedicated outputs; output8..11 are the four protocol pads;
input0..1 are dedicated inputs and input2..5 are physical pad readback.

GPIO_OWNER is one selection bit per output, not two overlapping permission masks.
For each pin, select the owner's registered value; for each bidirectional pad,
select that same owner's direction and OD bit. Feed these into the existing pad
module. Both engines can read all six physical inputs regardless of ownership,
using their own routing and FILTER enable.

This creates a single driver by construction. There is no round-robin arbiter,
wired-OR combination, ownership transfer on a PIO instruction, or stall caused
by losing a pin. Non-owner instructions still update their own programmed PINS/
DIRS; they have no physical effect on that pin. PINS/DIRS readback stays local
programmed state; INPUT remains physical sampled state. Overlapping ROUTE or
side-set mappings therefore do not change execution timing.

Accept an ownership update only when **both engines are stopped**. For every
changed bidirectional pad, additionally require both engines' programmed direction
for that pad to be zero. Reject the entire word if any condition fails. Bits above
11 are ignored. This is deliberately conservative and makes ownership stable
through timed execution.

Host handoff sequence:

1. Stop both engines; release directions on changing protocol pads.
2. Preload the incoming engine's values and OD configuration.
3. For changing dedicated outputs, make incoming and outgoing values equal if
   a level transition is unwanted. Dedicated outputs cannot be tri-stated.
4. Commit GPIO_OWNER and verify readback.
5. Explicitly arm the new owner's directions and START/RESUME as needed.

Hardware release checks apply even when an OD output value of one would
electrically release the pad: programmed direction must be zero for handoff.
There is no claim of analog glitch-free switching for dedicated outputs; prepare
equal levels and verify physical timing if an application requires it.

ABORT_RELEASE on one engine affects its own DIRS and therefore only its owned
physical pads. It never releases another engine's bus. STOP/HALT/fault/disable
continue to retain physical output state. Global reset immediately gates protocol
OE off, then synchronously resets state and ownership. No extra output pipeline
stage is permitted.

## 7. IRQs and synchronization

Keep eight local flags per engine, preserving WAIT IRQ, IRQ SET/CLEAR/WAIT,
host W1C/SET, and existing simultaneous-update priority. In particular, firmware
sets win host clears and firmware clears win host sets according to the current
RTL; preserve the one-time IRQ WAIT set and its acknowledgment state.
Clearing engine 0's flag must never acknowledge engine 1's wait. There remains
no dedicated external interrupt pin.

GLOBAL_STATUS provides one-edge snapshots of both engines' status and IRQ flags.
Software can acknowledge a local event and set the peer's local IRQ through its
bank. This is host-mediated signaling with transport latency, not a one-cycle
inter-engine handshake.

GROUP_CONTROL commits at DATA_3's accepted write edge. Apply the masks to both
engines on that edge, independently preserving local priority:
ABORT_RELEASE > STOP > START > RESUME. FIFO clear and error clear retain their
existing qualifications. Commands address engines independently of SM_SELECT.
The ordinary banked CONTROL register still affects only its selected engine.

START for both engines resets both divider phases; their first attempts are on
the next enabled clock edge. Equal divider settings remain phase-aligned until
a lifecycle action changes phase; blocking instructions can still make program
progress diverge. Different dividers share only the initial phase. Group RESUME
preserves each paused phase and is not an implicit resynchronization.

**Direct firmware synchronization alternative:** do not silently replace local
IRQs with one shared bank. That would make existing independent programs consume
each other's events. If direct communication is required now, approve a separate
event contract before implementation: number of shared flags, how instructions
address them without reinterpreting existing IRQ0..7, reset/START retention,
same-edge set/clear priority, read latency, single versus multiple consumers,
and acknowledgment ownership. A shared single bit coalesces events and cannot
count repeated notifications. A new encoding or opt-in mapping also needs ISA/
assembler/verification work. No such event fabric is included in the recommended
first integration.

## 8. Timing and area

Preserve these paths locally, with no second-engine arbitration or new pipeline:

| Potential path from RTL inspection | Risk / action |
| --- | --- |
| PC -> IMEM read mux -> decoder -> branch/retire -> PC | Preserve zero-penalty branch, wrap and dynamic PC writes. Measure actual slow-corner slack. |
| TX head -> same-tick autopull selection -> variable shift -> destination register | Do not insert shared FIFO grant/port muxing here. |
| IN source -> shift/mask/merge -> ISR or RX write | Keep independent datapaths and simultaneous RX writes. |
| FIFO level + selected host RX pop -> `rx_room` -> stall/retire | Demultiplex host strobes early; verify selected-bank fanout and timing. |
| Registered value/direction/OD -> owner mux -> pad data/OE | Adds a small output mux; STA must include pad output and OE requirements. |
| Host address -> bank/global read mux -> adapter read capture | Wider read selection may become a host setup path. |
| Shared sampled inputs and group control -> both engines | Fanout/routing grows; preserve sampling latency and synchronous enables. |

These are candidate paths, not measured critical paths. Retrieve the baseline
post-route reports (the area report identifies `55-openroad-stapostpnr/`) and
extract worst setup/hold slack, endpoints, cell delay, routing delay and fanout.
Optimize logic factoring, mux depth and placement only with that evidence.
Do not trade an extra instruction cycle for timing closure.

Incremental storage for a second engine is at least:

- 512 instruction bits.
- 256 FIFO data bits and 14 FIFO pointer/level bits.
- 128 X/Y/OSR/ISR bits.
- PC, counters, configuration, pin state, IRQ/debug/EXEC and host context state.

Thus the main instruction/FIFO/data-register storage increases by 896 bits,
before metadata. Sharing IMEM would save 512 data bits, but not its second
execution read path. Sharing the physical sampler avoids a second 12-bit
synchronizer plus 16-bit qualifier history/result. Keep per-engine FILTER enables.
The added owner register is 12 bits, selection is one bit, and capability data
is constant; status aggregation and group commands need decode rather than a
large data store.

The saved generic report attributes 1,589 cells to one IMEM, 1,105 to one
execution unit, and 306 to each FIFO. These are structural scale indicators,
not additive mapped-area predictions. The larger register/control mux network
also duplicates. Report hierarchical mapped area after implementation to decide
whether any further sharing is worth its behavioral cost.

The recorded routed non-filler area is 0.185105 mm2 in a 1.208173 mm2 core
(15.32%). Doubling it gives a planning reference of 0.370210 mm2 / 30.64% before
accounting for shared blocks, added muxes, routing and timing repair. This is
neither a bound nor a two-engine estimate with physical validation. Filler is
reclaimable; the 60% placement-density setting is not a measured utilization.
Keep 8x4 and 20 ns unchanged. Final acceptance requires routed fit and setup/hold
closure at the required corners; the existing slow-corner warning is unresolved.

## 9. Future USB low-speed and Ethernet PHY work

Keep the input sampler, pad boundary, byte-host interface, and per-engine FIFO
interfaces modular so later physical interfaces can be evaluated without merging
the execution engines. Do not implement bypasses or protocol hardware now.

USB low-speed is 1.5 Mbit/s. At 50 MHz, the nominal bit interval is 33 1/3 clocks;
an integer divider alone cannot represent it exactly. A future design must budget
firmware instruction timing, receiver phase tracking, stuffing/NRZI, turnaround,
and electrical transceiver behavior. Two engines and GPIO OD support do not by
themselves establish USB capability or compliance. Static output ownership still
allows both engines to observe the same input; DIRS can control transmit/release.
Source: [USB-IF FAQ](https://www.usb.org/faq).

RMII uses two-bit TX and RX paths and a common 50 MHz reference clock.
At 100 Mbit/s it leaves one core clock per dibit, so loop/control instructions
and the host service limit are substantial constraints even with separate TX/RX
engines. The current asynchronous-input synchronizers and optional filters are
not a validated source-synchronous PHY interface; a future design needs
clock-related I/O constraints, coherent data/control sampling, pin allocation,
and buffering/MAC responsibility decisions. A 50 MHz core frequency alone is
insufficient. Source: [Intel RMII documentation](https://www.intel.com/content/www/us/en/docs/programmable/683117/20-4/rmii.html).

These are feasibility boundaries, not additions to this implementation.
Any PHY selection, USB analog interface, clock-domain crossing, packet storage,
or host-throughput upgrade requires another approved design.

## 10. Staged implementation and concrete files

Each stage depends on approval of the corresponding architecture. No RTL or
firmware changes were made during this review.

| Stage | Proposed files and change | Exit evidence |
| --- | --- | --- |
| 0. Freeze contract and baseline | Approve this proposal; restore a working simulator environment; collect slow-corner reports. Update `docs/info.md`, `docs/isa.md`, `docs/memory_architecture.md`, and an additive dual-engine contract only after approval. | Current 27-test suite and FIFO/host/pad units run; baseline physical timing findings recorded. |
| 1. Extract reusable boundaries, still one engine | Add `src/pio_inputs.sv` for unchanged sampling/qualification and `src/pio_host_bank.sv` for per-engine byte register contexts. Refactor `src/protocol_core.sv` to consume sampled inputs and accepted local word/control operations; expose register read data/status and pin state. Wire from `src/project.sv`. | Existing register, timing, waveform, pad and I2C tests unchanged and passing; generic structural/no-latch check. |
| 2. Add second engine and banked host access | Add `src/pio_subsystem.sv`; instantiate two cores, two host banks, two IMEMs and four FIFOs. Intercept byte-F selection and common selectors. Add `src/pio_gpio_owner.sv`; wire one shared sampler and `pio_pads`. Preserve `src/host_interface.sv` behavior. | Independent fetch/load/FIFO/control tests; selection/snapshot interleaving; ownership/reset/abort tests. Engine 0 compatibility remains passing. |
| 3. Add approved coordination | Implement GROUP_CONTROL and GLOBAL_STATUS in `pio_subsystem.sv`; connect explicit control pulses into each core. Keep local IRQ logic. | Same-edge start and control-priority tests; phase preservation and IRQ isolation. No direct shared event fabric. |
| 4. Integrate host tooling and concurrent protocols | Add `tools/pio_host.py` or equivalent transport wrapper providing an engine-scoped, locked byte transport. Allow `tools/i2c_driver.py` to use that wrapper without changing the I2C firmware or existing default. Add `test/test_dual_pio.py` and focused subsystem/input/ownership SV units. | UART/SPI/I2C concurrency tests and mixed host-service stress; existing examples/hex/assembler remain unchanged. |
| 5. Physical qualification | Run the existing CMOS5L flow and functional gate suite on the final sources; inspect all required setup/hold corners and output/OE timing, area and congestion. Update `docs/architecture_area_budget.md` and verification documentation with measured results. | Actual two-engine 8x4 fit, 20 ns closure, all required functional checks; distinguish any remaining limits. |

The host-bank boundary should emit IMEM writes/address, full-word writes/
selectors, snapshot/pop strobes, and local CONTROL/IRQ/DEBUG operations. The core
retains execution configuration and architectural read values. Common selectors
override the bank's read input before its snapshot; their commits go to the
subsystem. This avoids a second snapshot mechanism or a global mux on the
instruction datapath.

Keep `src/frontend/pc.sv`, `src/frontend/decoder.sv`,
`src/frontend/instruction_fetch.sv`, `src/execution_unit.sv`, and
`src/pio_fifo.sv` behavior unchanged. `pio_pads.sv` continues to receive only one
resolved value/direction/OD vector. The assembler needs no ISA changes for the
recommended design.

Whenever sources are added, update `info.yaml`, `test/Makefile`,
`fpga/create_project.tcl`, and the existing-project migration list in
`fpga/build_bitstream.tcl`. `test/run.py` already reads `info.yaml`, but its
unit list and cocotb module list need the new tests; update the Makefile test
module list too. `test/synth.py` already consumes the manifest.
FPGA `test.ps1`, `test_spi.ps1`, and `test_i2c.ps1` consume the manifest; retain
their legacy engine-0 loaders and run them as compatibility checks.

## 11. Targeted verification and likely regressions

| Target test / assertion | Required checks and regression caught |
| --- | --- |
| Existing suite unchanged in default mode | All 27 cocotb tests plus FIFO, host and pad units; UART 434-clock bit intervals, UART RX, SPI waveforms, I2C stretching/recovery and `0x21` version checks. |
| `dual_independent_execution` | Both engines at divider 1; unrelated taken branches, wrap, shifts 1..32, PC writes, delay and chained EXEC. One fault/stall must not slow the other. Cycle-exact output retirement traces. |
| `dual_imem_isolation` | Distinct words at identical addresses; protected writes to running target; successful load/readback of stopped peer while other runs; per-bank low-byte stage and auto-increment wrap. |
| `dual_host_context_interleaving` | Switch after each data byte and after IMEM_LO; resume original transaction. Distinct selectors, patterns and RX snapshots. First DATA_0 pop occurs once; other queue never pops. |
| `dual_host_partial_nibbles` | Address/direction changes, held strobes, long idle, RD+WR, reset and disable around SM_SELECT; invalid selection bytes ignored; no partial commit or cross-bank high nibble. |
| `dual_fifo_boundaries` | Both TX pops and both RX pushes on the same edge, plus selected host access; every full/empty simultaneous case. Preserve old head/no bypass. Other-engine RX pop cannot create room. |
| `dual_lifecycle_isolation` | START/STOP/RESUME/ABORT/FIFO_CLEAR/error-clear on one engine leaves the other PC, queues, timing, IRQ and pins intact; shared `ena` freezes both, sampler continues. |
| `dual_gpio_ownership` | Exercise all twelve owner bits; conflicting SET/OUT/MOV and side-set on both engines. Only owner reaches pins; non-owner shadow state remains readable. OD data/OE and dedicated fixed-direction semantics preserved. |
| `dual_gpio_handoff` | Reject updates while either engine runs or a changed pad has either direction armed; atomic all-or-nothing update; release-before-handoff; engine-specific abort and asynchronous OE reset gating. |
| `dual_input_views` | Both engines observe identical raw sample latency; one filtered, one unfiltered; stopped/disabled sampling; absolute/relative WAIT, JMP pin, missing indices and physical readback. |
| `dual_irq_isolation` | Same IRQ index used concurrently by both engines; host set/clear coincident with instruction set/clear/WAIT; one-time wait request, successful WAIT1 clear, START retention. |
| `dual_group_control` | Both first ticks on the clock after command commit; independent divider rates; START/STOP/ABORT priorities; permitted/ignored FIFO clear; RESUME preserves divider/EXEC/delay state. |
| `dual_global_snapshots` | Aggregate status/IRQ captured on one edge; common-register snapshots survive switching; read-only writes ignored; capability discovery zero on old hardware and exact signature on new. |
| `dual_protocol_concurrency` | I2C on pads8/9 alongside UART or SPI on dedicated outputs; UART TX plus RX; repeated runs with engine roles exchanged. Independent programs/dividers; FIFO stress while servicing peer; exact waveform comparisons. |
| Structural and physical | No latches, combinational loops, multiple drivers or width truncations. Each ordinary ready engine retires independently. Functional gate regressions plus separately reported STA, area, congestion and pad timing. |

Retain pin-level observation for system tests so the same suite can run against
the hardened netlist. Unit tests may assert internal transaction enables and
ownership invariants. Use deterministic randomized schedules and queue
scoreboards to vary bank changes, host service, simultaneous operations and
reset/disable timing. Do not weaken waveform assertions to hide new bubbles.
Preserve the existing CI workaround by avoiding `failure` in passing test names.

## Approval decisions before RTL work

1. **Memory capacity:** approve two independent 32x16 stores and four independent
   4x32 FIFOs. The shared 32-word IMEM option saves storage but sacrifices total
   program capacity and independent reload; it is not the default.
2. **ABI:** approve byte-F write selection, banked contexts, proposed common
   selectors/bit fields, and keeping VERSION `0x21` with separate capability
   revision. Alternatively approve a version bump and client migration.
3. **GPIO:** approve exclusive static ownership, engine-0 reset ownership,
   non-owner shadow writes, stopped/released handoff checks, and engine-local
   abort behavior.
4. **Synchronization scope:** approve local IRQs plus host-mediated signaling
   and masked group control. If direct firmware events are required in the first
   release, resolve their separate contract before stage 2.
5. **Acceptance:** confirm two simultaneously available one-cycle engines at
   divider 1, unchanged instruction/host/pad latency contracts, and actual
   50 MHz timing closure within 8x4 as release requirements. The recorded
   slow-corner violation cannot be accepted as proof of closure.

Approval of this proposal does not authorize the deferred SRAM, direct-event,
USB, Ethernet or higher-throughput host alternatives.
