# Packed streaming on the qualified dual PIO

These opt-in programs pack four wire bytes per existing 32-bit FIFO word. ASIC
RTL, host VERSION, queue depth, instruction latency and the active physical
recipe are unchanged. Existing examples retain their behavior.

`uart_packed_stream.asm` sends a finite 8N1 stream; `spi_packed_stream.asm`
transfers a finite mode-0 stream with CS released between bytes. Queue a header
containing byte count minus one, then payload words. UART words are little
endian; SPI words place the first byte in bits 31:24. Final TX padding is never
sent. SPI RX words contain four bytes, with the last 1..3-byte word right-aligned.
RX delivery occurs at group completion or packet end. See the
[contract and campaign report](../../docs/streaming_20261104.md).

Use `streaming.host.configure` and `Stream` with the existing `PIOHost`. Configure
stopped engines, establish output ownership, prefill with `Stream.service()`,
then START. Repeated service calls select each FIFO once per batch and obey
observed credits. A submitted packet is complete only after expected RX words,
HALT, clear error flags and empty queues; `all_transferred` alone is not wire
completion. Transport failures are not automatically retried.

From the pinned WSL simulator environment, use fresh output paths:

```sh
python3 -B -m unittest discover -s test -p test_streaming_host.py -v
python3 -B -m unittest discover -s test -p test_usb_ls_tools.py -v
/home/shane/eda/pio-test-venv/bin/python -B tools/streaming/run_sim.py --out test/sim_build/NEW/rtl --benchmark
/home/shane/eda/pio-test-venv/bin/python -B tools/streaming/run_sim.py --out test/sim_build/NEW/usb --module test_usb_ls_tx
```

Gate runs require the existing pinned Nix EDA environment, Icarus 13 and its
documented libexpat dependency; add `--gates`. The runner selects the exact
active qualified netlist and retains software snapshots, source hashes and XML.
The new CI workflow runs RTL and unit tests; no new remote CI result is claimed.

## Physical FPGA run

No FPGA bitstream change or automatic programming is needed. The runner uses
the preserved qualified bridge v2 image. Copy `fixture.example.json` to a
private campaign folder, provide the three actual ports, and identify the
programmed image. Confirm the concurrent-profile wiring in
[EXTENDED.md](../bringup/EXTENDED.md). Keep the Nano READY signal connected.
The hardware SPI variant adds a WAIT before CS on every byte; bit timing stays
unchanged. Default rates are UART 1200 baud and SPI divider 8192.

```powershell
.tools/venv/Scripts/python.exe -m serial.tools.list_ports -v
.tools/venv/Scripts/python.exe tools/streaming/hardware.py --fixture .bringup/campaigns/streaming/fixture.json --out .bringup/runs/streaming-001
```

The run checks 256 SPI bytes in each direction, 256 UART bytes, queue completion
and FIFO flags, saving raw bridge traffic and peer observations. External peer
bytes are physical functional evidence; it explicitly reports waveforms as
`NOT_ACQUIRED`. Capture complete streams with an external logic analyzer and
retain actual sample rate, channels and raw captures for waveform qualification.
Electrical characterization remains separate. Current physical status is
pending because no serial ports were present during preparation.

## Digital USB low-speed prototype

`usb_ls_tx_symbols.asm` is a laboratory logical-line transmitter using existing
PIO outputs, not a USB device. Host-generated DATA0/DATA1 packets include CRC,
stuffing and NRZI, represented as timed J/K/SE0 commands. The program demonstrates
33/34-clock scheduling at 50 MHz and a TX-enable test marker. No USB connector,
PHY, receive engine, token/handshake implementation or enumeration is provided.
The waveform inspector rejects packets stretched by host starvation.
