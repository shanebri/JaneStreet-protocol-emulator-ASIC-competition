> Historical checkpoint or task record. Status statements and next steps below
> apply to the named revision/date. See [current project status](project_status.md)
> for the qualified dual-engine build and remaining hardware work.

# Implementation prompt: four-bit host and general bidirectional PIO

Implement the architecture and I2C support described below in this repository. This is an implementation request: complete the RTL, assembler, firmware, host tooling, FPGA integration migration, documentation, and meaningful verification. Inspect the current repository and applicable AGENTS.md instructions first. Preserve unrelated user changes. Do not deploy, program a board, or claim physical validation without actually performing it.

The approved decisions are:

- Split `uio[7:0]` permanently into four host data bits and four protocol pads.
- Give the PIO core general output-value and direction state, with configurable per-pad open-drain mode.
- Keep protocol framing in firmware; do not add a dedicated I2C controller FSM.
- Preserve concurrent host access while protocol firmware executes.
- Design for reusable shared-wire protocols and future host improvements. Do not attempt Ethernet, USB, multiple state machines, DMA, a new memory architecture, or a large routing crossbar in this change. In particular, 10 Gbps Ethernet is a separate hardware architecture, not an acceptance target.

Proceed autonomously on routine implementation details. First write a concise architecture contract in the repository, resolving the register layout and timing details below; then implement it in the same task. Do not stop after delivering a plan. If a requirement is genuinely incompatible with the hardware budget or existing execution model, explain the concrete conflict rather than silently relaxing it.

## 1. Fixed package allocation

Use this physical pin assignment:

| Pins | Role |
|---|---|
| `ui[3:0]` | Existing host byte-register address |
| `ui[4]` | Host WR |
| `ui[5]` | Host RD |
| `ui[6]`, `ui[7]` | Retained dedicated protocol inputs 0 and 1 |
| `uio[3:0]` | Four-bit bidirectional host data |
| `uio[7:4]` | Four independent bidirectional protocol pads |
| `uo[7:0]` | Retained dedicated protocol outputs |

For the default I2C example, use `uio[4]` for SDA and `uio[5]` for SCL. Leave `uio[6:7]` available for other uses; include a remapped I2C test to prove these are configurable pads rather than hardwired I2C signals.

The host must never enable a driver on `uio[7:4]`. Protocol logic must never control `uio[3:0]`. Host reads and writes must work while I2C is active, including while the engine waits for SCL or FIFO service.

## 2. Four-bit host transport

Keep the core-facing host interface byte-oriented: address, 8-bit write data, 8-bit read data, and exactly one read/write acceptance event per completed logical operation. Put nibble framing in the host transport adapter, not in the execution unit or FIFO implementation.

Retain synchronous-to-core-clock operation. Do not add an asynchronous-host assumption or silently add synchronizers to a bus requiring a coherent handshake.

Define and implement the following wire protocol:

- Each byte is transferred low nibble first, then high nibble, using two separate rising-strobe transactions at the same address and in the same direction.
- RD and WR must return low for a sampled edge between nibble transfers. Holding a strobe high never repeats a transfer or advances nibble phase.
- A write stages its first nibble and commits a byte only on the matching second nibble. No register/FIFO/instruction-memory side effect occurs on the first nibble.
- On the first read nibble, capture one coherent byte and perform its byte-read side effect once. The second nibble comes from the same captured byte even if core state changes.
- For RX FIFO reads, the first nibble of DATA_0 initiates the existing 32-bit snapshot/pop once. Abandoning this read does not undo the pop. Document that behavior explicitly and require clients to finish normal reads.
- Ordinary idle cycles between beats preserve the pending half-byte. Do not introduce an undocumented timeout.
- An address or read/write-direction change aborts a pending half-byte; treat the next accepted transaction as the first nibble of the new operation. An abandoned write has no side effect.
- A sampled RD=WR=1 is a reserved transport resynchronization condition: drive no host data, accept no core transaction, and discard pending nibble state. Require strobes low before the next transaction. It must not alter engine state or protocol outputs.
- Reset or disable discards incomplete transport state. Transactions while disabled are discarded; require strobes low before re-enabling transfers.
- Hold read data stable through the read strobe and define exactly when it becomes valid relative to the accepted edge. Disable all host output enables for writes, idle, reset, disable, and simultaneous RD/WR.

Preserve the existing byte-register addresses and little-endian 32-bit accesses through registers 6, 7, 9, A wherever possible. Preserve instruction low-byte staging/high-byte commit and data-word staging/final-byte commit. Nibble assembly must not cause duplicate snapshots, FIFO pushes/pops, instruction commits, address increments, or IRQ clears.

Bump VERSION from 0x20 to 0x21 for this breaking transport revision unless that value has already been assigned in the current repository. Make clients check the documented revision where practical. Old electrical byte-bus compatibility is not required; do not maintain two transports unless needed by an actual existing integration.

Document cycles per byte and per FIFO word, including strobe gaps and selector overhead. Do not claim that FIFO depth resolves a sustained throughput deficit. Keep the transport/core boundary suitable for a later burst adapter without implementing bursts now.

## 3. General PIO pin model

Use a clearly documented logical mapping that preserves old output indices:

- Logical output/value indices 0..7 map to `uo[7:0]`.
- Logical output/value indices 8..11 map to protocol pads `uio[7:4]`.
- Logical input indices 0..1 map to `ui[7:6]`.
- Logical input indices 2..5 map to physical pad readback from `uio[7:4]`.

Output and input namespaces are deliberately different; publish the correspondence in a single table and use named constants in software. Do not pretend the output-only pads have physical readback or can become inputs.

Retain the old dedicated-output reset value 0x01. Reset all four bidirectional protocol directions to input/released, their output latches to logical one, and their open-drain configuration to disabled. Ensure protocol output enables are suppressed during reset, including before the first resetting clock edge. Document synchronous state reset versus immediate pad-output gating.

Separate the execution core's desired output value and direction from a small pad-control layer that applies physical capabilities and open-drain configuration. Expose/read back these independently:

- Programmed output values.
- Programmed/effective direction with explicitly defined fixed-output behavior.
- Open-drain configuration for the four capable pads.
- Synchronized actual input values.

For dedicated outputs, direction writes are ignored and direction readback reports output-enabled. Open-drain writes to non-capable pins are ignored and read back zero. Only the four `uio` protocol pads have configurable electrical behavior. Document masking of unsupported bits.

For each owned bidirectional protocol pad, before reset/abort gating:

```
push-pull:  pad_data = value; pad_oe = direction
open-drain: pad_data = 0;     pad_oe = direction && !value
```

In both modes, input reads sample the external pad, not the output latch. In open-drain mode, value=1 releases the wire and value=0 pulls low when direction=1. Direction=0 always releases it.

Keep input synchronizers running while execution is stopped or disabled, as the existing design does. Extend them to all six input signals. Preserve two-stage synchronization and document observable latency. A synchronizer is not an I2C spike filter: assess filtering requirements for the selected operating modes and implement/document any needed filter and its additional latency. Do not silently bypass synchronization for speed.

## 4. ISA, configuration, and lifecycle semantics

- Preserve the existing ordinary-instruction latency, delay, wrap, EXEC, FIFO atomicity, and stall behavior.
- Extend OUT/MOV/SET output mapping to reach all 12 logical output indices, with masked writes preserving unrelated pins. Keep clipping rather than rotation. Define boundary and invalid-configuration behavior explicitly.
- Extend IN/MOV input selection, WAIT GPIO/PIN, and JMP PIN to reach all six real inputs. Define absolute versus base-relative indexing and out-of-range behavior consistently in RTL, assembler, and docs.
- Add `OUT PINDIRS` using destination selector 4 and `SET PINDIRS` using destination selector 4. Use the corresponding existing OUT and SET mapping ranges for direction writes. Do not accidentally legalize other reserved encodings.
- Add selectable side-set targeting: output value or direction. Retain optional single-bit side-set encoding and its existing delay-bit allocation. Make side-set pin selection reach all 12 output indices.
- Side-set wins overlaps on the same destination state. Value and direction updates to different state can occur on the same tick. Side-set applies on the first attempted instruction and remains effective during stalls, as today. Illegal instructions have no side-set or other architectural effects.
- OUT PINDIRS must obey normal shift counts, autopull, blocking, and atomic retirement semantics; a blocked instruction must not consume data or partially update direction.
- Configuration writes, including open-drain mode and pin routing, require the engine to be stopped. Preserve live FIFO/IRQ access.
- Prefer additive configuration fields/registers so existing UART/SPI pin mappings and instruction binaries retain their meaning after host migration. Do not cram wider fields into overlapping old fields. Publish every field, width, reset value, permission, and reserved-bit behavior.
- START preserves pad values/directions/configuration, consistent with existing output preservation. STOP, HALT, fault, and `ena=0` retain protocol pad state; document that this can hold a bus low. Transport disable still releases host drivers. Reset releases protocol bidirectional drivers.
- Add an explicit host ABORT_RELEASE command, using an unused CONTROL bit if available. It stops execution and clears all four protocol direction bits atomically, independent of a WAIT/FIFO stall. It does not alter dedicated outputs or silently clear FIFO contents. Give it priority over START/RESUME; document combinations with other control bits. Resuming or restarting must not implicitly re-enable directions; firmware or stopped-state configuration must re-arm them.

Do not claim atomic architectural updates prove analog glitch freedom. Review combinational OE/data paths and ensure firmware establishes data before enabling a push-pull driver where required.

## 5. Firmware I2C implementation

Implement and document a single-controller, 7-bit-address I2C firmware interface for nominal 100 kHz and 400 kHz at the 50 MHz target. Validate actual timing constraints, not just average clock frequency. Read the official NXP I2C specification when deriving timing requirements.

Required capabilities:

- Bus-idle check, START, STOP, and repeated START.
- Address+R/W transmission; byte write and byte read, MSB first.
- Target ACK/NACK sampling after address and write bytes.
- Controller ACK on intermediate read bytes and NACK on the final read byte.
- Multi-byte writes, multi-byte reads, and write-then-repeated-START-read transactions.
- Clock-stretch handling wherever SCL is released: wait for actual synchronized SCL high before timing its high phase or consuming SDA.
- Error/status reporting that distinguishes success, address NACK, and data NACK and identifies how many bytes completed.
- A documented bounded host-service/timeout policy. A permanently low SCL must not make the host inaccessible; the host must be able to invoke ABORT_RELEASE and recover. A hardware timeout counter is not required solely for this feature.
- A host-invoked firmware bus-clear procedure, following the applicable specification guidance, with bounded attempts and explicit failure when the line cannot be recovered.

Use the existing 32x16 instruction memory and existing FIFOs. Before finalizing the firmware interface, demonstrate instruction counts and how transactions longer than four FIFO words are streamed. A generic command interpreter or EXEC-based command stream is acceptable if it has a documented, tested ABI. Do not add protocol-specific RTL or enlarge memory silently to make the program fit.

The host may enqueue transaction descriptors/commands and service FIFOs; it must not bit-bang the I2C waveform with individual live register writes or rely on host reaction to every bus edge. Firmware owns wire timing. Place intentional FIFO stalls in documented legal bus states; do not let host jitter create unintended START/STOP conditions or short clock phases. Check how side-set-on-stall affects this.

Include readable assembly, reproducible checked-in hex, configuration metadata/constants, and a usable Python transaction encoder/driver with a transport abstraction. Show a sensor/register-style write-then-read example. Preserve and regression-test existing UART and SPI examples.

Do not claim multi-controller arbitration, I2C target mode, 10-bit addressing, SMBus conformance, Fast-mode Plus, or high-speed I2C. These are outside this implementation. Keep physical readback and direction support general enough for later development.

## 6. Required verification

Create a requirement-to-test matrix linking each behavior above to concrete test names. Use independent expected behavior and protocol monitors rather than simply reproducing the RTL equations in every test. Keep end-to-end acceptance tests at the external project pins; add focused module tests where they provide useful isolation.

### Host transport and existing semantics

- All 256 byte values and all 16 register addresses at the transport level using a mock core; use valid operations for integrated register tests.
- Low/high ordering; held strobes; arbitrary idle gaps; address changes; read/write-direction changes; interrupted reads/writes; explicit resynchronization; reset/disable between nibbles; correct re-entry after enable.
- Read coherence when the source changes between nibbles; stable data during a held RD; no host drive during forbidden conditions; host OE restricted to the low nibble even during protocol activity.
- Exactly-once FIFO enqueue/dequeue, snapshot, IRQ clear, instruction commit/increment, and final-byte word commit. Include simultaneous host/core FIFO boundary activity under the slower transport.
- Preserve the existing FIFO unit scoreboard and all applicable core timing/ISA tests. Update transport helpers instead of weakening their assertions.

### General pad, input, and direction behavior

- Every protocol pad, all value/direction/open-drain combinations, mixed modes on different pads, fixed-output capability masking, and unrelated-bit preservation.
- Output/readback separation: externally hold a released open-drain pad low and prove the core reads low despite its output latch being one.
- SET/OUT PINDIRS across bases/widths, clipping boundaries, counts 1..32, both shift directions, autopull success/stall, and existing EXEC injection paths.
- Side-set of values and directions, overlap priority, non-overlap simultaneous updates, stalls, HALT, and invalid-instruction suppression.
- All six input indices through IN, MOV, WAIT GPIO/PIN, and JMP PIN; synchronization latency, base mapping, reset, and invalid-index behavior.
- Reset, START, STOP, RESUME, HALT, faults, disable, and ABORT_RELEASE during actively driven high/low, WAIT, FIFO stalls, and a partial host transfer. Check documented priorities and re-arm requirements.
- Assembler encoding and rejection cases, including new operands and expanded WAIT indices; checked-in assembly/hex/config consistency.

### Electrical bus model and I2C acceptance

Model resolved SDA/SCL with pull-ups and separate controller/target drivers. Observe actual resolved wires and feed them back to ASIC inputs. Do not directly assign an expected SDA bit while ignoring output enable. Assert the ASIC never actively drives high in open-drain mode. Detect illegal push-pull contention in dedicated negative tests. Include delayed rise behavior without claiming this models all analog effects.

Build an independent target model and bus monitor covering:

- Address ACK/NACK, each write-byte ACK/NACK position, reads, final-read NACK, repeated START, STOP, and bus-idle detection.
- Payloads 00, FF, 55, AA, 01, 80, walking bits, and reproducible randomized data.
- Both target rates, a slower diagnostic configuration, varied asynchronous target phases, delayed SDA changes, and delayed line rise within the timing budget.
- Clock stretches of varying lengths at multiple bit/ACK positions, including the first SCL release and a permanently stuck-low condition.
- Multi-byte transfers exceeding FIFO capacity, deliberate host-service delays, TX starvation and RX backpressure; verify byte order, exactly-once transfer, documented legal stalls, and continued host access.
- Bus busy at entry, SDA stuck low, successful bus clear, failed bus clear, host timeout/abort, reset mid-transfer, and clean subsequent transactions.
- Alternate SDA/SCL pad assignment; unrelated protocol pads and dedicated outputs preserved.

Check all applicable minimum setup/hold/high/low/bus-free timing requirements on resolved wires, including after a stretch. Do not sample stale synchronized SCL high immediately after a low-to-release sequence. Assert the required number of clock pulses per byte, stable SDA during SCL high except START/STOP, correct ACK ownership, and no spurious edges during FIFO waits.

Use bounded test timeouts and deterministic random seeds. Tests must fail on a stuck transaction rather than hang indefinitely. Existing 12-test counts are historical, not a ceiling or a required final count.

## 7. Integration and future maintenance

Inspect all instantiations of `tt_um_shanebri_top`, all host helpers, source lists, and build scripts. Migrate at least the current cocotb helpers, `fpga/arty_demo.sv`, `fpga/arty_spi_test_host.sv`, and associated simulations. Prefer one reusable FPGA byte-to-nibble host adapter over separately duplicated framing FSMs. Preserve the UART demo and SPI hardware-test behavior.

Do not leave upper UIO inputs connected to old host-data bits. FPGA protocol pads require actual top-level tri-state buffers/IOBUF mapping when physically exposed; keep such primitives out of the technology-independent ASIC core. Provide a simulation-verified I2C FPGA wrapper/example and document the proposed board wiring. Verify actual board constraints against authoritative board documentation before assigning physical pins. Do not claim an FPGA hardware demonstration from simulation alone.

Update `info.yaml`, test source lists/runners, FPGA source lists, README, datasheet, ISA reference, host documentation, and protocol examples. Add a focused I2C guide and a short architecture-decision record explaining the four/four split, electrical modes, transport boundary, capabilities, and limits. Avoid retaining contradictory fixed-direction or eight-bit-host claims.

The design should permit later burst-host adapters, deeper FIFOs, additional state machines, and other pad modes without embedding host transport or I2C assumptions in the execution datapath. That means clear module boundaries and explicit ownership, not speculative implementation of those future features. Retain the current one-state-machine and static pad ownership model.

## 8. Validation and completion report

Run the complete RTL/FIFO/assembler/I2C suite and all applicable FPGA simulations. Run available lint and generic synthesis/structural checks; check for unintended latches, multiple drivers, internal tri-states, and width truncations. Use the actual submission manifest so tests cannot accidentally omit a new module.

Record baseline and final synthesis statistics using the same flow. Run CMOS5L area/timing and applicable gate-level tests if the required tools/PDK/netlist are available; otherwise state exactly which checks could not run. Preserve the 8x4 tile and 50 MHz targets without asserting fit from generic cell counts. Do not spend the task installing an unrelated physical toolchain or waive failed functional checks.

Completion requires working RTL plus runnable firmware and host examples, preservation of existing UART/SPI functionality, and passing available meaningful regressions. Summarize changed files, exact validation commands and outcomes, instruction-memory usage, host bandwidth, I2C timing, known limitations, and any unverified physical assumptions. Do not describe simulation as electrical compliance, timing closure, or hardware interoperability.
