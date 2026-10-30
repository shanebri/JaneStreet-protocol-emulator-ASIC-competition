# Project status and qualification

Updated 2026-10-29. This page is the current status reference; dated experiment
reports retain their original measurements and checkpoint decisions.

## Implemented design

The ASIC is a dual-engine programmable protocol emulator, ISA/host revision
`0x21`, dual capabilities `0x50490102`. Each engine has a 32x16 writable
instruction memory, 32-bit X/Y/OSR/ISR and independent four-word TX/RX FIFOs.
Host access uses the synchronous low-nibble-first four-bit bus; engine selection
is banked. Eight dedicated outputs and four bidirectional protocol pads have
exclusive ownership. Six inputs are synchronized; the pads support open drain
and optional filtering. Protocol framing is firmware.

The allocation is 8x4 Tiny Tapeout tiles in IHP SG13CMOS5L, with a 20 ns
(50 MHz) clock. No SRAM macro, DMA, fractional divider, FIFO joining, USB or
Ethernet implementation is present. See the [datasheet](info.md),
[per-engine contract](pio21_contract.md), [dual-engine contract](dual_pio.md),
[ISA](isa.md) and [storage architecture](memory_architecture.md).

## Qualified ASIC baseline

The completed [GitHub Actions run 40938542430](https://github.com/shanebri/JaneStreet-protocol-emulator-ASIC-competition/actions/runs/40938542430)
qualifies source commit `bb7c5ef3c54a7ae2733bbfae82aa940016375007`:

| Check | Evidence/result |
| --- | --- |
| GDS build and strict post-route signoff | Passed |
| Extracted setup/hold, slew/capacitance/fanout | Passed all three required corners |
| Parasitic coverage | Zero filtered annotation gaps in all corners |
| Routing DRC / Magic DRC / illegal overlaps | Zero final errors |
| Antenna | Zero violating nets/pins |
| Netgen LVS | Circuits match uniquely; all seven error/difference fields zero |
| Tiny Tapeout precheck | Completed successfully |
| Functional gate-level tests | 39 passed, zero failed/skipped |
| Layout viewer | Completed successfully |

The production workflow uses pinned Tiny Tapeout action/support-tools revisions,
LibreLane `3.1.0.dev3`, and the audited route finalization step. Configuration and
exact pins are defined by the repository manifest and flow, not by historical
experiment instructions.

| Corner | Overall setup slack (ns) | Overall hold slack (ns) | Restricted register setup slack (ns) |
| --- | ---: | ---: | ---: |
| Slow, 1.08 V, 125 C | 0.303434 | 0.373120 | 0.988909 |
| Typical, 1.20 V, 25 C | 6.120987 | 0.145750 | 8.026990 |
| Fast, 1.32 V, -40 C | 9.516462 | 0.012811 | 12.118178 |

Setup/hold TNS and violation counts are zero. Fast hold has only **12.8 ps**
margin; slow overall setup has **303 ps**. Any ASIC implementation change must
be compared against its passing parent and repeat the full required checks.
The optional native register-setup `Infinity` summary is a path-selection
artifact, not absent timing coverage; see the [coverage audit](timing_coverage_audit_20261029.md).

| Physical metric | Qualified build |
| --- | ---: |
| Block dimensions | 1724.16 x 710.64 um |
| Block area | Approximately 1.2253 mm2 |
| Standard-cell area excluding filler | 380835 um2 |
| Core utilization excluding filler | 31.5216% |
| Standard cells excluding filler | 25640 |
| Sequential cells | 2421 |
| Filler cells | 78983 |
| Routed signal nets | 25361 |
| Reported routed wire length / vias | Approximately 1.436 m / 171646 |

The [LVS closure record](timing_lvs_closure_20261029.md) explains the serialized
route-short repair. [GDS reports](https://github.com/shanebri/JaneStreet-protocol-emulator-ASIC-competition/actions/runs/40938542430/artifacts/12938512721)
and the [submission artifact](https://github.com/shanebri/JaneStreet-protocol-emulator-ASIC-competition/actions/runs/40938542430/artifacts/12937579269)
identify the qualified output. Artifact retention is finite; preserve release
copies and hashes. A source merge does not independently qualify a different
merge commit's output: inspect the workflow for the exact revision being released.

## Scope of that evidence

KLayout DRC was disabled in the qualified flow; the reported DRC acceptance is
for routing DRC and Magic DRC. Gate simulation uses functional cell models,
without SDF annotation; timing evidence comes from extracted STA. I/O checks
assume the documented synchronous timing contract. They do not establish
arbitrary asynchronous reset release, synchronizer MTBF, board-level electrical
compliance, or successful silicon operation.

## FPGA and repeatable bring-up

The fixed UART demo, standalone UART diagnostic, fixed SPI/Nano tester and
I2C byte-requester wrapper remain available. Their simulation reports are not
proof of programmed-board interoperability.

The new [Python bring-up suite](../tools/bringup/README.md) adds a programmable
FPGA UART-to-host bridge, six shared smoke cases, explicit peer profiles and
saved run bundles. The smoke cases primarily repeat already-covered core
behavior through a deployable control path; they do not replace the deeper
39-test regression. New validation covers bridge framing, corruption/sequence
errors, timeouts, truncated packets and disabled-host rejection.

Local validation passed the six smoke cases through package pins and through
UART/adapter/core, hardware-divisor link checks, four transport tests, five
existing SPI-checker tests, three host-API tests and the original 39 RTL tests.
The Arty top has syntax/elaboration checks with clock primitives black-boxed.
The new bridge has **not** been qualified by Vivado implementation or operated
on connected boards. UART/SPI/I2C peer profiles are implemented but not physically
validated here. Automated waveform acquisition and electrical characterization
are not implemented. A silicon fixture must still implement physical chip-pin
driving; the current FPGA bridge instantiates the emulated ASIC core.

Bring-up work changes no ASIC RTL, timing constraints or production GDS flow;
it introduces no ASIC timing-cone change or consumed timing headroom. This is
not a new extracted signoff measurement.

## Next qualification work

1. Preserve the qualified artifacts and confirm CI for the exact release revision.
2. Build the bring-up FPGA image, inspect timing/DRC/exception endpoints and
   program the board.
3. Run hardware smoke and separately wired UART/SPI/I2C profiles, retaining logs.
4. Add measured waveforms, electrical checks and physical recovery/concurrency
   tests before making hardware interoperability claims.

SRAM and further architecture changes remain separate proposals. Area headroom
alone is not timing closure or a justification to change cycle behavior.
