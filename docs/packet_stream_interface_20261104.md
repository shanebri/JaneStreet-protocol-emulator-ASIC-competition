# Provisional packet/stream interface v0

This specification follows the packed-stream measurements. It remains
provisional until sustained physical peer service gaps are measured. It does
not add SRAM, DMA, a FIFO depth change or a new ASIC host map.

## Existing implementation

The host retains packet payloads in host RAM. `Stream` copies payload bytes and
queues a length-minus-one header followed by packed words. Each engine has one
active stream, independent TX/RX staging and one shared locked host connection.
UART emits exactly the length; SPI returns exactly the length. RX tail size is
derived from the descriptor's length, never from payload padding.

Existing FIFO levels are conservative service credits. Read only the observed
RX count and write only the observed free TX slots. FIFO-empty is not packet
completion: UART can still be shifting its last word and SPI may retain a
partial ISR. Completion requires HALT, all declared words submitted/consumed,
zero error flags and no residual queued words. No automatic retry follows an
indeterminate host transaction or an abandoned RX snapshot.

For restart, explicitly abort/stop, clear queues, submit the complete new stream
and START. Reset invalidates completion and host transaction phase while retaining
IMEM under the existing core contract. STOP/disable may stretch active waveforms;
they are not successful packet endings.

## Future FPGA-side autonomous command feeder

The USB digital prototype exposes a different need from FIFO depth: a complete
short timing script must survive PC/USB scheduling gaps once transmission starts.
The proposed first feeder is outside the ASIC, in the FPGA host wrapper:

| Field/resource | Proposed contract |
| --- | --- |
| Slots | Two independently owned 128-byte command slots |
| Descriptor | 32-bit sequence, 16-bit length-minus-one, 16-bit flags/format |
| Slot data | Up to 120 bytes, including the PIO header |
| Ownership | FREE → HOST_FILL → READY → ACTIVE → COMPLETE → FREE |
| Launch | Complete descriptor and immutable command data before READY; explicit launch only |
| Replay | Explicit new submission after error; no automatic replay of a side effect |
| Completion | Sequence, actual TX/RX counts, terminal running/error/queue state |
| Backpressure | Preserve ordered words until accepted; never silently discard |
| Reset | Cancel both slots and clear validity/ownership; retained RAM bits are invalid |
| Concurrent engines | Separate descriptors and bounded fair arbitration on the shared host bus |

This is a design proposal, not implemented FPGA queue RTL. It must preserve
current host acceptance/commit/pop cycles. CDC, active-route timing, electrical
and full FPGA qualification are required before selecting a new image.

## Storage bound and measured motivation

Four existing words hold 16 payload bytes when packed. In the 4096-byte-per-
protocol fast test, batching tolerates the tested recurring 512-clock service
pause without a stalled SM tick; single-word service fails the shorter 1024-byte
test at both depths. Those finite tests support keeping four-word ASIC queues
for this workload, not a universal service-gap guarantee.

For an eight-byte USB DATA packet, a conservative bound is 96 unstuffed bits,
at most 16 inserted bits and three EOP symbols: 115 symbol commands. Four
commands fit per FIFO word, so the complete prepared script including its
header needs at most 120 bytes. Adding the proposed eight-byte descriptor fits
one 128-byte slot. Two slots permit preparing the next script while one runs.

The GPIO-symbol prototype needs one new FIFO word per roughly 132–136 core
clocks. A PC stop-and-wait serial command path has no proven bound at that
scale. Eight-word queues also cannot guarantee an arbitrary PC pause during a
packet. The feeder should accept a complete script before launch and service
the core locally; larger ASIC storage is not yet justified by these results.

Remaining decisions depend on physical measurements: actual bridge throughput,
worst service gap, receiver availability, capture timing, required concurrent
packet count, error recovery and USB response deadlines. A transceiver/receive
interface and protocol-level device behavior require their own contract.
