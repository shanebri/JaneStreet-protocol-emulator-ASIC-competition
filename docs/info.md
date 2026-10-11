## How it works

V0 is a small programmable output engine targeting **8×4 Tiny Tapeout tiles** on
IHP CMOS5L. A synchronous 8-bit host bus loads 16-bit instructions into 32 words of
instruction memory. A 5-bit PC, decoder, 16-bit accumulator and ALU execute them.
There are eight 16-bit scratch words, seven GPIO outputs and an 8N1 UART transmitter.
The target clock is 50 MHz (20 ns); final area and timing require physical validation.

Most instructions execute in one clock. WAIT inserts a specified number of extra
clocks; WAIT_TX and a store to busy UART_DATA stall execution until the transmitter
is ready. UART timing runs independently of instruction execution, including after
HALT. This V0 deliberately uses small inferred memories and simple control logic.

### Pins

| Pins | Function |
| --- | --- |
| `ui[3:0]` | Host byte-register address |
| `ui[4]` | Host write strobe WR, active high |
| `ui[5]` | Host read strobe RD, active high |
| `ui[7:6]` | Reserved; drive zero |
| `uio[7:0]` | Bidirectional host data bus |
| `uo[0]` | UART TX, idle high |
| `uo[7:1]` | GPIO[6:0], reset low |
| `clk` | Shared host/core clock |
| `rst_n` | Active-low synchronous reset |
| `ena` | Enable; hold high during normal operation |

### Host bus timing

All host signals are synchronous to `clk`; there is no asynchronous clock-domain
crossing, acknowledge signal or variable bus latency.

1. Begin with RD and WR low for at least one rising clock edge.
2. To write, drive address and data before a rising edge with WR high and RD low.
   The write is accepted on that edge.
3. To read, release the host's data drivers and drive address with RD high and WR
   low before a rising edge. Read data is latched on that edge and can be sampled
   after propagation settles, for example on the following falling edge.
4. Lower the strobe for at least one rising edge before the next transaction.

A strobe held high causes exactly one transaction. Read data stays latched until
the next accepted read. The chip drives all eight data pins only while RD is high,
WR is low, reset is inactive and `ena` is high. Lower RD before the host drives a
write. Simultaneous RD and WR are ignored and release the data bus; lower both
before retrying. Address/data must meet normal setup and hold times.

Host register addresses are **byte registers**. Instruction and CPU data addresses
are **16-bit word addresses** in separate spaces. Multi-byte host writes stage the
low byte, then commit the whole word on the high-byte write. Multi-byte reads are
independent byte snapshots: stop the CPU before reading a coherent PC/accumulator
or scratch value that software may otherwise change.

### Host register map

| Address | Register | Read | Write |
| --- | --- | --- | --- |
| `0x0` | CONTROL | Zero | Bit 0 START; bit 1 STOP; STOP wins if both set |
| `0x1` | STATUS | Bit 0 running, bit 1 UART busy, bit 2 fault, bit 3 waiting | Ignored |
| `0x2` | IMEM_ADDR | Current 5-bit program pointer | Set pointer from bits [4:0] |
| `0x3` | IMEM_LO | Selected instruction [7:0] | Stage instruction low byte while stopped |
| `0x4` | IMEM_HI | Selected instruction [15:8] | Commit staged low + this high byte; increment pointer modulo 32, while stopped |
| `0x5` | DATA_ADDR | Current 8-bit data-map pointer | Select a mapped word |
| `0x6` | DATA_LO | Selected data word [7:0] | Stage data low byte while stopped |
| `0x7` | DATA_HI | Selected data word [15:8] | Commit staged low + this high byte while stopped; pointer does not increment |
| `0x8` | PC | Current instruction address, zero extended | Ignored |
| `0x9` | ACC_LO | Accumulator [7:0] | Ignored |
| `0xA` | ACC_HI | Accumulator [15:8] | Ignored |
| `0xB–0xF` | Reserved | Zero | Ignored |

Reads never increment pointers. Pointer writes and reads are allowed while running;
instruction/data writes, including low-byte staging, are ignored while running.
A host write to busy UART_DATA while stopped is ignored, so poll STATUS bit 1 before
sending directly from the host. The host data pointer reaches the first 256 words;
all currently implemented data registers are within that range.

START restarts at PC=0, clears the accumulator, waits and fault, sets running and
cancels any UART frame. STOP clears running/waits and cancels UART, retaining the
PC, accumulator and fault for inspection. Both preserve GPIO, scratch memory, UART
data/divider and program contents. Writing zero to CONTROL has no effect.

### CPU data and peripheral map

| Word address | Register | Width and behavior |
| --- | --- | --- |
| `0x000–0x007` | SCRATCH[0:7] | Eight read/write 16-bit words, reset to zero |
| `0x010` | GPIO_OUT | Read/write low seven bits, zero extended on read; reset zero |
| `0x011` | UART_DATA | Write low eight bits to start a frame; read last accepted byte; reset zero |
| `0x012` | UART_DIV | Read/write 16-bit clocks per bit; reset 434; zero coerced to one |
| `0x013` | UART_STATUS | Read-only bit 0 busy; other bits zero |
| Other addresses | Unmapped | Reads return zero; writes ignored |

The CPU uses these same addresses in LD/ST instructions. A CPU store to UART_DATA
holds its PC and accumulator while busy and sends exactly once when available.
Writes to the divider do not affect a frame already in progress: the transmitter
captures the divider at frame launch. There is no receive path or FIFO.

### Instruction set

Each instruction is `{opcode[3:0], immediate[11:0]}`. `A` denotes the 16-bit
accumulator. Immediates are unsigned and zero extended. Arithmetic wraps modulo
65536. Branches test A directly; there is no separate flags register.

| Opcode | Mnemonic | Effect |
| --- | --- | --- |
| `0x0` | NOP | Advance PC |
| `0x1` | LDI imm | A = zero-extended imm |
| `0x2` | LD addr | A = mapped 16-bit word |
| `0x3` | ST addr | Mapped word = A; UART stores can stall |
| `0x4` | ADDI imm | A = A + imm |
| `0x5` | SUBI imm | A = A - imm |
| `0x6` | ANDI imm | A = A AND imm |
| `0x7` | XORI imm | A = A XOR imm |
| `0x8` | JMP addr | PC = addr |
| `0x9` | JZ addr | Branch if A == 0 |
| `0xA` | JNZ addr | Branch if A != 0 |
| `0xB` | WAIT n | Advance PC, then wait n extra clocks (0–4095) |
| `0xC` | WAIT_TX | Stall until UART is idle, then advance PC |
| `0xD` | HALT | Clear running; hold PC and outputs; UART finishes its frame |
| `0xE` | SHL | A = A << 1, zero fill; immediate ignored |
| `0xF` | Reserved | Halt with fault; retain offending PC |

All branch targets must be 0–31. An out-of-range target faults even for an untaken
conditional branch. Sequential execution wraps from word 31 to word 0. NOP,
WAIT_TX and HALT ignore their immediate fields. To load a full 16-bit constant,
initialize a scratch word through the host then use LD, or build it with ALU operations.

If WAIT n executes at edge t, the next instruction executes at edge t+n+1.
WAIT 0 therefore has ordinary one-cycle instruction latency. STATUS.waiting is
set while the wait counter is nonzero or execution is stalled by the UART.

### UART waveform and reset

UART TX sends one low start bit, eight data bits least-significant bit first and
one high stop bit. Every bit, including stop, lasts exactly UART_DIV enabled
clock edges. Busy clears after the full stop bit. Baud is `clock_hz / UART_DIV`.
At 50 MHz with divider 434 the rate is about 115207 baud, close to 115200.

For ASCII `U` (`0x55`) the ten frame bits are:

```text
            start  d0 d1 d2 d3 d4 d5 d6 d7  stop
TX level:     0     1  0  1  0  1  0  1  0    1
clocks/bit:  434   434 for each data bit       434
```

Reset stops execution, clears PC/A/scratch/GPIO and host staging/pointers, restores
divider 434, clears UART data/busy and returns TX high. Instruction memory is not
reset and is undefined at power-up: load every reachable instruction before START.
`ena=0` pauses the CPU, waits and UART counters and disables the host interface.
It may stretch a UART bit, so hold `ena=1` throughout a frame. Strobed transactions
while disabled are discarded; return strobes low before resuming.

## How to test

### Load and run the supplied UART program

Use `examples/uart_v0.hex`, one 16-bit hexadecimal instruction per line:

```text
11B2 3012 1055 3000 2000 3011 C000 1001 3010 B010 D000
```

1. Apply clock and synchronous reset, with RD=WR=0 and `ena=1`.
2. Write `0x00` to IMEM_ADDR (`0x2`).
3. For each instruction write its low byte to `0x3`, then its high byte to `0x4`.
   The program pointer auto-increments after each high-byte commit. For example,
   `11B2` is written as `B2` to `0x3`, then `11` to `0x4`.
4. Optionally read each word back by setting IMEM_ADDR and reading `0x3`/`0x4`.
5. Write `0x01` to CONTROL (`0x0`). Observe one `U` frame on `uo[0]` and then
   GPIO[0] high on `uo[1]`. After the final wait, STATUS.running and busy are zero.
6. Write `0x01` again to replay, or `0x02` to abort.

For a host data write, set DATA_ADDR, stage DATA_LO and commit DATA_HI. Example:
write `0x12` to `0x5`, `0xB2` to `0x6`, then `0x01` to `0x7` to set divider 434
while the CPU is stopped. All accesses still use the low/high strobe timing above.

The cocotb regression performs this entire flow through the external pins and
checks every transmitted bit at clock resolution. Run `python test/run.py` from
the repository root, or `make -C test`, after installing Icarus and the Python
packages in `test/requirements.txt`. Waveforms are saved to `test/tb.fst`.

## External hardware

A host that shares the clock and can drive a synchronous 8-bit bidirectional bus,
plus a logic analyzer or oscilloscope, is sufficient. A UART adapter can receive
TX at 115200 baud, 8 data bits, no parity and one stop bit with the example's
50 MHz clock. Use logic levels compatible with the chip or FPGA board and a
common ground. UART RX is not implemented.
