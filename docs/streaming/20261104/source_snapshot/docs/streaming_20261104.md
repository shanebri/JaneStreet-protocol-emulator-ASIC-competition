# Packed streaming and stretch-goal campaign

Status: packed streaming and the digital USB TX prototype pass RTL and exact
qualified-netlist functional tests. Physical peer validation is pending: the
user reports Arty COM3, but COM3 is not exposed to this runtime, and the USB UART
receiver has not arrived. The qualified ASIC remains active and unchanged.

## Immutable references and regression policy

Fixed budget release: `bb7c5ef3c54a7ae2733bbfae82aa940016375007`, qualified CI
run 40938542430. Active implementation and immediate parent for this campaign:
November 4 state SHA256
`aecf268e7bda1242683b19d238f0f99ea469bf9b00b6df963e042b2d71802062`, bound by
`docs/timing/20261104-headroom/activation.json`. Its historical immediate parent
is October 31 state `8cda1271b19e0395f15568ac628639ba6d55d0930d80f31e93b502bd3ea26074`.
The active receipt verified before implementation. Existing FPGA/bring-up edits,
qualified images and prior FIFO evidence are retained.

The user's budget policy supersedes historical parent-margin vetoes. No ASIC
architecture floors are approved. Proposed floors, if needed for a changed
implementation, retain the original CI setup/hold reserves separately in each
corner; they require a concrete decision before activation and are not asserted
to be silicon-safe margins. Actual setup/hold violations and TNS, electrical,
coverage and physical limits remain unchanged. Parent differences alone use an
absolute numerical-tie tolerance of 0.000001 ns. Cumulative consumption always
uses the fixed CI release. Firmware/software changes with identical ASIC inputs
consume zero additional physical margin; inherited measurements are labelled
as inherited, not fresh extraction.

## Feature contract, established before implementation

* New opt-in finite UART-TX and full-duplex SPI-mode-0 programs use the existing
  ISA, host transactions, reset, START/STOP/RESUME and four-word FIFO behavior.
  Existing examples and defaults retain their behavior. No ASIC RTL, clock,
  constraints, pad ownership logic or physical recipe changes are included.
* A stream starts with one TX header word containing payload byte count minus
  one, followed by payload words. Empty payloads are rejected before host side
  effects. Supported transfer lengths are 1..65536 bytes.
* UART payload words contain up to four bytes, first byte in bits 7:0; wire bits
  remain 8N1, LSB first, with 14 SM ticks per bit. PULL IFEMPTY occurs before the
  start bit. Inter-frame spacing retains the 143-tick continuous example period
  when unstalled. The program HALTs after exactly the declared bytes.
  With header and payload prefetched, the first start bit is the sixth SM
  attempt: one enabled clock plus five divider periods after accepted START.
* SPI payload words place the first byte in bits 31:24, MSB first. CS is released
  between every byte as in the existing example. SCLK remains mode 0, with
  eight-tick half-periods, first rise eight ticks after CS assertion and CS
  release four ticks after the final falling edge. Unstalled frame periods
  remain 138 SM ticks. FIFO backpressure occurs with CS high and SCLK low.
  The first CS assertion is likewise the sixth SM attempt when prefetched.
  The physical Nano profile additionally waits for synchronized READY before
  each assertion, adding a documented wait tick outside the selected interval.
* SPI RX packs four received bytes per word, first byte in the highest valid
  byte. A final 1..3-byte word is right-aligned and flushed before HALT. No
  padding byte appears on either wire. Full RX words appear after four frames;
  partial RX appears at the declared end, so sparse single-byte visibility is
  explicitly different from the existing per-byte RX program.
* Packing delays the earliest byte's host visibility until its group completes
  (up to three more SPI frames plus the PUSH tick). Blocking RX service may
  extend that latency. No hidden timeout flush is implemented.
* Reset clears queue/shift/count/host state under the existing contract and
  retains IMEM. START resets OSR/ISR and counters for a new stream. STOP and
  disable freeze waveform state; they are not normal framing operations.
  Restart requires STOP/FIFO_CLEAR and a complete new header/payload.
* The batching host driver serializes an entire bank service operation, polls
  actual FIFO levels, drains only observed RX words, and writes only observed
  free TX slots. It selects a FIFO once per batch. Concurrent engine progress
  can only create additional room/data; another client must not share a stream's
  bank outside the same transaction lock. No side-effecting operation is retried
  after an indeterminate transport failure.
* Existing full simultaneous pop/push, old-head reads and no empty fall-through
  semantics remain unchanged. Exact pin-level tests cover length tails, order,
  stalls, restart, bank isolation and simultaneous operation.

## Sequence and evidence boundaries

1. Implement packed firmware and batching; compare it with a byte-per-word
   control under the same payloads, rates, bank scheduling and service delays.
2. Run sustained FPGA peer validation when the Arty/Nano/UART receiver are
   connected. Initial serial inventory found no ports. Physical evidence cannot
   be replaced by simulation; preserve the qualified FPGA images.
3. Derive packet-interface ownership, lengths, partial completion, credits and
   storage requirements from the measurements. Until physical runs exist, those
   requirements remain provisional.
4. Select and prepare a specific USB/Ethernet timing/interface prototype from
   the documented roadmap. Independent feasibility work can proceed while
   hardware is unavailable; it does not count as completing physical stage 2.

## Provisional packet interface v0

One active packet per engine has an immutable protocol, byte length, payload,
sequence identifier and completion/error state owned by the host. Submission
copies the payload; queue occupancy is a credit snapshot, never a packet-complete
indicator. Completion requires all declared TX words submitted, all expected RX
words consumed, HALT observed, no FIFO error and no residual queue contents.
UART completion therefore follows the final stop bit, not the final host write.
SPI completion includes flushing the partial RX word.

RX ownership transfers to the host one complete word at its existing snapshot
pop edge. The host uses packet length to distinguish the final 1..3-byte tail;
no new per-word metadata is encoded into payload bits. A partial RX read still
pops once under the unchanged host contract. Transports must finish its saved
bytes or abandon the entire packet as indeterminate. There is no automatic
retry or implicit replay after failure. Reset/abort invalidate completion and
require a new explicit submission, STOP/FIFO_CLEAR and START.

Four packed FIFO words hold 16 useful bytes per direction; the active OSR/ISR
can hold an additional word but is not a substitute for a documented queue
credit. The initial header consumes one prefetched TX slot. Storage selection
will use measured service gaps and latency requirements rather than assume
eight words or a macro is necessary. This interface is implemented in host RAM
and existing queues; no general PIO load/store or ASIC packet RAM is added.

## Selected stretch prototype: USB low-speed digital packet TX

The independent first prototype targets DATA0/DATA1 packets with 0..8 payload
bytes at 1.5 Mbit/s. Host software prepares CRC16, bit stuffing and NRZI line
symbols; an opt-in PIO program emits logical J/K/SE0 and a TX-enable marker.
Symbols include explicit 33/34-clock durations at the unchanged 50 MHz clock.
The PIO program consumes four symbol commands per FIFO word. Its header is
symbol count minus one; each command contains two line-state bits and a six-bit
loop count. Duration is loop count plus five clocks, including instruction
overhead. The final marker releases at the end of the final J symbol.

Reset/STOP/disable retain their existing behavior. A mid-packet TX starvation
holds the current symbol and invalidates packet timing; the host must provide
bounded service or a future autonomous packet feeder. Tests must detect this
failure, not label a resumed stretched waveform as valid USB. Logical symbols
are test outputs only. No USB connector is driven, no transceiver is selected,
and receiver phase tracking, token/handshake deadlines, enumeration and
electrical compliance remain future work. This is a timing/interface prototype,
not an operational USB device or an activated ASIC feature.

Protocol reference: USB 2.0 original specification, sections 7.1.8–7.1.11 and
8.2–8.4 ([USB-IF distribution](https://www.usb.org/document-library/usb-20-specification),
[original specification mirror](https://bitsavers.trailing-edge.com/components/usb/USB_2.0_2000.pdf)).

## Measured benefit and storage decision

All comparisons below drive the actual nibble host and check exact payloads,
UART frames, SPI phase widths, CS framing, FIFO flags and clean terminal state.
The finite stream header is included in TX word counts. It deliberately adds
startup parsing relative to the old single-byte examples. Those examples and
the existing ISA/host cycle contracts are unchanged.

At fast dividers 1/1, 256 bytes per protocol and a recurring 512-clock service
pause, the four-word results are:

| Policy | Completion clocks | SPI blocked ticks | UART blocked ticks | SPI TX / RX words | UART TX words |
| --- | ---: | ---: | ---: | ---: | ---: |
| Byte per word, one word per visit | 150464 | 113011 | 111764 | 257 / 256 | 257 |
| Packed, one word per visit | 37568 | 529 | 0 | 65 / 64 | 65 |
| Packed, batched | 37048 | 0 | 0 | 65 / 64 | 65 |

The selected packed/batched policy completes this test **4.0613 times faster**
and reduces aggregate FIFO data-word transactions from **770 to 194** (74.8%).
This is a workload result, not a new maximum clock or universal throughput gain.
At practical UART/SPI dividers 31/4 the wire time is already UART-limited, so
packing reduces host work and prevents the observed SPI stalls rather than
shortening the entire dual-protocol transfer substantially. At the practical
1024-clock pause, the byte-per-word SPI has 3326 blocked SM ticks while both
packed policies have zero in the 32-byte-per-protocol test.

Long runs prevent initial FIFO reserve from concealing a service deficit:

| Packed case, 512-clock pause | Bytes per protocol | Completion clocks | SPI / UART blocked ticks |
| --- | ---: | ---: | ---: |
| Four words, single-word service | 1024 | 150464 | 7441 / 2369 |
| Eight words, single-word service | 1024 | 150304 | 5089 / 17 |
| Four words, batching | 1024 | 146684 | 0 / 0 |
| Eight words, batching | 1024 | 146588 | 0 / 0 |
| Four words, batching | 4096 | 586152 | 0 / 0 |
| Eight words, batching | 4096 | 586060 | 0 / 0 |

The eight-word rows are RTL diagnostics using the previous isolated unqualified
source. They do not change its physical-signoff rejection. The four-word packed
policy addresses this measured problem without its 16.7% cell-area increase.
Batching can service more than one accumulated word in a visit; adding storage
to the single-word policy only postpones its recurring service deficit.

The [raw matrix](streaming/20261104/rtl_final/measurements.json) and
[long four-word run](streaming/20261104/long4/measurements.json) retain service
costs and separate TX/RX stalls. The finite tests establish the reported windows,
not an unbounded guarantee or measured PC scheduling limit.

## Budget ledger and unchanged physical qualification

ASIC source/configuration, the repair recipe, models and exact gate netlist
remain identical to the active qualification. No additional sequential cells,
clock sinks, standard-cell area, timing endpoints or exceptions are introduced.
The actual retained netlist has 2421 clock sinks and 380951 um2 standard-cell
area excluding filler. Firmware changes can alter switching activity; no new
power or analog measurement is claimed.

The following values are **inherited extracted results on that identical
implementation**, not fresh extraction. Approved floors and remaining approved
budgets are unassigned in all six checks. The proposal retains fixed-CI reserves
only as a future decision option, with no claim of a silicon-safe floor.

| Corner / check | Parent = candidate slack, ns | Increment consumed, ns | Proposed floor, ns | Proposed reserve remaining, ns | Cumulative consumed from fixed CI, ns |
| --- | ---: | ---: | ---: | ---: | ---: |
| Slow setup | 0.532949699 | 0 | 0.303433731 | 0.229515968 | -0.229515968 |
| Slow hold | 0.561024798 | 0 | 0.373120101 | 0.187904697 | -0.187904697 |
| Typical setup | 6.249411832 | 0 | 6.120986558 | 0.128425274 | -0.128425274 |
| Typical hold | 0.264246299 | 0 | 0.145750305 | 0.118495994 | -0.118495994 |
| Fast setup | 9.689972654 | 0 | 9.516461666 | 0.173510988 | -0.173510988 |
| Fast hold | 0.089365851 | 0 | 0.012811419 | 0.076554432 | -0.076554432 |

The smallest absolute margins remain slow setup (532.950 ps) and fast hold
(89.366 ps). There is no new limiting ASIC path. The inherited slow host-control
path to engine-1 output state and fast IMEM read-address hold family remain the
relevant limits. Actual endpoint identities are derived from the qualified NL
in the [campaign receipt](streaming/20261104/receipt.json). Additional endpoint
floors are unassigned because this increment adds no hardware endpoint.

The parent already passed complete three-corner extracted timing/electrical,
coverage, clock/contact/pin audits, physical DRC/antenna, actual-GDS LVS,
precheck and 39 exact-netlist gate tests. Its activation verifier still passes.
These results remain applicable through exact input identity. This campaign
adds firmware-specific functional tests on that exact netlist; it does not
substitute RTL simulation for changed-design physical qualification. Any future
FPGA feeder or ASIC change must receive its own complete applicable qualification.

## Qualification, artifact identities and remaining work

| Evidence | Result |
| --- | --- |
| Existing ASIC regression | 39/39 pass, plus its FIFO/host/pad/frontend/I/O units and timing tools |
| New packed-stream host units | 6 pass |
| USB preparation/parser units | 3 pass; known CRC/sync vectors and checked-in image agreement |
| Packed streaming pin tests | 4 pass on RTL and exact qualified gate netlist |
| Long four/eight-word diagnostics | Pass, including 4096 bytes per protocol |
| USB digital packet prototype | 2 pass on RTL and exact qualified gate netlist; 14 DATA0/DATA1 vectors plus deliberate starvation rejection |
| Full physical ASIC qualification | Preserved and verified on identical hardware inputs |
| New FPGA image | None; existing qualified bridge v2 image retained |
| Physical UART/SPI peer validation | Pending receiver/wiring/port access; no physical peer run claimed |
| Physical waveforms/electrical results | Not acquired |
| Remote CI | Workflow added; no new remote run claimed |

Early failed attempts remain under `test/sim_build/streaming_20261104_01*`:
an insufficient USB test completion bound and a core regression started before
all new `.hex` files were generated. The final tests retain both source and
generated images, use fresh outputs and pass without skips. Each run records
its own software hashes and snapshots; earlier measured harness versions remain
available even when later input validation was strengthened.

The reviewable implementation is the three new assembly/hex pairs, the
`tools/streaming` package, new tests and independent streaming CI workflow.
The [evidence index](streaming/20261104/evidence_sha256.json) binds results and
runner versions. The inherited ASIC netlist SHA256 is
`49687f75688eb8870bd2b3eb2dfafdc23fb0b4c637b69a82dff289244f78589c`;
the unchanged SDC SHA256 is
`7088ce29adb0f7213b0f3ed4b76177f104819061b87b32bf4f166ff50e055d59`.
The preserved FPGA bridge v2 bitstream remains
`624e969ab52f0a32527cfea3c4c325e51bf328d14dce2d9d64d0fa7bdac271e9`.
Gate models are functional, without SDF; timing evidence is the retained
qualified extracted signoff.

The [provisional packet interface](packet_stream_interface_20261104.md) proposes
two 128-byte FPGA-side command slots. A conservative worst-case eight-byte USB
packet script fits in 120 bytes including its PIO header, plus an eight-byte
descriptor. No packet RAM or new feeder is implemented. The digital TX
prototype demonstrates a bounded line schedule and highlights the need for
local autonomous feeding; it establishes no receive, handshake, enumeration,
transceiver or electrical compliance. Raw simulated logical-line samples are
retained with its test records.

Recommendation: **retain the opt-in packed firmware/host software for physical
evaluation**, keep four-word ASIC queues for the measured workload, and retain
the USB program as a digital feasibility prototype. Physical stage 2 remains
open. Stages 3 and 4 are provisional independent work, not evidence that stage 2
has passed. The next concrete step is the prepared physical peer run once the
receiver and confirmed wiring are available, followed by an autonomous FPGA
packet-feeder design if its measured service gaps justify it. No ASIC successor
or FPGA image is activated by this campaign.
