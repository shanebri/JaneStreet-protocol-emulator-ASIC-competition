# Autonomous FPGA packet feeder — board validation pending

The Arty wrapper now supports two complete, immutable USB low-speed logical-line
scripts on the existing revision-0x21 8×4 ASIC. Both engines can execute without
PC requests after launch. The firmware generates DP/DM test levels and a TX
marker; USB PHY, RX, token/handshake processing and enumeration remain outside
this implementation. The feeder branch includes packed streaming and the
revision-0x21 baseline tests. Use the preserved baseline image for its separate
physical qualification campaign.
Run that freeze campaign from `codex/rev21-8x4-baseline-tests`: its checker
deliberately requires the original FPGA inputs. This feeder image is a separate
FPGA candidate on the same ASIC revision.

## Ownership and execution

Each slot follows FREE=0 → HOST_FILL=1 → READY=2 → ACTIVE=3 → COMPLETE=4.
A descriptor contains a 32-bit sequence, engine and symbol count minus one.
The slot accepts 29 ordered 32-bit payload words, at most 116 timed symbols;
the worker generates the PIO length header. Header plus payload uses at most
120 bytes, fitting the original 128-byte slot budget with the descriptor.
Padding past the declared symbol count is never transmitted.

Configure stopped engines first. COMMIT requires every declared word and no
unfinished half-word. READY/ACTIVE/COMPLETE reject edits. The other slot can
be uploaded during execution. LAUNCH clears the selected queues/errors,
prefills up to four words, then starts the engine. Subsequent writes obey
observed FIFO credits. Round-robin arbitration keeps each four-byte TX word
atomic, preserving per-engine staging and selectors. LAUNCH_BOTH atomically
checks two READY slots targeting different engines. Individual launch rejects
an engine already owned by an ACTIVE slot. Starts overlap but are not on the
same clock edge.

While either worker is ACTIVE, direct READ, WRITE, ENABLE and RAW_BEAT return
BUSY (status 5). Upload/status, trace and core reset remain available.
Completion requires HALT, every declared word committed, empty queues and
clear errors. It retains sequence, engine, committed TX words including the
header, and pre-cleanup status/levels/errors until RELEASE. Result codes are
OK=0, ABORTED=1, ENGINE_ERROR=2 and TIMED_OUT=3. There is no packet RX count.

ABORT during fill/ready discards the upload and returns FREE. During execution
it lets an issued byte retire, snapshots terminal state, then aborts, clears
queues and releases protocol directions. A word counts only if its final
commit byte retired. The default watchdog is 500,000 core clocks (10 ms at
50 MHz), including preparation/arbitration; cleanup adds bus cycles. The
synchronous adapter must continue acknowledging requests. A peer worker can
complete through another worker's abort/watchdog cleanup.

A partial waveform is failed. Dedicated output levels retain the core's
existing abort behavior, so the marker can remain asserted. Reconfigure the
stopped engine before a fresh submission. Reset invalidates slots, fragments
and completions, resets adapter phase and releases the core under its existing
contract. No retained RAM bits are valid. No side effect is retried/replayed.

## Serial interface

Legacy INFO remains version 2; opcodes 1–14 retain their meanings. Feeder
requests use `C3 sequence opcode address value_lo value_hi 00 XOR`. INFO and
STATUS below return four little-endian data bytes; others return zero data and
zero reserved bytes. Known invalid commands return status 2; disabled feeder
capability returns 3. Slot and engine are 0 or 1.

| Opcode | Operation | Address | Value |
| ---: | --- | --- | --- |
| 15 | INFO | 0 | 0; reply 1,2,29,3 (API, slots, words, capabilities) |
| 16 | SEQUENCE_LOW | slot | Sequence bits 15:0, FREE only; invalidates old sequence |
| 17 | SEQUENCE_HIGH | slot | Bits 31:16; accepted low half required |
| 18 | BEGIN | slot OR (engine << 1) | Symbol count minus one, 0..115; consumes sequence |
| 19 | WORD_LOW | slot | Next ordered word bits 15:0, HOST_FILL only |
| 20 | WORD_HIGH | slot | Bits 31:16; accepted pair appends one whole word |
| 21 | COMMIT | slot | 0 |
| 22 | LAUNCH | slot | 0 |
| 23 | ABORT | slot | 0 |
| 24 | RELEASE | slot | 0, COMPLETE only |
| 25 | STATUS | slot OR (query << 1) | 0 |
| 26 | LAUNCH_BOTH | 0 | 0, atomic readiness/collision check |

Capability bits 0/1 indicate two workers/dual launch. STATUS query 0 packs
state at bits 2:0, result at 4:3 and engine at 5. Query 1 returns sequence.
Query 2 packs committed words at 5:0, status at 13:6, levels at 21:14 and errors
at 29:22. Query 3 returns watchdog clocks. BEGIN, accepted abort/release and
reset clear fragment validity. A damaged exchange requires reset and a fresh
submission. The Python `Feeder` client bounds polling and verifies sequence;
it returns terminal failures for inspection without replay.

## Qualification and regression

Vivado 2026.1 built the Arty A7-100T image with the original XDC:
**5.050 ns setup / 0.049 ns hold**, exceeding the v2 parent's required
4.871 / 0.047 ns by 179 / 2 ps at report precision. DRC has zero findings,
including warnings. CDC reports 14 safe endpoints and zero unsafe, unknown or
missing-ASYNC_REG endpoints. Timing coverage has zero no-clock registers and
unconstrained internal endpoints. Utilization is 5,871 LUTs, 1,643 registers
and seven RAMB36 tiles: +782 LUTs, +339 registers, no added BRAM versus v2.

The image is `.bringup/feeder-builds/20261107-01/arty_bringup_top.bit`, SHA-256
`b1d10fbefb043bcc4ab657220a0ee4ecfbcbd2b64eccb9a5b0f06b9c7ae0bc0b`.
The [receipt](fpga_packet_feeder_receipt.json) and saved reports anchor it.
ASIC sources, manifest and constraints are unchanged. Active ASIC state remains
`aecf268e7bda1242683b19d238f0f99ea469bf9b00b6df963e042b2d71802062`;
incremental ASIC area and timing-margin consumption are zero.

Tests cover quiet-PC packets, concurrent output, upload during execution,
reversed slot/engine assignments, immutable uploads/bounds, early HALT,
abort/watchdog isolation, reset in flight, sequence retention and reuse.
The serial suite also retrieves both waveforms through the actual FPGA observer
and decodes synchronized input loopbacks. The worker (five), bank (two) and
USB timing (two) tests pass against the exact qualified functional gate netlist
`49687f75688eb8870bd2b3eb2dfafdc23fb0b4c637b69a82dff289244f78589c`.
The earlier reset-X diagnostic was Icarus 12 leaving IHP delayed model pins
undriven. Matching Icarus 13 and the pinned runtime resolves it without RTL/PDK
edits. These are functional gate tests without SDF signoff.

Run from this branch with Python requirements and Icarus installed; use fresh
output paths. CI includes feeder unit, worker, bank and serial suites.

```sh
python -B -m unittest discover -s test -p test_feeder_tools.py -v
python -B tools/streaming/run_sim.py --module test_packet_feeder --out test/sim_build/NEW/worker
python -B tools/streaming/run_sim.py --module test_packet_feeder_bank --out test/sim_build/NEW/bank
python -B tools/bringup/simulate.py --packet-feeder
python -B tools/bringup/build.py --packet-feeder --port COM3 --out .bringup/feeder-builds/NEW
```

For gates add `--gates --qualified-root /absolute/path/to/production` and
`--iverilog-bin /path/to/icarus13/bin` to run_sim.py. Receipts record exact
sources, simulator, gate runtime and results.

## Board run

Programming and physical capture remain pending. Program the selected feeder
image in Vivado Hardware Manager when back at the FPGA. Copy its generated
fixture privately and set the actual control port, retaining the image hash.
Install the host dependency with
`python -m pip install -r tools/bringup/requirements.txt`.
The capability query checks the interface, not programmed fabric identity;
the operator must select the matching bitstream. A second USB-UART adapter
is not needed for this feeder test.

With capture.mode=none, the runner validates completions and records waveforms
as NOT_ACQUIRED. For sampled physical evidence, disconnect other peers from
these pins, wire the loopbacks and confirm the fixture:

| Engine / signal | Arty output | Observer input |
| --- | --- | --- |
| 0 / DP | JA1 (out0) | JC1 (pad0) |
| 0 / DM | JA2 (out1) | JC2 (pad1) |
| 0 / marker | JA3 (out2) | JC3 (pad2) |
| 1 / DP | JB1 (out3) | JC4 (pad3) |
| 1 / DM | JB2 (out4) | JA4 (in0) |
| 1 / marker | JB3 (out5) | JA7 (in1) |

```json
"capture": {
  "mode": "fpga",
  "loopbacks_confirmed": true,
  "loopbacks": {
    "pad0": "out0", "pad1": "out1", "pad2": "out2",
    "pad3": "out3", "in0": "out4", "in1": "out5"
  }
}
```

The default uploads two different eight-byte packets, launches both, sends no
requests for 20 ms, then retrieves completions and all 8192 observer samples.
It triggers on the first internal marker before physical input synchronization.
Internal symbol timing is strict; physical decoding allows three sampled clocks
at edges for synchronization/skew, still checking CRC, PID, stuffing and exact
payload. It checks input/output correlation and released pad directions.
This measures nominal-clock digital behavior, not analog USB compliance.

```sh
python -B tools/streaming/feeder_hardware.py --fixture .bringup/feeder.local.json --out .bringup/runs/feeder-001
python -B tools/bringup/analyze.py --run .bringup/runs/feeder-001 --out .bringup/analysis/feeder-001 --require-physical-waveforms
```

Use `--engine 0` or `--engine 1` for a single slot and declare only that engine's
three loopbacks. Fresh sealed bundles retain raw traffic, completions, image/
software/firmware hashes, timestamps, native samples, CSV/VCD and failures.
Analysis writes separately and never changes the source evidence. Baseline
freeze and physical USB functionality still require their own board tests.
