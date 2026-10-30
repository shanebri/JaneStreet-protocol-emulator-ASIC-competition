# Eight-bit SPI mode-0 master

[spi_mode0.asm](../examples/spi_mode0.asm) implements one full-duplex byte using
the existing PIO V0 ISA. It consumes one TX FIFO word, asserts active-low chip
select, generates eight clock pulses, deasserts chip select, pushes one RX word,
and halts. No RTL, UART bridge, FPGA wrapper or Vivado configuration is required
for the simulation. For board wiring and physical SPI validation, use the
[Arty + Nano 33 BLE hardware test guide](../tools/spi_hardware/README.md).
The [memory architecture guide](memory_architecture.md) explains how instruction
storage, FIFOs and shift registers support this program.

Mode 0 means SCLK idles low (CPOL=0) and data is sampled on rising edges (CPHA=0).
The first MOSI bit is established before the first rising edge; subsequent bits
are established during low phases. Both directions are MSB-first.

## Pin and host setup

These are **core logical pins**, not Arty package pins or PMOD assignments.

| Signal | Default core pin | PIO mechanism |
| --- | --- | --- |
| MOSI | `uo[0]` | OUT base 0, width 1 |
| SCLK | `uo[1]` | Optional side-set output 1 |
| CS_n | `uo[2]` | SET base 2, width 1 |
| MISO | `ui[6]` (input 0) | IN base 0, two-flop synchronized |

While stopped, configure the following through the [32-bit host data
map](info.md#32-bit-data-map). Write words little-endian to byte registers
`6, 7, 9, A` after selecting DATA_ADDR at register `5`.

| Selector | Register | Value | Purpose |
| --- | --- | --- | --- |
| `0x04` | PINS | `0x00000004` | CS_n high, SCLK and MOSI low |
| `0x10` | SHIFTCTRL | `0x00000000` | Shift both OSR and ISR left; disable automatic FIFO transfers |
| `0x11` | EXECCTRL | `0x000083E0` | Side-set enabled, entry 0, wrap 0–31 |
| `0x12` | PINCTRL | `0x00020A08` | Map OUT, SET, side-set and IN as above |
| `0x13` | DIVIDER | `4` | Example clock rate; one SM tick per four core clocks |

Load the ten words in [spi_mode0.hex](../examples/spi_mode0.hex) at instruction
address 0. Queue the transmit byte **in TX word bits [31:24]**, with the remaining
bits zero: for example, byte `0x96` is word `0x96000000` (host bytes `00 00 00 96`).
The left-shifting OSR emits bit 31 first. Write CONTROL=1 to START.

After the engine stops, check that no fault/error occurred, then read one RX word
using DATA_ADDR=`0x09` and host bytes `6,7,9,A`. The result is zero-extended in
**bits [7:0]**; for example MISO byte `0x3D` returns word `0x0000003D`. Left IN
shifts earlier received bits toward the MSB of the accumulated byte.

For another independent byte transaction, drain RX, enqueue another TX word and
START again. The program raises CS_n between transactions. It does not implement
a multibyte transfer under continuous chip select. Initialize PINS explicitly:
the core's reset output value `0x01` is not the default SPI idle pattern.

## Timing and synchronization

Let `D` be DIVIDER and `f_core` the input clock rate. SCLK's period is `16D` core
clocks, so `f_SCLK = f_core / (16D)`. At 50 MHz and D=4 this is 781.25 kHz.
Each complete high and inter-bit low phase lasts eight SM ticks (50% duty cycle).

| Event | Timing |
| --- | --- |
| CS_n assertion to first rising edge | 8 SM ticks |
| MOSI update to its rising edge | 4 SM ticks |
| Rising edge to falling edge | 8 SM ticks |
| Falling edge to next rising edge | 8 SM ticks |
| Eighth falling edge to CS_n release | 4 SM ticks |

`out pins, 1 side 0 [3]` places MOSI while low and waits four ticks. `in pins, 1
side 1 [7]` raises SCLK and shifts one synchronized MISO bit into ISR, then waits
eight ticks. `jmp x--, bitloop side 0 [3]` lowers SCLK and spends four ticks in the
low phase; the next OUT spends the other four. X starts at seven, yielding eight
iterations because decrement tests the old value before branching.

The IN instruction consumes the **already synchronized** input on the same core
edge that raises SCLK. It does not capture the physical MISO pad at that instant.
The slave must present its first bit before the first rising edge and subsequent
bits after falling edges, allowing propagation plus the two synchronization
stages and clock-phase uncertainty to settle before IN. The conservative
eight-tick half-period leaves room for this. Select a slower divider when required
by the slave or board; simulation cannot establish a hardware maximum SPI rate.

An empty TX FIFO blocks before CS assertion with SCLK low. RX FIFO backpressure
blocks after CS release, also with SCLK low. STOP or `ena=0` during a transaction
stretches it; reset changes output levels. Do not use those controls as a normal
SPI transfer-completion mechanism.

Pin assignments can change without reassembling: for MOSI output `m`, clock
output `s`, CS output `c`, and MISO input `i` (0 or 1), use
`PINCTRL = m | (1 << 3) | (c << 8) | (1 << 11) | (i << 16) | (s << 17)`.
Choose distinct output pins and initialize PINS with CS high and SCLK low.

## Verification

`firmware_spi_mode0_byte_transfer` in [test/test.py](../test/test.py) assembles and
compares the checked-in hex, loads it through the host bus, and models a slave
using only external core pins. It tests seven TX/RX pairs at dividers 1, 2 and 5,
on two pin layouts (42 transfers). The alternate layout uses MOSI=5, SCLK=7,
CS_n=3 and input1. The unused input carries inverse data to catch wrong mappings.

The slave changes MISO one core clock after selection/falling edges. Assertions
check exactly eight rising and falling edges, mode-0 idle, MSB-first MOSI, MOSI
setup/stability, both clock phase widths, chip-select timing, unchanged unrelated
outputs, waiting safely for TX, and exactly one correctly aligned RX word.

```powershell
$env:COCOTB_TEST_FILTER = 'firmware_spi_mode0_byte_transfer$'
./test/run.ps1
Remove-Item Env:COCOTB_TEST_FILTER
```

Run the complete suite with `python test/run.py` or `./test/run.ps1`.

Host revision 0x21 transfers each byte low nibble then high nibble on uio[3:0].
See [the transport contract](pio21_contract.md) for framing, reset and resynchronization.

## Repeatable hardware profile

The [Python bring-up suite](../tools/bringup/README.md) loads this firmware through
the programmable FPGA host bridge and runs the existing 256-byte Nano peer
checker without buttons. It is separate from the fixed `arty_spi_test_top` image.
The profile checks both endpoints' payloads and completion; it does not acquire
waveforms or establish electrical timing. Physical execution of that new profile
has not been recorded here. ASIC qualification is in [project status](project_status.md).
