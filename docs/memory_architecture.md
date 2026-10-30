# Memory in the PIO engine: current storage and an SRAM path

## What exists now

The [dual-PIO extension](dual_pio.md) uses independent program memories and TX/RX
queues. There is no fetch or FIFO port arbitration between engines. Host access
is selected and serialized, with separate staging and read snapshots per engine.

Each of the two engines currently has small, separate storage structures. It does **not** have
a general-purpose RAM address space, stack, cache, or LOAD/STORE instructions.

| Storage | Organization | Capacity | Access |
| --- | --- | --- | --- |
| Instruction memory | 32 x 16 bits | 64 bytes | Host writes while stopped; PC fetches instructions |
| TX FIFO | 4 x 32 bits | 16 bytes | Host writes; PULL/autopull consume |
| RX FIFO | 4 x 32 bits | 16 bytes | PUSH/autopush produce; host reads consume |
| X, Y, OSR, ISR | Four 32-bit registers | 16 bytes | Instruction datapath and host debug access |

Per engine that is **96 bytes of instruction/FIFO storage**, plus **16 bytes of main
data registers**; two engines provide 192 bytes and 32 bytes respectively. PC, shift counters, configuration, FIFO pointers, IRQ flags, host
staging/snapshot registers and other control state are additional storage.

`instruction_fetch.sv` declares `reg [15:0] words [0:31]`. A rising clock edge
writes one word. Reads are combinational: `words[pc_addr]` feeds the decoder and
`words[load_addr]` feeds host readback. Thus it logically has two read paths and
one write path. Declaring a Verilog array does not select an ASIC SRAM macro.
The qualified ASIC build uses ordinary standard cells and muxes, with no memory
macros; see [measured implementation results](project_status.md). An
FPGA tool may use distributed RAM or registers depending on inference; the
actual implementation report is authoritative. No physical SRAM macro is
instantiated in the current RTL.

Each FIFO in `pio_fifo.sv` is four words plus read/write pointers and an occupancy
counter. Its head is also read combinationally. Empty reads return zero; the
level controls whether a word is valid. On a full queue, simultaneous pop and
push are allowed and the consumer gets the **old head**. On an empty queue, a
same-edge push is not immediately available to a pop. These are architectural
rules that a future memory implementation must preserve.

## How one SPI byte uses this storage

1. The host loads the ten SPI instructions into instruction slots 0–9. Those
   instructions stay there throughout the batch; they are not consumed.
2. For MOSI byte `96`, the host enqueues TX word `96000000`. Little-endian host
   writes send bytes `00 00 00 96`, committing the complete word on the last byte.
3. PULL moves that FIFO word into OSR. Eight one-bit OUT instructions shift its
   high bits onto MOSI. X counts the eight iterations.
4. Eight IN instructions shift the synchronized MISO bits into ISR. A received
   byte `3D` becomes ISR value `0000003D`.
5. PUSH copies ISR into RX FIFO and clears ISR/count. A host low-byte read of RX
   pops the word and snapshots all 32 bits for coherent subsequent byte reads.

An instruction and a received byte are stored in different memories. A full RX
FIFO cannot overwrite program instructions. FIFO occupancy and instruction
addresses are not interchangeable.

## Loading, reset and power loss

The ASIC instruction memory has no reset initialization. Power-up contents are
unspecified, so a host must load every reachable instruction before START. A
normal core reset preserves instruction-memory contents but resets register
state and FIFO occupancy. FIFO storage bits themselves are not reset; old words
become inaccessible because the queues are empty.

The fixed FPGA UART/SPI demo wrappers contain hardcoded loader ROMs. The newer
[programmable bring-up bridge](../tools/bringup/README.md) instead accepts runtime
program/register commands from Python. After reset, each fixed loader writes its
program/configuration through the same host bus that an external controller
would use. That loader is **FPGA test infrastructure**, not an embedded boot ROM
in the ASIC core. In a standalone ASIC system, an MCU or other host must provide
the program after power-up, unless a future boot mechanism is explicitly added.

SRAM holds bits while powered and needs no DRAM-style refresh, but it is still
volatile. Adding SRAM would not make firmware survive power loss. A host, external
Flash, or deliberately designed ROM/bootloader remains necessary for startup.

## What an actual SRAM integration would require

An SRAM macro is a physical memory block with a specific depth, width, port count,
timing and read/write behavior. Integration needs its functional model, timing
library and physical views, along with an RTL wrapper and physical-flow support.
No macro, capacity or final memory layout has been selected for this project.

For these tiny existing arrays, macro overhead could outweigh the savings. SRAM
becomes more attractive as program or packet storage grows, but actual mapped
area, macro dimensions and routing decide whether it fits the tile budget.

The central complication is **read latency**. Today's instruction read is
combinational: PC -> instruction -> decoder -> datapath -> next registered state
fits in one execution cycle. A synchronous SRAM normally returns a requested
instruction after a clock edge. Substituting it blindly adds a fetch stage and
breaks timing-sensitive firmware.

There are several possible designs, none implemented yet:

- Keep a small instruction store in registers/distributed logic and use SRAM only
  for packet data. This is the least disruptive first use of a memory macro.
- Add a prefetch/pipeline mechanism with specified branch and EXEC behavior.
  Preserving one instruction per tick on all paths requires a complete design,
  not just sequential prefetch; taken branches can invalidate the prefetched word.
- Define a new, documented execution timing contract and rebuild firmware/tests
  for it. The change must be explicit in the ISA version.

Port ownership also matters. The current host can read instruction memory while
the engine runs. A single-read-port SRAM cannot simultaneously serve independent
PC and host addresses at full rate without arbitration, replication, or changing
that host-read rule. Host instruction writes are already restricted to stopped
state, which helps with write arbitration.

For FIFO-backed SRAM, a prefetched head register can hide synchronous read latency,
but refill and full/empty boundary behavior need explicit control. Do not rely on
an unspecified SRAM read-during-write result to reproduce the existing old-head
semantics. Buffer validity, simultaneous producer/consumer operations and reset
must remain well-defined and be covered by the FIFO tests.

## Larger programs and packet RAM are separate features

A larger instruction SRAM also requires wider instruction addresses. PC, wrap,
ENTRY, host addressing and encoded five-bit JMP targets currently limit programs
to 32 slots. A larger physical memory alone does not make extra instructions
reachable; the ISA needs an addressing or banking extension.

Packet RAM would serve a different purpose: retaining longer payloads so the host
does not need to service a four-word FIFO immediately. It would need an address
map, read/write arbitration and ownership/length metadata. If PIO firmware must
access arbitrary packet locations directly, it also needs new memory operations
and address state. The current IN/OUT/PUSH/PULL instructions are not general
memory loads and stores.

A sensible first candidate is to keep deterministic instruction fetch and the
four main registers as they are, then evaluate deeper FIFO/packet storage behind
a defined interface. Whether that storage should be flip-flops or a particular
SRAM macro is an area/timing decision after measurement, not a prerequisite for
the current SPI test.
