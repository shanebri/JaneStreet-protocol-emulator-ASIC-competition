# Packed UART/SPI streaming — hardware validation pending

The opt-in finite-stream programs pack four protocol bytes into each existing
32-bit FIFO word. `tools/streaming/host.py` batches host service using observed
FIFO credits. Existing examples, ASIC RTL, host/ISA revision, four-word queue
depth and FPGA images are unchanged.

The first TX word is byte count minus one (1..65536 bytes). UART payload is
little endian; SPI payload begins at bits 31:24. SPI returns four bytes per RX
word and right-aligns a final partial word. No padding is transmitted. Completion
requires HALT, expected RX words, empty queues and clear errors; queued TX data
alone is not wire completion. Reset/abort abandon the stream and require an
explicit new submission. FIFO stalls occur before UART start bits or with SPI
CS released. SPI RX visibility is delayed until four bytes or the declared end.

The 256-byte fast-rate comparison under recurring 512-clock host pauses takes
150464 clocks with byte-per-word service and 37048 with packed batching. FIFO
data-word transfers fall from 770 to 194. Packed batching also completes 4096
bytes per protocol without stalls in the tested window. These are simulation
measurements, not physical peer results or unlimited-duration guarantees.

Fixed budget reference: qualified CI source
`bb7c5ef3c54a7ae2733bbfae82aa940016375007`. The active physical implementation is
November 4 extracted state
`aecf268e7bda1242683b19d238f0f99ea469bf9b00b6df963e042b2d71802062`.
All additional area and timing-margin consumption are zero because ASIC inputs
are identical. The inherited setup/hold slacks, in ns, are:

| Corner | Setup | Hold |
| --- | ---: | ---: |
| Slow | 0.532949699 | 0.561024798 |
| Typical | 6.249411832 | 0.264246299 |
| Fast | 9.689972654 | 0.089365851 |

Approved architecture floors remain unassigned. The budget policy permits
measured parent-margin losses within approved floors for future changed
implementations; it does not relax actual signoff limits. This increment
preserves the exact qualified hardware and introduces no new timing paths.

The existing 39-test RTL regression passed, along with six host unit tests,
four packed-stream pin tests on RTL and the exact qualified functional gate
netlist, and the long-transfer checks. Qualification of the retained ASIC is
inherited through exact input identity, not a new place-and-route claim.

The streaming-specific bridge adapter is independent of the separate uncommitted
bring-up work. Hardware runs require the recorded bridge v2 image, actual
three-port wiring and a UART receiver. The user reports Arty COM3; it was not
exposed to this runtime, and the receiver had not arrived. Peer runs, physical
waveforms and electrical measurements remain pending. No new FPGA image is
programmed by these tools.

Recommendation: retain for physical evaluation on `codex/packed-streaming`.
Keep the qualified ASIC and FPGA images available. See
[run instructions](../tools/streaming/README.md).
