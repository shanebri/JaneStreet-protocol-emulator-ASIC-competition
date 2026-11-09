# Firmware I2C on PIO revision 0x21

The controller supports one controller, seven-bit addresses, Standard-mode and
Fast-mode, with target clock stretching. Framing runs entirely in
[i2c.asm](../examples/i2c.asm): **24/32 instructions**, unchanged four-word FIFOs.
It does not implement arbitration, target mode, ten-bit addresses, SMBus, Fm+,
high-speed mode, Ethernet or USB. The two synchronized dedicated inputs and all
four bidirectional pads remain general PIO resources.

Use [the architecture contract](pio21_contract.md) for the single physical/logical
pin correspondence table and [the datasheet](info.md) for host registers.
Default SDA is pad0 (`uio[4]`, output8/input2), SCL pad1 (`uio[5]`, output9/input3).
`I2C.configure(sda=2, scl=3)` uses `uio[6:7]`; arbitrary distinct pad pairs work.
The driver rewrites the three absolute SCL WAIT operands when remapping. IN base
selects SDA; SET/OUT affect only SDA; side-set affects only SCL. Both directions
are armed with output values one and open-drain enabled. Unused values, direction
and electrical mode are preserved by normal configuration and transactions.

## Software interface and service policy

[i2c_driver.py](../tools/i2c_driver.py) provides an asynchronous byte-transport
protocol: `read(register)` and `write(register, byte)`. An implementation must
complete the low/high nibble handshake described in the datasheet, preserve the
upper input bits, and bound its own I/O calls. It must serialize accesses to the
shared DATA_ADDR/staging/snapshot registers. `test.Host` is an executable pin-level
implementation. `fpga/byte_nibble_host.sv` provides the FPGA equivalent.

```python
from i2c_driver import I2C

bus = I2C(transport, timeout=0.25)
await bus.configure(400_000)       # requires VERSION == 0x21
result = await bus.transfer(0x48, write=b"\x00", read=2)
assert result.status == "success"
temperature_register = int.from_bytes(result.data, "big")
```

This writes a sensor register pointer, issues repeated START, reads two bytes,
ACKs the first and NACKs the last, then issues STOP. `completed` counts acknowledged
write payload bytes plus received read payload bytes, excluding addresses. Status
is `success`, `address_nack`, `data_nack`, `bus_busy`, `timeout`, or (for recovery)
`bus_clear_failed`. NACK ends the transaction with STOP. Invalid arguments raise
ValueError; a firmware fault raises RuntimeError. No reserved-address policy is
imposed beyond the seven-bit range; use addresses appropriate to the target.

One transfer has a monotonic 250 ms default deadline, adjustable for long messages
or slower transport. The budget includes host service and stretching, not just
wire time. Polling FIFO/IRQ advances the synchronous transport; no host response
is required on individual wire edges. TX starvation at the dispatcher and RX
backpressure at PUSH preserve the preceding SCL-low state and SDA value. After
STOP, dispatcher starvation preserves idle high. The dispatcher has no side-set,
so it cannot accidentally pull SCL down while waiting after STOP.

The production driver services one complete byte at a time to stop promptly on
NACK. Transfers are not limited to four words: each byte command is enqueued and
its response drained before the next. The streaming acceptance test additionally
queues eight commands, fills RX, and feeds/drains twenty bytes with deliberate
service gaps. Applications can pipeline independent read commands after the read
address is acknowledged; never prequeue writes past an ACK decision unless the
application explicitly accepts continuing after NACK.

Timeout sends CONTROL.ABORT_RELEASE, which remains accessible during every WAIT
or FIFO stall. It releases directions without clearing queues or values. Call
`configure` again to stop/clear stale commands and explicitly re-arm; START or
RESUME alone does not re-arm. Transport-level timeouts must also be bounded by
the concrete transport. STOP, HALT, fault and enable-low retain pad state and can
hold a bus low; use ABORT_RELEASE for release.

## FIFO ABI and configuration

Each TX word starts with a five-bit program address in bits[4:0]. Dispatch is
PULL then OUT PC,5. Valid commands:

| Address | Command | Remaining word | Response |
| --- | --- | --- | --- |
| 2 | Clock 1..9 bits | [8:5] count minus one (0..8); [17:9] wire bits in chronological LSB-first order; upper bits zero | One RX word: sampled bits in chronological MSB-first order, right aligned |
| 9 | START / repeated START | zero | none |
| 14 | Hold SCL low (recovery preparation) | zero | none |
| 16 | STOP | zero | IRQ0 after STOP hold delay |

Other command addresses are invalid ABI even though OUT PC can branch there.
BITS requires SCL already low, established by START, a preceding byte, or LOW.
LOW executes the existing three-tick low hold and returns to the dispatcher.
Address/data writes send eight MSB-first bits followed by a released ninth bit.
Their response bit0 is target ACK (0) / NACK (1). Reads send eight released bits
and a controller ACK=0 or final NACK=1; response[8:1] is the received byte. PUSH
clears ISR, preventing contamination between responses. Bits are packed by
`write_command`, `read_command`, and `bits_command`; the host never writes live
waveform registers. Command length above nine is rejected by the Python encoder.

SHIFTCTRL=1 (OUT right, IN left, no automatic transfers), EXECCTRL=0xD7E0
(entry21, optional side-set, wrap0..31). Entry waits for actual SCL/SDA high before
dispatch. ROUTE selects the configurable pads with widths one; directions and
OD bits for both pads are one; FILTER enables both pad qualifiers. DIVIDER is 24
for nominal 100 kHz, 6 for nominal 400 kHz, or 240 for diagnostic 10 kHz. Checked-in
hex is regenerated with `python tools/pioasm.py examples/i2c.asm`; configuration
constants live in `tools/i2c_driver.py` and `examples/i2c.json`.

## Timing derivation

Reference: NXP [UM10204 revision 7.0, Table 11 and section 3.1.16](https://www.nxp.com/docs/en/user-guide/UM10204.pdf).
The digital checks use these minimums in ns:

| Mode | SCL low | SCL high | START hold | Repeated START setup | STOP setup | Bus free | Data setup |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Standard | 4700 | 4000 | 4000 | 4700 | 4000 | 4700 | 250 |
| Fast | 1300 | 600 | 600 | 600 | 600 | 1300 | 100 |

Let T=20 ns × DIVIDER. Each continuing bit has 11T commanded low: the preceding
JMP side0 holds three ticks, OUT updates SDA and holds eight ticks. WAIT side1
releases SCL and retries until synchronized, qualified SCL is high. Its eight-tick
delay begins only on success; IN samples SDA one tick before the following fall.
Thus high is at least 9T plus observation time; a stretch lengthens low without
shortening high. The minimum 11T low exceeds filter latency, so WAIT cannot
consume stale high from the preceding pulse. SDA changes 3T after falling SCL
within a byte (1.44 us / 360 ns), before the next release. At command boundaries,
intentional extended-low service waits can delay data availability further.

START's two high waits provide setup, followed by nine ticks of START hold before
SCL falls. STOP holds SDA low for eight ticks after qualified SCL high, then
releases SDA and waits eight ticks before IRQ. Entry/START sequencing supplies
bus-free time before another START. Rise delays and synchronized observation
reduce achieved clock rate; nominal rates are upper targets, not exact fixed
frequencies. At zero stretch the instruction schedule is at least 21T per bit:
99.21 kHz / 396.83 kHz upper bounds, before rise and extra sampling retries.

Both I2C inputs enable four-sample qualification after two synchronization stages.
At 50 MHz this rejects ideal digital spikes up to 50 ns. Filtered state appears
after 5–6 clock periods; instructions consume the previous registered value.
This digital model does not establish metastability probability, thresholds,
hysteresis, analog spike rejection, pull-up sizing or physical rise/fall limits.
The test target uses independent open-drain drivers, pull-ups and delayed rises.
No simulation result is a claim of electrical compliance or timing closure.

## Recovery

`bus_clear()` bypasses entry's idle check using stopped-state ENTRY=0, first sends
LOW to establish a complete first low phase, sends at most nine clocks with SDA
released, then STOP, and checks both actual inputs high.
SDA remaining low reports failure and releases all protocol directions. Permanent
SCL-low reaches the deadline and releases; further recovery requires target reset
or power cycling as applicable to the hardware. Configure before bus clear after
an abort to explicitly re-arm. No unbounded retry loop or automatic recovery is
hidden in ordinary transactions. Reset immediately gates off bidirectional OEs;
reset mid-byte requires target recovery and a fresh configuration.

## FPGA wiring and limits

[arty_i2c_bridge.sv](../fpga/arty_i2c_bridge.sv) exposes real top-level tri-state
protocol pads with readback and the reusable byte adapter. Integrate its byte
requester and a 50 MHz clock; this is a simulation-verified bridge, not a complete
USB host bridge or a programmed board demonstration.

The [constraint fragment](../fpga/arty_i2c_pads.xdc) maps pad0..3 to JA1..4
(G13, B11, A11, D12), verified against Digilent's official
[Arty A7-100 Rev D/E master constraints](https://github.com/Digilent/digilent-xdc/blob/master/Arty-A7-100-Master.xdc).
Proposed default wiring is JA1 SDA, JA2 SCL, common ground, with external pull-ups
to 3.3 V chosen for measured capacitance/rise time. JA3/4 remain available.
Use voltage-compatible targets. The fragment does not constrain the requester
ports or clock of a larger design; do not treat it as a complete board top.

For a complete programmable control path, the separate
[bring-up suite](../tools/bringup/README.md) supplies `arty_bringup_top` and a
Python I2C profile using this driver. Its pads are **JC1/2/3/4**, not the JA
mapping of the reusable wrapper above. Configure a target's address, write data
and known expected response in the fixture file. This basic hardware profile
does not reproduce all simulation fault-injection tests. The bridge is
simulation-tested. The [functional baseline](fpga_baseline_0x21_20261108.md)
records the physical 100 kHz response, unused-address NACK and return to idle.

### Nano 33 IoT board test

Use the preserved `20261101-v2-18` image and the Arty's onboard USB control port.
Upload the [I2C target sketch](../tools/bringup/nano33iot_i2c_target/nano33iot_i2c_target.ino)
with the Arduino SAMD Boards core and the **Arduino Nano 33 IoT** board selected.
This replaces the SPI sketch on that Nano until you upload the SPI sketch again.

Disconnect the other protocol fixtures. Wire **Arty JC1 → Nano A4/SDA**,
**Arty JC2 → Nano A5/SCL**, and share ground. Verify SDA and SCL each have a
pull-up to 3.3 V. Power the boards through their own USB cables. The PC uses the
Arty COM port for this test.
[Arduino Nano 33 IoT pinout](https://docs.arduino.cc/resources/pinouts/ABX00027-full-pinout.pdf)

Program the v2 image with Vivado Hardware Manager. From the repository root,
substitute the actual Arty COM port and use fresh output directories.

```powershell
py tools/bringup/prepare.py --list-ports
py tools/bringup/prepare.py --i2c-only --image .bringup/candidates/20261101-v2-18/arty_bringup_top.bit --bridge-port COM3 --out .bringup/campaigns/i2c-001
py tools/bringup/run.py --fixture .bringup/campaigns/i2c-001/i2c.json --suite i2c --out .bringup/runs/i2c-001
```

At 100 kHz, the fixture writes `00` to `0x50`, issues a repeated START, and reads
`50 49 4F` (`PIO`). The Nano returns fixed bytes; it does not use the written
value to select its response. The runner then probes `0x51` and requires
`address_nack`, zero completed bytes and both lines high after STOP. Keep
`0x51` unused on this bus. For a different target, set its address, write data,
and expected response, and choose a known unused address for `nack_address`.
Older fixtures may omit that field for a positive-only run.

### Verify the waveform and rise time

This section covers physical bus qualification separately from the 100 kHz
functional freeze gate. The 400 kHz board profile can be selected by setting
`i2c.rate` to `400000` in a separate fixture after verifying the rise-time limit.

Use an external logic analyzer or scope with enough memory for the entire
transaction, including pauses while the host services the FIFOs. Export digital
0/1 SDA and SCL samples at 10 MS/s or higher. Keep idle before START and after
STOP. If the instrument captured both cases, export each as a separate CSV.
Use case 0 for the write/repeated-START/read and case 1 for the wrong address.
The analyzer checks the actual address, direction, bytes, ACKs, repeated
START, final read NACK, STOP and idle against the saved fixture.

Use a separate oscilloscope export for rise time. Capture several representative
open-drain releases on both SDA and SCL with the same wiring and pull-ups.
Export voltage samples as `time_s,sda_v,scl_v` and measure the bus pull-up
voltage for `rise_supply_v`. Use a sample interval of 30 ns or shorter so the
export can also resolve the Fast-mode limit. The analyzer interpolates the
30% and 70% crossings and reports the longest observed rise on each line.
Standard-mode's maximum is 1000 ns and Fast-mode's maximum is 300 ns. Check
against 300 ns before trying 400 kHz, then repeat the measurement at 400 kHz.
[NXP UM10204, Table 11](https://www.nxp.com/docs/en/user-guide/UM10204.pdf)

Save a mapping JSON with the exact image hash from the run's `manifest.json`,
your instrument details, and the actual CSV column names.

```json
{
  "instrument": "instrument model, sample rate and threshold",
  "image_sha256": "COPY FROM THE RUN MANIFEST",
  "time_column": "Time [s]",
  "time_unit": "s",
  "channels": {"sda": "D0", "scl": "D1"},
  "rise_supply_v": 3.3
}
```

```powershell
py tools/bringup/analyze.py --run .bringup/runs/i2c-001 --out .bringup/analysis/i2c-read-001 --import-csv read.csv --mapping i2c-map.json --case 0 --rise-csv scope.csv --require-physical-waveforms
py tools/bringup/analyze.py --run .bringup/runs/i2c-001 --out .bringup/analysis/i2c-nack-001 --import-csv nack.csv --mapping i2c-map.json --case 1 --require-physical-waveforms
```

Omit `--rise-csv` for digital-only evidence. The report then marks rise time
as `NOT_MEASURED`. The run and analysis bundles keep the raw serial traffic,
capture CSVs, and decoded results for comparison.
