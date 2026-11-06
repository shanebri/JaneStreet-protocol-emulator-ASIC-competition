# FPGA autonomous packet feeder prototype

This implements the first stage of the [provisional packet interface](packet_stream_interface_20261104.md).

## Cycle and ownership contract

The first milestone uses one slot, engine 0, and the existing USB symbol TX
program at 50 MHz. The caller configures the stopped engine first, then gives
the feeder exclusive ownership of the existing byte-to-nibble adapter until
completion. Commands and the adapter share a clock. The command interface
accepts BEGIN with a sequence and symbol count minus one, then ordered 32-bit
payload words. The feeder synthesizes the PIO header from the count. The fixed
TX format fits up to 116 symbol bytes and the 8-byte descriptor in 128 bytes.
Padding in the final word is outside the declared symbol count.

The feeder accepts COMMIT only after every declared payload word has arrived.
LAUNCH selects the engine, clears its queues and errors, prefills up to four
words, then issues START. The feeder samples free FIFO space before each write
and services subsequent words without further commands. It reports completion
only after HALT and a terminal check of errors, FIFO levels, and the number of
completed writes. A terminal failure stops the engine, clears queues, and
releases protocol directions. Completion remains readable until RELEASE.

ABORT in the fill or ready state discards the upload. During execution it lets
the issued byte retire, then stops and clears the engine and releases protocol
directions. It reports the number of completed writes, including any commit
that retired during abort. The core preserves its dedicated output levels
on abort. Treat any partial waveform as failed. A new launch after abort or
failure requires the caller to reconfigure the engine and submit a new script.
Shared synchronous
reset invalidates slot contents and completion and resets the bus phase. There
is no RX data path or execution timeout in this first milestone. A caller can
abort a stalled execution. The existing nibble accept, commit, and pop cycles
are preserved through the unmodified adapter and core.

Two slots, the serial upload protocol, and dual-engine arbitration are later
increments. CDC review, routed timing, electrical checks and full FPGA
qualification are required before selecting an image.

## Simulation result

Run from the repository root with Icarus Verilog and cocotb installed.

```sh
python -B tools/streaming/run_sim.py --module test_packet_feeder --out test/sim_build/NEW/feeder
```

The five RTL cases cover four decoded DATA waveforms, upload ownership and
capacity, abort and reset with a byte in flight, premature HALT, and the case
where the complete script fits in the prefill. Every waveform matched the
expected payload, PID, CRC, stuffing and 33/34-clock symbol schedule with zero
PC requests after launch. Across the four packets, the largest observed gap
between completed FIFO word writes was 136 core clocks. The eight-byte
all-ones case took 3,930 clocks from launch to completion, including 3,700
clocks on the digital waveform. The existing USB timing and starvation control
tests also passed on RTL.

The feeder and the unchanged USB tests both encountered unknown output values
at reset in a matched functional gate simulation. The input netlist hash was
`49687f75688eb8870bd2b3eb2dfafdc23fb0b4c637b69a82dff289244f78589c`.
This is an open gate-simulation diagnostic. The RTL result supports retaining
the prototype for evaluation. Routed FPGA timing, resource use, board captures,
and electrical qualification are still pending.

## Qualification reference

The immediate parent is `8e421ac543cf17a946b1696ecb3c11baad5acbbf`. The fixed
budget reference remains `bb7c5ef3c54a7ae2733bbfae82aa940016375007` and the
active state remains
`aecf268e7bda1242683b19d238f0f99ea469bf9b00b6df963e042b2d71802062`.
The active recipe and frozen qualification evidence reverified. The feeder
sits outside the ASIC and the existing FPGA bridge image. ASIC inputs are
identical to the immediate parent, so incremental ASIC area and timing margin
consumption are zero. The [packed streaming receipt](packed_streaming.md)
records the unchanged per-corner margins and budget status. Evaluate any future
routed feeder image against its own measured FPGA parent before activation.
