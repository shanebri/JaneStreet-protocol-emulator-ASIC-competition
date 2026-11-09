# Revision 0x21 on 8x4

This campaign closes the FPGA functional baseline before architecture additions.
It uses the qualified `20261101-v2-18` bridge image, the four-word FIFO design,
the Nano 33 IoT peer and a 3.3 V USB UART adapter. The checklist pins the image
hash and the current ASIC source hashes. Each run records its own source commit,
dirty state, firmware and harness hashes.

## Prepare

Upload the [Nano SPI sketch](../spi_hardware/nano33iot_spi_slave/nano33iot_spi_slave.ino)
with the Arduino SAMD Boards core and the Nano 33 IoT selected. Program the
preserved FPGA image through Vivado Hardware Manager and confirm LD7 is lit.
Use actual runtime serial ports below.

```powershell
py tools/bringup/prepare.py --list-ports
py tools/bringup/prepare.py --baseline --nano-board nano33iot --image .bringup/candidates/20261101-v2-18/arty_bringup_top.bit --bridge-port COM3 --nano-port COM4 --uart-peer-port COM5 --out .bringup/campaigns/baseline-0x21-8x4-001
```

The output contains ten fixtures, `campaign.json` and `RUNBOOK.md` with
commands for each test. Run the cases separately while changing wiring. Connect
signal grounds and power boards through their own USB cables. Pull-ups use 3.3 V.

| Case | Wiring and required result |
| --- | --- |
| `smoke` | Arty USB control only. Pass all six smoke cases on the selected image. |
| `boundaries` | Arty USB control only. Both engines fill RX/TX, reject overflow, drain in order, report underflow and recover from TX starvation. |
| `recovery` | Disconnect active peers and loopbacks. Check disable retention, partial write/read handling, reset with live queues, IMEM retention, restart and abort release. |
| `stress` | JA1 → JC3 and JB2 → JC4 marker loopbacks. Confirm these in the fixture. Run at least 1000 rounds and 600 seconds with captures. Both markers must progress during host access, and all tagged FIFO words must return in order. |
| `pads` | Remove output loopbacks and active peers. Connect known pull-ups on JC1..JC4 and confirm the actual values/supply in the fixture. Capture all four pads under both owners and reset release. |
| `uart` | Arty JA1 → adapter RX. Check all byte values 00..FF at 115200 baud. |
| `uart_rx` | Adapter TX → Arty JA4. Disconnect Nano MISO from JA4 and set `uart_rx.wiring_confirmed`. Check 00..FF on both engines, exact ISR byte alignment, HALT, empty queues and clear FIFO errors. |
| `spi` | Arty JA1 → Nano D11, JA2 → D13, JA3 → **D8**, JA4 ← D12, JA7 ← D2. Check all 256 transfers at both ends and `DONE 256 0`. |
| `concurrent` | SPI wiring plus JB1 → adapter RX. Add JA1 → JC1, JA3 → JC2, JB1 → JC3 and JA2 → JC4 capture loopbacks, then confirm them. Check all 256 SPI transfers and 1024 UART bytes, capturing rounds 85 and 170 with host traffic during overlap. |
| `i2c100` | Upload the I2C target sketch. JC1 → Nano A4/SDA, JC2 → Nano A5/SCL with verified pull-ups and shared ground. Check the fixed `PIO` response at `0x50`, the `0x51` address NACK and the idle bus after both transactions at 100 kHz. |

The UART RX firmware samples 16 state-machine ticks per bit. At the 50 MHz core
clock and requested 115200 baud, divider 27 gives a nominal 115741 baud sampling
schedule. The adapter transmits at 115200 independently. Every byte is sent only
after the selected engine reports that it is running and waiting for the start.
The finite program HALTs after each received byte.

The Nano 33 BLE is also supported with `--nano-board nano33ble`; its SPI chip
select is D10. The I2C target fixture uses the Nano 33 IoT sketch. Use its board
selection and restore the SPI sketch before returning to SPI/concurrent tests.

## Analyze each run

Keep failed attempts. If retrying a case, choose a fresh run directory and edit
that case's `run` and `analysis` paths in `campaign.json` to select the new
attempt for review.

The generated run paths use `CAMPAIGN/runs/CASE`. Analyze captures into the
matching `CAMPAIGN/analysis/CASE` directory. For example,

```powershell
py tools/bringup/analyze.py --run CAMPAIGN/runs/stress --out CAMPAIGN/analysis/stress --require-physical-waveforms
py tools/bringup/analyze.py --run CAMPAIGN/runs/pads --out CAMPAIGN/analysis/pads --require-physical-waveforms
py tools/bringup/analyze.py --run CAMPAIGN/runs/concurrent --out CAMPAIGN/analysis/concurrent --require-physical-waveforms
```

The I2C freeze gate uses the scored 100 kHz functional results and raw host
traffic. Physical waveform framing, rise-time measurements and the 400 kHz
board test are separate qualifications. Their fixtures and acquisition guidance
remain available in the [I2C waveform guide](../../docs/i2c.md#verify-the-waveform-and-rise-time).

## Check readiness

Run the software regressions with the existing Python/cocotb/Icarus environment.
Keep the complete extended run directory printed by the simulator.

```powershell
py -m unittest discover -s tools/bringup -p 'test_*.py' -v
py test/run.py
py tools/bringup/simulate.py
py tools/bringup/simulate.py --default-baud-link
py tools/bringup/simulate.py --extended
py tools/bringup/baseline.py --campaign CAMPAIGN --rtl-results test/results.xml --bridge-run PATH_TO_COMPLETE_EXTENDED_RUN --out CAMPAIGN/report-001
```

The report lists every outstanding case and exits 2 while evidence is missing.
It returns `READY_FOR_FREEZE` and exits 0 only when the complete 39-case RTL and
seven-case bridge regressions pass and all ten board cases have matching
evidence. It checks immutable run indexes, raw host traffic, source/image
identity, UART RX coverage on both engines, stress duration, both concurrent
capture rounds and all pad-owner captures. Simulation records retain their
simulation classification.

Review the report, commit the reviewed source, and preserve the source snapshot,
FPGA image, ASIC qualification receipt and all run/analysis bundles with hashes
outside the checkout when freezing the baseline. Record the measured rates and
fixture in the release notes.
