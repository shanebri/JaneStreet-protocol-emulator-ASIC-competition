# Dual PIO implementation and validation

Date: 2026-10-20. Compatible ISA/host revision: `0x21`.
Dual-extension capabilities: `0x50490102` (revision 1, two engines).
The [implemented contract](dual_pio.md) defines the register map and lifecycle.

## Delivered implementation

- Two independent `protocol_core` instances, two 32x16 asynchronous-read IMEMs,
  four 4x32 FIFOs, and independent execution/configuration/IRQ/error state.
- One unchanged nibble `host_interface`, a shared physical input sampler and
  qualifier, and one existing physical pad layer.
- Per-engine host register contexts with independent IMEM staging, data selector,
  word-write staging and read snapshot.
- Byte-F write engine selection with byte-F read compatibility preserved.
- Capability discovery, twelve exclusive output owner bits, coherent aggregate
  status/IRQ snapshots, and masked group commands including simultaneous START.
- GPIO handoff rejection unless both engines are stopped and changing pads have
  both programmed directions released. Non-owner instructions update only shadow
  state and never wait for ownership.
- A locking Python engine transport compatible with the existing I2C driver.
  Source manifests, FPGA project/migration scripts and waveform paths updated.

The execution unit, decoder, PC, instruction-memory and FIFO implementations,
host nibble adapter, electrical pad equations, assembler, protocol firmware and
checked-in example binaries were not changed. The tile allocation remains 8x4;
`src/config.json` retains the 20 ns target and existing physical-flow settings.
Direct inter-engine events and SRAM/USB/Ethernet functionality remain deferred.

## Tests actually run

The local Icarus installations previously crashed inside the sandbox before
compilation. Running outside the sandbox succeeded without replacing tools or
changing RTL to accommodate the environment. Windows asyncio event-loop tests
also needed execution outside the sandbox.

| Check | Result |
| --- | --- |
| Unchanged single-engine baseline, `test/run.ps1` | 27/27 pin-level tests and original SV units passed. |
| One-engine extraction checkpoint, before enabling engine1 | 27/27 pin-level tests and original SV units passed. |
| Final dual implementation, `test/run.ps1` | **39/39 pin-level tests passed**: original 27 plus 12 dual-engine tests. |
| FIFO SV unit | Occupancy boundaries, old-head full simultaneous pop/push, empty no-bypass, clear, wrap and 1,000 deterministic traffic combinations passed. |
| Host/pad SV units | All 4,096 host address/byte combinations and all 4,096 electrical value/direction/mode combinations passed. |
| New subsystem SV unit | Simultaneous full TX0 host enqueue + both engine dequeues; empty TX refill/no fall-through; both RX producers; same-edge full RX pop/push; RX0 pop cannot unblock RX1; group abort/clear isolation passed. |
| Python host wrapper | Three unittest cases passed: competing engine/same-engine word clients, transport error/cancellation lock release, and argument validation. |
| `fpga/test.ps1` | UART ROM/boot/debounce/replay/reset; three frames at 434 clocks per bit passed. |
| `fpga/test_spi.ps1` | 512 SPI transactions, UART reports, mismatch detection and missing-slave timeout passed. |
| `fpga/test_i2c.ps1` | Existing nibble adapter/24-word firmware, physical tri-state readback, NACK/STOP, contention and abort-release passed. |
| Final generic synthesis | `synth -noabc`, `check -assert`, and no-latch assertion passed; zero structural problems. |

The twelve new pin-only tests cover:

1. Capability discovery, invalid selections, randomized banked writes and
   snapshots, separate IMEM low-byte stages, auto-increment and reset retention.
2. Partial selection nibbles, held strobes, RD+WR, disable phase discard, and
   preservation of selection/staging through disable.
3. Same-edge group START, next-edge first ticks, zero-cycle hardware wrap and
   taken branches on both engines, and group stop/resume.
4. Independent dividers, live loading of a stopped peer, executing injected
   instructions on engine1, and running-engine IMEM write protection.
5. All twelve owner bits, mixed data/direction/OD, rejected driven-pad/running
   handoffs, local abort release and immediate reset OE gating.
6. Overlapping SET/side-set output mappings with independent IRQ WAIT states and
   host acknowledgment; aggregate status/IRQ readback.
7. Independent FIFO contents/clear/error flags and interleaved saved RX words.
8. Shared input latency, independent filter enables, rejection of a short pulse,
   and continued sampling while execution is disabled.
9. Production I2C transfers concurrent with UART, with engine roles exchanged.
10. All shift widths 1..32 in both directions, executing different widths/data on
    both engines simultaneously and checking register/FIFO results.
11. Fault isolation, global enable freeze, resume of faulted state, and group
    START/STOP/RESUME/ABORT/FIFO_CLEAR priorities.
12. Concurrent SPI and UART with exact SPI edge intervals/data and UART waveform
    checks at 434 clocks per bit.

Pin-level tests access no RTL hierarchy and are included in the gate-level
Makefile test-module list. The subsystem SV unit intentionally uses RTL state
to align exact byte/engine edges and runs only in the RTL Python runner.
All original waveform assertions and version checks remain intact.

## Comparable generic synthesis

The saved single-engine synthesis snapshot matches the baseline submission
sources. Both baseline and final reports use the same generic `synth -noabc`
flow. Reports are in `test/sim_build/synth_final/synthesis.log` (single engine)
and `test/sim_build/synth_dual_pio_final/synthesis.log` (dual engine).

| Generic metric | Single engine | Dual engine | Change |
| --- | ---: | ---: | ---: |
| Cells including submodules | 10,030 | 20,467 | +10,437 |
| Mux cells | 5,207 | 10,541 | +5,334 |
| Flip-flop cells, all variants | 1,218 | 2,401 | +1,183 |
| IMEM + FIFO data storage bits | 768 | 1,536 | +768 |

The extra storage and datapaths support two simultaneous independent ordinary
instructions; the sampler, host nibble adapter and physical pad logic have one
instance each. Synthesis emits the expected warning that the sampler history
array is replaced with registers. There are no inferred latches or reported
structural problems. Icarus's final RTL compilation has no warnings.

Generic cells are not CMOS5L mapped cells, physical area or timing measurements.
No percentage of the physical tile budget can be derived directly from these
counts. The historical single-engine routed utilization and doubled-area planning
reference remain documented in [the area budget](architecture_area_budget.md).

## Remaining physical qualification

This host has no installed WSL distribution, Docker, Librelane, OpenROAD or
KLayout available on PATH. `PDK_ROOT` is unset and there is no local gate-level
netlist. Consequently the two-engine CMOS5L place-and-route, all-corner STA,
DRC/LVS and functional gate-level run have **not** been performed. No new FPGA
bitstream or board interoperability result is claimed.

The existing `.github/workflows/gds.yaml` remains the physical build entrypoint;
it consumes the updated submission manifest, and its gate suite uses all 39
pin-level tests. Physical qualification requires running it on the implemented
revision and inspecting actual area/congestion, setup/hold at all required
corners, clock distribution, and dedicated-output/pad-OE timing. The historical
single-engine slow-corner setup warning is still relevant and is not resolved
by the functional tests or generic synthesis in this update.

The RTL implementation is functionally validated. Release acceptance at 50 MHz
within the 8x4 allocation remains pending physical evidence.
