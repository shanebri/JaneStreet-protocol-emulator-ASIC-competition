# Dual-engine FPGA campaign

This campaign adds persistent dual-engine stress, FIFO/recovery boundaries,
bidirectional pad checks, and a concurrent UART/SPI demonstration. It runs
through the public host interface. ASIC RTL, instruction cycles, submission
configuration and the qualified ASIC physical recipe are unchanged. The v2
observer and raw-nibble requester exist only in the FPGA wrapper.

The infrastructure has simulation coverage; **physical runs on the v2 image are
still pending**. The preserved [October 30 image and smoke evidence](../../docs/fpga_baseline_20261030.md)
remain a separate baseline. See the [v2 implementation report](../../docs/fpga_bringup_v2_20261101.md)
for build identity, timing comparison and qualification status.

## Equipment and wiring

Use the Arty A7-100T, its onboard USB control link, a **Nano 33 IoT or Nano 33 BLE**
SPI peer, and a **3.3 V TTL USB UART adapter**. Select the matching sketch and
`nano_board` value. The IoT sketch uses SAMD21 SERCOM1 and chip select D8.
The BLE sketch uses nRF52840 SPIS and chip select D10.
Follow the [Nano upload instructions](../spi_hardware/README.md#2-load-the-nano-sketch).
Close serial terminals before running. USB upload and runtime ports can differ.

Power boards independently through USB and share signal grounds. Identify pins
from connector markings. UART adapter TX and VCC remain unconnected. Pin mapping
follows the [Digilent Arty A7-100 master XDC](https://github.com/Digilent/digilent-xdc/blob/master/Arty-A7-100-Master.xdc);
Nano wiring follows the [existing verified mapping](../spi_hardware/README.md#1-wire-the-boards).

Use a separate wiring setup for each profile:

| Profile | Connections in addition to onboard USB control |
| --- | --- |
| `dual_engine_stress` | Disconnect protocol peers. JA1/out0 → JC3/pad2; JB2/out4 → JC4/pad3. These are marker loopbacks. |
| `boundaries` | No external protocol connections needed. |
| `recovery` | Disconnect active protocol peers and output loopbacks. JC1/pad0 is deliberately driven low; the observer checks logical drive retention/release. |
| `pads` | Disconnect active peers and **all output loopbacks**. Connect one known 4.7 kΩ pullup from each JC1..JC4 to the Arty's 3.3 V rail. Ground references remain connected. |
| `concurrent` | Nano SPI connections below, USB UART RX on JB1/out3, and capture loopbacks JA1/MOSI → JC1/pad0, JA3/CS_n → JC2/pad1, JB1/UART → JC3/pad2 and JA2/SCLK → JC4/pad3. |

Concurrent peer wiring:

| Signal | Arty | Nano peer / adapter |
| --- | --- | --- |
| SPI MOSI | JA1 | Nano D11/MOSI |
| SPI SCLK | JA2 | Nano D13/SCK |
| SPI CS_n | JA3 | Nano IoT D8 / BLE D10 |
| SPI MISO | JA4 | Nano D12/MISO |
| SPI READY | JA7 | Nano D2 |
| UART TX | JB1 | USB UART adapter RX only |
| Ground | JA5/JA11 or another marked GND | Nano GND and adapter GND |

The loopbacks sample physical I/O input buffers independently of the internal
output nets. Do not reuse the stress loopbacks for the concurrent profile. The
pad profile must have neither set of output loopbacks attached.

## Build and prepare

Run from the repository root, using a Python installation with pyserial:

```powershell
py -m pip install -r tools/bringup/requirements.txt
py tools/bringup/build.py --port COM3
py tools/bringup/prepare.py --list-ports
py tools/bringup/prepare.py --image "PATH/TO/arty_bringup_top.bit" --bridge-port COM3 --nano-port COM4 --uart-peer-port COM5 --out .bringup/campaigns/dual-v2-001
```

Use the actual three distinct ports. Preparation only writes private fixtures
and a `RUNBOOK.md`; it neither programs hardware nor opens a serial connection.
The image hash is pinned into every fixture. Each extended run probes the live
bridge v2 capability. Neither check independently reads back FPGA configuration;
the operator must program the selected file through Vivado Hardware Manager.
The older v1 image supports the original smoke/protocol profiles, not the new
raw-nibble and capture commands.

Pass `--nano-board nano33iot` when preparing an IoT fixture. The
[8x4 baseline campaign](BASELINE.md) selects the IoT peer by default.

Inspect the build's routed setup/hold, DRC, CDC, exceptions and timing-coverage
reports, including the comparison with the passing parent. Keep the preserved
image available. Program the selected qualified candidate, wait for LD7 clock
lock, and run an initial smoke test using that build's generated fixture.

Edit the prepared fixtures to confirm **actual** wiring:

* Stress and concurrent: set `capture.loopbacks_confirmed` to `true` only for
  that fixture's listed loopbacks.
* Pads: confirm `pads.pullups_confirmed` and `pads.active_peers_disconnected`.
  Record the actual pullup values and supply voltage.
* Recovery and boundaries: use their own fixtures, with no output loopbacks.

All confirmations start false. For a functional-only stress or concurrent run,
use `--capture-mode none`; the saved fixture records that override and results
state `NOT_ACQUIRED`. This does not meet a physical-waveform requirement.

## Run each increment

Use the generated `RUNBOOK.md`, changing wiring between profiles. Example:

```powershell
py tools/bringup/run.py --fixture .bringup/campaigns/dual-v2-001/stress.json --suite dual_engine_stress --seed 2201 --rounds 1000 --duration-seconds 600 --out .bringup/runs/stress-001
py tools/bringup/run.py --fixture .bringup/campaigns/dual-v2-001/boundaries.json --suite boundaries --seed 2202 --out .bringup/runs/boundaries-001
py tools/bringup/run.py --fixture .bringup/campaigns/dual-v2-001/recovery.json --suite recovery --seed 2203 --out .bringup/runs/recovery-001
py tools/bringup/run.py --fixture .bringup/campaigns/dual-v2-001/pads.json --suite pads --seed 2204 --out .bringup/runs/pads-001
py tools/bringup/run.py --fixture .bringup/campaigns/dual-v2-001/concurrent.json --suite concurrent --seed 2205 --out .bringup/runs/concurrent-001
```

Every output directory must be new. Start with short stress rounds, then the
long campaign. `--rounds` and `--duration-seconds` are both minimums; stress runs
until both are satisfied. Payload and scheduling random generators are separate,
so elapsed duration can change the number of words without changing the seeded
prefix. The default seed is 2201 and default minimum is 64 rounds.

Profiles check:

| Profile | Scored behavior |
| --- | --- |
| Stress, marker phase | Both engines execute persistent decrement/output loops with different dividers and split output ownership. Interleaved bank reads and protected writes occur while both continue. Coherent X snapshots must decrease; both output markers must keep transitioning. |
| Stress, data phase | Both engines execute persistent blocking echo loops. Tagged bank/sequence/random words are queued in seed-selected host order and drained in reverse bank order. Exact data, ordering, isolation, levels and error flags are checked. |
| Boundaries | RX fills to four, a fifth word blocks at PUSH, and four TX words queue behind it. Rejected overflow, complete ordered draining, empty-read/underflow flags, error clearing, TX starvation and active refill are checked independently for both banks. |
| Recovery | Both engines have full live FIFO state. Disable interrupts partial writes and preserves drive, queues and staged word state. Abandoned RX reads must pop on the first nibble exactly once; disable discards their saved high nibble without undoing a pop. Reset clears partial read/write and snapshot state, architectural/FIFO/staging state and OE, retains IMEM, and permits a fresh restart. A raw two-nibble control proves that packet-spanning writes really work. ABORT release is checked. |
| Pads | Both engine owners drive/release every pad in open-drain mode. Physical input level and logical OE are scored. Ownership transfer is rejected while directions remain active, then succeeds after release of directions. Reset releases all pads to declared pullups. |
| Concurrent | Persistent UART engine 1 and SPI engine 0 run synchronized bursts: four UART bytes and one SPI byte per round, 256 rounds. Independent UART reception, Nano MOSI/MISO records, FPGA SPI RX, FIFO flags, ordering and completion are compared. |

Disable is a **freeze with retained pad drive**. It is not a pad-release command.
STOP also retains drive/state; ABORT and reset release directions. The concurrent
programs are loaded once, then STOP/RESUME between bursts so host refill can
produce deliberate overlap. This is a concurrent protocol demonstration, not a
claim of continuously saturated UART/SPI streams. The marker phase separately
tests continuous engine progress during host traffic.

Default concurrent rates are deliberately slow: UART 1200 baud and SPI divider
8192. The existing Nano ARM protocol requires exactly 256 hardware transfers.
Optional later profiles can use 9600/2048 or 115200/32 (`uart_baud`/`spi_divider`),
each in a new fixture and run. Rates are nominal and rounded to integer core
dividers; the analyzer uses the resulting nominal rates. These faster profiles
still require their own hardware results.
The 115200/32 burst is shorter than a normal control-link round trip. Use
functional-only mode or an external protocol capture at that rate; an FPGA
capture still requires host activity during the overlap and may correctly fail
that check. The default slow profile is intended to demonstrate all three.

## Captures and offline analysis

The FPGA one-shot buffer holds 8192 × 32-bit samples in block RAM. It triggers
on a selected falling edge or immediately, with no pretrigger history, and
samples every 2^N core cycles. Concurrent capture defaults to the SPI 55/AA
rounds (indices 85/170), so MOSI transitions can also be
correlated. All five decoded protocol signals use physical input samples.
Automatic decimation checks both complete burst coverage and at least
eight samples per nominal UART bit/SPI clock. A configuration that cannot meet
both fails rather than aliasing silently.

Channels are `out0..7`, `pad0..3`, `in0..1`, `oe0..3`, `enabled`, `rst_n`,
`host_write_bin` and `host_read_bin`. Only pad/input channels pass through
physical input buffers and two observer synchronizer registers. All channels
then pass through one shared observation register before trigger/capture, keeping
asynchronously asserted clock-loss reset out of block-RAM control paths. This
adds one common observation cycle and does not feed the emulated core. Output and OE
channels are internal nets. Host activity bins OR strobes between samples;
they are not exact host-edge timestamps. Physical loopbacks permit sampled
correlation with internal outputs. Their synchronizer lag is allowed explicitly.

Each capture retains native little-endian `samples.bin`, digital `samples.csv`,
`samples.vcd`, capture configuration and channel scope. The timebase is the
nominal 50 MHz FPGA clock, not a calibrated instrument. Dumping one buffer over
the control UART takes roughly 12 seconds plus host overhead; progress is logged.
The core clock continues throughout capture retrieval.

```powershell
py tools/bringup/analyze.py --run .bringup/runs/concurrent-001 --out .bringup/analysis/concurrent-001 --require-physical-waveforms
```

Analysis is offline, writes a fresh directory and never edits the source run.
It checks every indexed file hash/size, verifies raw packet checksums, sequence,
write counts, fragmented replies and status, replays deterministic expectations,
and decodes UART 8N1 / SPI mode 0 MSB-first. Exact bytes, frame counts and protocol
overlap must match. FPGA observer captures must show host activity during the
overlap. Declared loopbacks must correlate, not merely toggle. Framing errors,
partial SPI frames, insufficient sampling, missing columns and incomplete
captures fail. `decoded_transactions.jsonl` retains per-frame decoded results.

Exit 0 means the requested functional checks and provided digital captures pass.
Exit 1 means failure/integrity error. With `--require-physical-waveforms`, exit 2
means functional/digital checks passed but validated physical-input captures are
missing. Simulation can never earn physical-input evidence. A normal pass with
capture disabled explicitly reports `NOT_ACQUIRED`.

Open-drain results establish sampled low/released-high levels with declared
pullups and logical OE. They do not measure high impedance, rise time, contention
current, voltage compliance or analog signal integrity. No FPGA result qualifies
ASIC extracted timing. The report keeps analog/electrical qualification marked
`NOT MEASURED`.

## Import a later external instrument capture

An oscilloscope or logic analyzer is optional for initial digital bring-up.
When available, export a complete concurrent burst as CSV with digital 0/1
columns, idle-high CS at the beginning, all four UART frames and the complete SPI
transaction. Capture UART, SCLK, MOSI, MISO and CS with at least eight samples per
bit/clock. Retain analog instrument files separately if analog measurements are
needed. A mapping file identifies column names, units, instrument and image:

```json
{
  "instrument": "model / serial / sample-rate / threshold settings",
  "image_sha256": "COPY EXACT HASH FROM THE RUN MANIFEST",
  "time_column": "Time [s]",
  "time_unit": "s",
  "channels": {"uart": "D0", "sclk": "D1", "mosi": "D2", "miso": "D3", "cs": "D4"}
}
```

```powershell
py tools/bringup/analyze.py --run .bringup/runs/concurrent-001 --out .bringup/analysis/external-001 --import-csv capture.csv --mapping capture.local.json --case 0 --require-physical-waveforms
```

The case must identify one scored round from that run. Raw CSV and mapping are
copied into the separate analysis bundle and sealed. If the first sample is
already the UART falling trigger, explicitly add
`"trigger":{"channel":"uart","falling":true}` to the mapping. Otherwise retain
idle before the first frame. Imported data from a simulation run remains
simulation evidence even if an instrument label is supplied.

## Evidence and failure handling

`manifest.json` saves the fixture, seed, selected image hash, commit/dirty state,
harness/assembler/checker hashes, example firmware hashes, peer sketch hash and
timestamps. The peer sketch hash identifies the expected local source, not
independent readback of Nano flash. `results.jsonl` saves expected/observed
assertions and intermediate observations. `transport.jsonl` retains raw bridge
TX intent/write counts/RX chunks, full responses, partial timeouts and peer bytes.
Peer startup bytes discarded before the first burst are explicitly recorded.
No in-test peer bytes are silently discarded.

Failures retain `exception.txt`, completed/partial captures and a failed manifest.
`artifacts.json` seals each run and analysis bundle with per-file SHA-256 hashes.
This detects subsequent changes; it is not an external timestamp/signature.
Do not edit sealed bundles or delete failed attempts. Keep operator notes and
reruns in separate directories. Archive raw evidence together with the exact
bitstream and build reports, then copy it to durable storage.

There are no automatic packet retries. A timed-out or corrupt reply may follow
a committed write/FIFO read; the session becomes indeterminate and refuses later
commands. Preserve the failure, press BTN0 to reset the bridge, then use a fresh
run directory. A protocol failure deliberately does not trigger a hidden core
reset that would erase the failing state. Inspect/recover the hardware explicitly.

## Bridge v2 additions and validation

Opcodes 1..6 remain compatible. INFO(7) returns 2; RAW_BEAT(8) drives exactly one
public nibble beat with explicit idle/pulse/idle boundaries; PADS(9) returns
physical sampled inputs and logical OE; INPUTS(10) samples dedicated inputs.
TRACE_ARM/STATUS/READ/CANCEL are 11..14. Only STATUS and READ use four reply data
bytes; checksums and sequence still cover the full eight-byte response. A raw
pending byte is explicitly aborted before a regular atomic byte command.
Trace reset is independent of core reset, so core reset can be captured.

Run software/RTL checks with the existing test environment:

```text
python -m unittest discover -s tools/bringup -p 'test_*.py' -v
python tools/bringup/simulate.py
python tools/bringup/simulate.py --default-baud-link
python tools/bringup/simulate.py --extended
python test/run.py
```

The extended suite exercises real serial framing, bridge logic, public adapter,
both cores, wire-level simulated UART/SPI peers, pullups and captured waveform
analysis. It retains fresh logs, results XML, source hashes and captures under
`test/sim_build/bringup-extended/`. Those artifacts are labelled simulation.
