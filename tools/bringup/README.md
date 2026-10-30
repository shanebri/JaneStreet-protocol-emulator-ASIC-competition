# Repeatable PIO bring-up

This suite controls the real synchronous host interface. The same six async
smoke scenarios run against the existing package-pin simulator and the FPGA
serial bridge. UART, SPI and I2C hardware profiles require explicitly wired peers;
they never silently skip missing equipment. ASIC submission sources and GDS
configuration are unchanged.

Its primary purpose is repeatable FPGA/silicon bring-up infrastructure. Most
smoke behaviors are already covered more deeply by the 39-test RTL/gate suite;
the new evidence concerns the programmable control path and its error handling.
See [project status](../../docs/project_status.md) for the exact qualified ASIC
build. A passing smoke run is neither full regression coverage nor timing signoff.

## FPGA preparation (Arty A7-100 Rev D/E)

Build a separate Vivado project for `xc7a100tcsg324-1`. Add **all** current
SystemVerilog sources listed by `info.yaml`, plus:

```
fpga/byte_nibble_host.sv
fpga/spi_test_uart_tx.sv
fpga/bringup_uart_rx.sv
fpga/bringup_bridge.sv
fpga/arty_bringup_top.sv
```

Select `arty_bringup_top`; enable only `fpga/arty_bringup.xdc`. The MMCM supplies
50 MHz, and USB UART operates at approximately 115200 8N1. Build/program the
bitstream and inspect Vivado timing, DRC and exception endpoint resolution.
FPGA place-and-route and hardware operation have **not** been performed here.
Do not treat the simulation result as FPGA timing qualification. The pin mapping
is derived from [Digilent's master constraints](https://github.com/Digilent/digilent-xdc/blob/master/Arty-A7-100-Master.xdc).

| Signal | Connector |
| --- | --- |
| Outputs 0/1/2 | JA1/2/3 (SPI MOSI/SCLK/CS) |
| Dedicated inputs 0/1 | JA4/7 (SPI MISO/READY) |
| Outputs 3/4/5/6/7 | JB1/2/3/4/7 |
| Protocol pads 0/1/2/3 | JC1/2/3/4 |

Use 3.3 V-compatible peers and shared ground; do not join the boards' supply
outputs. Pin numbers refer to connector markings, not viewing orientation.
LD7 indicates clock lock. BTN0 resets the bridge and core. Once programmed,
normal suite execution requires no button presses.

## Run

From the repository root:

```powershell
py -m pip install -r tools/bringup/requirements.txt
Copy-Item tools/bringup/fixture.example.json fixture.json
# Edit COM ports and the actual programmed bitstream path in fixture.json.
py tools/bringup/run.py --fixture fixture.json --suite smoke --out test/output/bringup-001
```

Each output directory must be new. Exit 0 means all requested functional tests
passed; failures exit 1. Each smoke case resets the core and re-arms the host:

1. Revision/capabilities and both engine banks.
2. Seeded scratch-register isolation and interleaved partial word commits.
3. All 32 instruction addresses in both engines, using seeded patterns/readback.
4. Four distinct TX words per engine, simultaneous group execution, independent
   RX order and exact FIFO levels.
5. Blocking execution, disable/re-enable, completion and reset recovery.
6. Walking dedicated output bits and switching/restoring ownership between banks.

`--seed` defaults to 2201. Use `--repeat 100` for a smoke endurance run with
successive seeds, fresh reset per case and first-failure retention.
`manifest.json` records source commit/dirty state,
fixture, image hash, assembly hashes, seed, suite, verdict and timestamps.
`results.jsonl` records verdicts; `transport.jsonl` preserves raw bridge packets
and peer results. Preserve failure directories; do not replace a failure with a
successful retry. Press BTN0 to recover from a truncated/corrupt serial session
before starting a new run. A COM timeout is a failure, not permission to replay a
possibly committed register/FIFO transaction.

### Optional peer profiles

Run each with a fresh output directory, e.g. `--suite spi --out test/output/spi-001`.

- **SPI:** use the existing Nano sketch and wiring in
  `../spi_hardware/README.md`, but program the new bring-up FPGA image. Set
  `nano_port`. The Python profile loads `spi_mode0.asm`, uses divider 32, arms the
  Nano, polls READY, performs all 256 byte values, and reuses the existing
  `Results` checker to require independent success at both endpoints and DONE.
- **UART:** wire dedicated output 0 (JA1) to a separate 3.3 V UART receiver and
  set `uart_peer_port`. Runs `uart_v0.asm` with divider 31 and checks bytes 00..FF
  at 115200. The FPGA USB UART remains exclusively the control link.
- **I2C:** wire a deterministic target to pad0 SDA (JC1), pad1 SCL (JC2) with
  appropriate external pullups. Set the fixture's 7-bit address, write bytes and
  expected response; the example values are placeholders, not a device preset.
  The profile uses the existing `I2C` driver, including its bounded service waits.

Hardware profiles are implemented but have not been exercised on connected
equipment. The underlying protocol firmware/driver has existing RTL regressions.
Functional peer reception does not measure edges, analog levels or setup/hold.
Waveform acquisition, GPIO electrical characterization, I2C fault injection and
long-duration concurrent protocol stress remain additional qualification work.

## Validation and CI

```sh
python -m unittest discover -s tools/bringup -p test_transport.py -v
python tools/bringup/simulate.py
python tools/bringup/simulate.py --default-baud-link
# Optional direct package-pin path:
make -C test COCOTB_TEST_MODULES=test_bringup
```

The serial regression compiles the **submission manifest**, UART RX/TX, bridge
and byte-to-nibble adapter. It rejects corrupt/unknown commands and runs all six
shared smoke scenarios through UART. Baud is accelerated to eight clocks/bit in
simulation; a separate link-only run checks actual divisor 434. CI runs both and the
transport failure tests in addition to existing tests.

## Bridge contract and silicon migration

One outstanding eight-byte command: `C3 sequence opcode address lo hi 00 XOR`.
The XOR includes all previous bytes. Reply: `C3 sequence status data 00 00 00 XOR`.
Opcodes 1=read byte, 2=write byte, 3=reset, 4=wait core cycles (16-bit), 5=enable,
6=sample dedicated outputs. Status 0=success, 1=bad packet, 2=disabled/invalid byte,
3=unknown opcode, 4=host timeout. Invalid packets have no host side effects.
Truncated packets expire after twenty idle UART bit periods. No pipelining/retry
is supported. Wait specifies a minimum explicit delay; serial transfers also
consume time while the core runs continuously.

For silicon, implement the same transport contract in an external fixture that
drives the chip's host pins with its own synchronous timing and connects reset,
enable and shared clock. Keep `PIOHost`, scenario code and protocol drivers.
The current FPGA bridge instantiates the emulated core; it is **not** already a
silicon pin-driving fixture. `sample` reads FPGA core output nets and is not an
external electrical measurement.

## Physical implementation scope

Local validation on 2026-10-29 passed: six shared cases through package pins;
the same six through UART/adapter/real core; default-baud link checks; four
transport failure/fragmentation tests; five existing SPI checker tests; three
existing host API tests; and the complete original 39-test RTL regression.
The board wrapper also passes Icarus syntax/elaboration with vendor clock
primitives treated as black boxes. This does not validate the MMCM or XDC in
Vivado. Logs are retained under `test/sim_build/bringup-*.log`.

No files in `src/`, `info.yaml`, production timing tooling or GDS workflow were
changed. Thus no ASIC timing cone/register boundary changes or consumed ASIC
timing headroom are introduced. The qualified ASIC baseline is retained; a new
extracted ASIC timing run is not claimed. The added FPGA-only bridge still needs
its own Vivado implementation checks before board use.
