# Revision 0x21 FPGA functional baseline

The November 8, 2026 campaign passed all ten hardware cases for the dual-engine,
four-word FIFO design on the 8x4 allocation. It used the Arty A7-100T, Nano 33 IoT
and 3.3 V USB UART adapter with the qualified `20261101-v2-18` bridge image.
The [implementation receipt](fpga_bringup_v2_20261101_receipt.json) identifies
the FPGA build and timing evidence. The [freeze receipt](fpga_baseline_0x21_20261108_receipt.json)
records the exact image, ASIC inputs and evidence hashes.

| Hardware case | Passing evidence |
| --- | --- |
| Smoke | All six scenarios, including both engine banks and instruction memory |
| FIFO boundaries | Both engines passed overflow, underflow, drain order and refill after starvation |
| Recovery | Disable retention, partial transactions, reset, restart and pad release, with two digital captures |
| Dual-engine stress | 1,042 ordered words per engine over 600.235 seconds. A physical loopback capture showed both markers running during host access |
| Pad ownership and release | All four pads under both owners with 4.7 kΩ pull-ups to 3.3 V, plus reset release. All nine captures passed |
| UART transmit | All 256 byte values at 115200 baud |
| UART receive | All 256 byte values on each engine at 115200 baud, with correct alignment and clean FIFO state |
| SPI | All 256 transfers verified at both ends. The Nano reported `DONE 256 0` |
| Concurrent SPI/UART | 256 SPI transfers and 1,024 UART bytes. Captures at indices 85 and 170 each showed 21.627 ms of overlap with host access |
| I2C at 100 kHz | The Nano at `0x50` returned `50 49 4f` (`PIO`). Address `0x51` returned NACK. Both transactions returned the bus to idle |

The I2C entry is functional only. The logic analyzer verified the NACK frame.
In the 24 MS/s read trace, two SDA/SCL falling edges share a sample, so the
strict decoder could not establish their order. Rise times were unmeasured and
physical 400 kHz operation was untested. Those checks are outside the functional
freeze gate. See the [I2C guide](i2c.md#verify-the-waveform-and-rise-time) for
separate bus qualification.

The freeze gate also passed the complete 39-case RTL and seven-case extended
bridge regressions. The ASIC implementation and timing qualification remain as
documented in the [project status](project_status.md). Recreate the board
fixtures and verify the evidence with the [baseline checklist](../tools/bringup/BASELINE.md).

The private evidence archive retains the bitstream, source snapshots, hardware
run bundles and analyses, native I2C captures and simulator results. Its SHA-256
is in the freeze receipt. Raw files stay outside version control.
