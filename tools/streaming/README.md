# Packed streaming on the qualified dual PIO

Hardware validation is pending. These opt-in programs and the batching driver
use the unchanged revision-0x21 ASIC and its four-word FIFOs. See the
[feature contract and status](../../docs/packed_streaming.md).

`uart_packed_stream.asm` sends finite 8N1 streams. `spi_packed_stream.asm` sends
finite mode-0 streams with CS released between bytes. Queue byte count minus
one, then payload words. UART words are little endian; SPI places the first
byte at bits 31:24. SPI RX returns four bytes per word, with the last 1..3 bytes
right-aligned. Existing examples retain their behavior.

Use `streaming.host.configure` and `Stream` with `PIOHost`. Configure stopped
engines, establish ownership, prefill with `Stream.service()`, then START.
Service calls select a FIFO once per batch and obey observed credits. Check
HALT, expected RX, empty queues and error flags before declaring completion;
`all_transferred` alone is not wire completion. Never retry an indeterminate
side effect automatically.

With Python, cocotb and Icarus installed, use fresh output paths:

```sh
python -B -m unittest discover -s test -p test_streaming_host.py -v
python -B -m unittest discover -s test -p test_streaming_transport.py -v
python -B tools/streaming/run_sim.py --out test/sim_build/NEW/rtl --benchmark
python -B tools/streaming/run_sim.py --module test_streaming_long --out test/sim_build/NEW/long
```

Gate runs also need the pinned EDA environment and locally preserved qualified
artifacts. Pass `--gates --qualified-root /absolute/path/to/qualified/production`.
The runner records exact netlist/model identities, software snapshots and XML.
Optional eight-word diagnostics require `--depth 8 --diagnostic-design PATH`;
they do not qualify or activate that architecture. CI runs RTL/unit tests.

## Prepared physical run

The runner uses the preserved bridge v2 image identified by
`qualified_bridge.json`. No image is programmed automatically. Copy
`fixture.example.json` privately, set the three actual ports and the preserved
image path, then confirm the programmed-image and wiring facts.

| Signal | Arty A7 | Nano 33 BLE / 3.3 V UART receiver |
| --- | --- | --- |
| SPI MOSI | JA1 | Nano D11 |
| SPI SCLK | JA2 | Nano D13 |
| SPI CS_n | JA3 | Nano D10 |
| SPI MISO | JA4 | Nano D12 |
| SPI READY | JA7 | Nano D2 |
| UART TX | JB1 | Receiver RX |
| Ground | Marked GND | Shared Nano and receiver ground |

Receiver TX/VCC remain unconnected. The hardware SPI program waits for READY
before every CS assertion; bit timing is unchanged. Defaults are UART 1200 baud
and SPI divider 8192. Use the existing Nano 33 BLE SPIS/checker sketch; this
profile is not for a classic 5 V Nano.

```sh
python -m serial.tools.list_ports -v
python tools/streaming/probe.py --port COM3 --out .bringup/probe-001
python tools/streaming/hardware.py --fixture /path/to/private/fixture.json --out .bringup/runs/streaming-001
```

The INFO probe does not reset or start engines. The peer run checks 256 SPI
bytes in both directions and 256 UART bytes, terminal queues and error flags.
It records raw bridge traffic and peer results. It reports waveforms as
`NOT_ACQUIRED`; full waveform/electrical qualification needs separate captures.
No physical peer pass has been recorded yet.

## Digital USB low-speed prototype

`usb_ls_tx_symbols.asm` is an opt-in laboratory logical-line transmitter.
Host-generated DATA0/DATA1 packets include CRC, stuffing and NRZI, represented
as timed J/K/SE0 commands. The program demonstrates 33/34-clock scheduling at
50 MHz with a TX-enable test marker. It provides no USB connector/PHY, receiver,
token/handshake implementation or enumeration. Its inspector rejects packets
stretched by host starvation.

```sh
python -B -m unittest discover -s test -p test_usb_ls_tools.py -v
python -B tools/streaming/run_sim.py --module test_usb_ls_tx --out test/sim_build/NEW/usb
python -B tools/streaming/verify_evidence.py
```

The [combined campaign report](../../docs/streaming_20261104.md) and
[provisional packet interface](../../docs/packet_stream_interface_20261104.md)
retain measured results, inherited timing budgets and pending hardware work.
Historical receipts retain their original machine-local paths and measured
source snapshots. `verify_evidence.py` checks their bytes after relocation.

## Autonomous FPGA feeder

The [two-slot feeder](../../docs/fpga_packet_feeder.md) uploads complete USB
symbol scripts before launch and services both engines locally through the
unchanged four-word ASIC FIFOs. The opt-in FPGA image has passed routed
timing/CDC/DRC; physical validation is pending. Its host API is in
`feeder.py`; `feeder_hardware.py` runs finite packets and saves completion/
optional physical-loopback capture evidence. The guide includes build,
programming, loopback and offline-analysis commands.
