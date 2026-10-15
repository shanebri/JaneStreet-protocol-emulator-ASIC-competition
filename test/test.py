"""PIO V0 pin-only regression, also usable with a gate-level netlist."""
from pathlib import Path
import random
import sys

import cocotb
from cocotb.triggers import Timer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from pioasm import assemble, encode

CTRL, STATUS, IM_ADDR, IM_LO, IM_HI, DATA_ADDR = range(6)
DATA_BYTES = (6, 7, 9, 10)
PC, LEVEL, IRQ, DEBUG, INPUT, VERSION = 8, 11, 12, 13, 14, 15
X, Y, OSR, ISR, PINS, COUNTS, TX, RX = 0, 1, 2, 3, 4, 5, 8, 9
SHIFT, EXEC, PINCTRL, DIVIDER, IRQ_SET = 0x10, 0x11, 0x12, 0x13, 0x14
MASK = 0xffffffff


class Host:
    def __init__(self, dut):
        self.dut = dut
        self.samples = []
        self.inputs = 0

    def control(self, value):
        self.dut.ui_in.value = value | (self.inputs << 6)

    async def tick(self, count=1):
        for _ in range(count):
            self.dut.clk.value = 0
            await Timer(10, unit="ns")
            self.dut.clk.value = 1
            await Timer(10, unit="ns")
            self.samples.append(int(self.dut.uo_out.value))

    async def reset(self):
        self.dut.clk.value = 0
        self.dut.ena.value = 1
        self.inputs = 0
        self.control(0)
        self.dut.uio_in.value = 0
        self.dut.rst_n.value = 0
        await self.tick(3)
        self.dut.rst_n.value = 1
        await self.tick()
        assert self.samples[-1] == 1
        assert int(self.dut.uio_oe.value) == 0

    async def write(self, address, value, held=1):
        self.control(address | 0x10)
        self.dut.uio_in.value = value
        await self.tick(held)
        assert int(self.dut.uio_oe.value) == 0
        self.control(address)
        await self.tick()

    async def read(self, address, held=1):
        self.control(address | 0x20)
        self.dut.uio_in.value = 0
        await self.tick(held)
        assert int(self.dut.uio_oe.value) == 255
        value = int(self.dut.uio_out.value)
        self.control(address)
        await self.tick()
        assert int(self.dut.uio_oe.value) == 0
        return value

    async def load(self, program, address=0):
        words = assemble(program) if isinstance(program, str) else program
        await self.write(IM_ADDR, address)
        for word in words:
            await self.write(IM_LO, word & 255)
            await self.write(IM_HI, word >> 8)

    async def read_instruction(self, address):
        await self.write(IM_ADDR, address)
        return await self.read(IM_LO) | ((await self.read(IM_HI)) << 8)

    async def write_word(self, address, value):
        await self.write(DATA_ADDR, address)
        for i, register in enumerate(DATA_BYTES):
            await self.write(register, (value >> (8 * i)) & 255)

    async def read_word(self, address):
        await self.write(DATA_ADDR, address)
        value = 0
        for i, register in enumerate(DATA_BYTES):
            value |= (await self.read(register)) << (8 * i)
        return value

    async def done(self, timeout=100):
        for _ in range(timeout):
            status = await self.read(STATUS)
            assert not status & 4, "illegal instruction"
            if not status & 1:
                return
        raise AssertionError("state machine did not finish")


def check_frames(samples, payload, clocks):
    tx = [sample & 1 for sample in samples]
    cursor = 1
    starts = []
    for byte in payload:
        while cursor < len(tx) and not (tx[cursor-1] == 1 and tx[cursor] == 0):
            cursor += 1
        assert cursor < len(tx), f"missing UART start for {byte:#x}"
        starts.append(cursor)
        bits = [0] + [(byte >> bit) & 1 for bit in range(8)] + [1]
        expected = [bit for bit in bits for _ in range(clocks)]
        assert tx[cursor:cursor+10*clocks] == expected, f"bad frame {byte:#x}"
        cursor += 10*clocks
    assert all(tx[cursor:]), "unexpected extra frame"
    return starts


@cocotb.test()
async def host_bus_atomic_words_and_reset(dut):
    h = Host(dut)
    await h.reset()
    assert await h.read(VERSION) == 0x20
    assert await h.read(STATUS) == 0x10
    assert await h.read(LEVEL) == 0
    assert await h.read_word(COUNTS) == 32
    for address, value in ((X, 0xdeadbeef), (Y, 0x12345678), (OSR, MASK), (ISR, 0x81020408)):
        await h.write_word(address, value)
        assert await h.read_word(address) == value
    await h.load([0xabcd], 31)
    assert await h.read(IM_ADDR) == 0
    await h.write(IM_LO, 0x34)
    await h.write(IM_HI, 0x12, held=5)
    assert await h.read(IM_ADDR) == 1
    assert await h.read_instruction(0) == 0x1234
    assert await h.read_instruction(31) == 0xabcd
    await h.write(DATA_ADDR, X)
    await h.write(6, 0x11)
    assert await h.read_word(X) == 0xdeadbeef  # no partial commit
    h.control(IM_ADDR | 0x20)
    await h.tick()
    assert int(dut.uio_out.value) == 31
    h.control(STATUS | 0x20)
    await h.tick(3)
    assert int(dut.uio_out.value) == 31
    h.control(0)
    await h.tick()
    h.control(IM_ADDR | 0x30)
    dut.uio_in.value = 9
    await h.tick(3)
    assert int(dut.uio_oe.value) == 0
    h.control(0)
    await h.tick()
    assert await h.read(IM_ADDR) == 31
    await h.reset()
    assert await h.read_word(X) == 0
    assert await h.read_instruction(0) == 0x1234


@cocotb.test()
async def variable_shifts_all_widths_both_directions(dut):
    h = Host(dut)
    rng = random.Random(42)
    for right in (0, 1):
        for width in range(1, 33):
            await h.reset()
            value = rng.getrandbits(32)
            initial = rng.getrandbits(32)
            await h.write_word(SHIFT, 3 if right else 0)
            await h.write_word(OSR, value)
            await h.write_word(ISR, initial)
            await h.load(f"out x, {width}\nin x, {width}\nhalt")
            await h.write(CTRL, 16)  # RESUME keeps host-initialized registers.
            await h.done()
            mask = (1 << width) - 1
            out = value & mask if right else value >> (32-width)
            shifted = value >> width if right else (value << width) & MASK
            received = (initial >> width) | (out << (32-width)) if right else ((initial << width) | out) & MASK
            assert await h.read_word(X) == out, (right, width)
            assert await h.read_word(OSR) == shifted
            assert await h.read_word(ISR) == received
            assert await h.read_word(COUNTS) == (width << 8) | width
    # Saturating shift counters, not modulo-32 counters.
    await h.load("in null, 31\nin null, 31\nout null, 31\nout null, 31\nhalt")
    await h.write(CTRL, 1)
    await h.done()
    assert await h.read_word(COUNTS) == 0x2020


@cocotb.test()
async def scratch_branches_mov_and_exec(dut):
    h = Host(dut)
    await h.reset()
    program = """
        set x, 2
        set y, 2
        jmp x!=y, bad
        jmp !x, bad
        jmp !y, bad
    loop: jmp x--, loop
        mov isr, x
        push block
    yloop: jmp y--, yloop
        mov isr, y
        push block
        mov x, null
        jmp !x, equal
    bad: halt
    equal: mov y, ~null
        mov isr, ::y
        push block
        halt
    """
    await h.load(program)
    await h.write(CTRL, 1)
    await h.done()
    assert await h.read(LEVEL) == 0x30
    for _ in range(3):
        assert await h.read_word(RX) == MASK  # decrement uses old value, then wraps
    # EXEC executes the low 16 bits on the following tick, without skipping PC.
    await h.reset()
    await h.write_word(TX, assemble("set pins, 5")[0])
    await h.load("pull block\nmov exec, osr\nset pins, 6\nhalt")
    begin = len(h.samples)
    await h.write(CTRL, 1)
    await h.tick(8)
    samples = h.samples[begin:]
    assert samples.index(6) - samples.index(5) == 1
    assert await h.read(PC) == 3
    # OUT EXEC, MOV PC, and OUT PC take effect without a branch bubble.
    await h.reset()
    await h.write_word(TX, assemble("set x, 4")[0])
    await h.load("pull block\nout exec, 16\nmov pc, x\nhalt\nset pins, 9\nhalt")
    await h.write(CTRL, 1)
    await h.done()
    assert h.samples[-1] == 9
    await h.reset()
    await h.write_word(TX, 3)
    await h.load("pull block\nout pc, 32\nhalt\nset pins, 10\nhalt")
    await h.write(CTRL, 1)
    await h.done()
    assert h.samples[-1] == 10
    await h.reset()
    await h.write_word(X, 0x12345678)
    await h.load("mov y, ::x\nmov isr, ~x\nhalt")
    await h.write(CTRL, 16)
    await h.done()
    assert await h.read_word(Y) == 0x1e6a2c48
    assert await h.read_word(ISR) == 0xedcba987


@cocotb.test()
async def fifo_order_backpressure_and_nonblocking(dut):
    h = Host(dut)
    await h.reset()
    values = [0x12345678, MASK, 0x80000001, 0]
    for value in values:
        await h.write_word(TX, value)
    assert await h.read(LEVEL) == 4
    await h.write_word(TX, 0xbad)
    assert await h.read(DEBUG) == 1
    await h.write(DEBUG, 1)
    await h.load("pull block\nmov isr, osr\npush block\njmp 0")
    await h.write(CTRL, 1)
    await h.tick(30)
    assert await h.read(LEVEL) == 0x40
    assert (await h.read(STATUS)) & 3 == 3
    assert await h.read(PC) == 0
    # Fifth item reaches PUSH and blocks with full RX, preserving ISR and PC.
    await h.write_word(TX, 0xabcdef01)
    await h.tick(5)
    assert await h.read(PC) == 2
    assert await h.read_word(ISR) == 0xabcdef01
    await h.write(DATA_ADDR, RX)
    low = await h.read(6, held=5)  # Pop exactly once even while next push retires.
    word = low
    for i, reg in enumerate(DATA_BYTES[1:], 1):
        word |= (await h.read(reg)) << (8*i)
    assert word == values[0]
    assert await h.read(LEVEL) == 0x40
    for value in values[1:] + [0xabcdef01]:
        assert await h.read_word(RX) == value
    assert await h.read(LEVEL) == 0
    assert await h.read_word(RX) == 0
    assert await h.read(DEBUG) == 2
    await h.write(CTRL, 2)
    await h.load("set x, 19\npull noblock\nmov isr, osr\npush block\nhalt")
    await h.write(CTRL, 9)
    await h.done()
    assert await h.read_word(RX) == 19
    assert await h.read(DEBUG) == 8


@cocotb.test()
async def autopull_autopush_and_atomic_stall(dut):
    h = Host(dut)
    await h.reset()
    # IN shifts left; OUT shifts right; four eight-bit samples per ISR word.
    await h.write_word(SHIFT, 1 | 4 | 8)
    words = [0x12345678, 0x89abcdef, 0x10203040, MASK]
    for word in words:
        await h.write_word(TX, word)
    await h.load("out x, 8\nin x, 8\njmp 0")
    await h.write(CTRL, 1)
    await h.tick(60)
    assert await h.read(LEVEL) == 0x40
    assert await h.read_word(ISR) == 0
    await h.write_word(TX, 0x55667788)
    await h.tick(20)
    assert await h.read(PC) == 1
    assert await h.read_word(ISR) == 0x887766  # Last IN has not partially executed.
    assert (await h.read_word(COUNTS)) >> 8 == 24
    for word in words + [0x55667788]:
        expected = int.from_bytes(word.to_bytes(4, "little"), "big")
        assert await h.read_word(RX) == expected
    assert await h.read(LEVEL) == 0
    assert await h.read(DEBUG) == 0
    # Threshold eight automatically transfers once per byte.
    await h.write(CTRL, 6)
    await h.write_word(SHIFT, 1 | 4 | 8 | (8 << 4) | (8 << 9))
    await h.write_word(TX, 0x55)
    await h.write_word(TX, 0xa6)
    await h.write(CTRL, 1)
    await h.tick(10)
    assert await h.read_word(RX) == 0x55
    assert await h.read_word(RX) == 0xa6


@cocotb.test()
async def deterministic_timing_wrap_delays_and_sideset(dut):
    h = Host(dut)
    for divider in (0, 1, 3, 31):
        for delay in (0, 1, 7, 31):
            await h.reset()
            await h.write_word(DIVIDER, divider)
            await h.load(f"set pins, 2 [{delay}]\nset pins, 3\nhalt")
            begin = len(h.samples)
            await h.write(CTRL, 1)
            await h.tick((delay+4)*max(1, divider))
            values = h.samples[begin:]
            assert values.index(3)-values.index(2) == (delay+1)*max(1, divider)
    await h.reset()
    await h.load("set pins, 2\nset pins, 3\nset pins, 4\nhalt")
    await h.write_word(EXEC, 1 | (2 << 5) | (1 << 10))
    begin = len(h.samples)
    await h.write(CTRL, 1)
    await h.tick(8)
    assert h.samples[begin+1:begin+9] == [3, 4]*4  # Zero-cost wrap and entry.
    await h.write(CTRL, 2)
    await h.reset()
    await h.write_word(EXEC, (31 << 5) | (1 << 15))
    await h.write_word(PINCTRL, 1 << 17)  # side-set pin 1
    await h.load(".sideset\npull block side 1\nset pins, 0 side 1 [3]\nset pins, 1 side 0\nhalt")
    await h.write(CTRL, 1)
    await h.tick(5)
    assert h.samples[-1] == 3  # Side-set applies while PULL stalls.
    begin = len(h.samples)
    await h.write_word(TX, 0)
    await h.tick(10)
    assert await h.read(STATUS) & 1 == 0
    assert h.samples[-1] == 1
    values = h.samples[begin:]
    assert values.index(1) - values.index(2) == 4
    # Distinct OUT/SET mapping, clipping at pin 7 and preservation of other pins.
    await h.reset()
    await h.write_word(PINS, 0x15)
    await h.write_word(PINCTRL, 6 | (4 << 3) | (2 << 8) | (2 << 11))
    await h.write_word(TX, 3)
    await h.load("pull block\nout pins, 2\nset pins, 2\nhalt")
    await h.write(CTRL, 1)
    await h.done()
    assert h.samples[-1] == 0xd9


@cocotb.test()
async def input_wait_irq_and_firmware_receive(dut):
    h = Host(dut)
    await h.reset()
    await h.load("wait 1, gpio, 1\njmp pin, taken\nhalt\ntaken: in pins, 2\npush block\nirq wait, 3\nset pins, 7\nhalt")
    await h.write_word(PINCTRL, 1 << 20)
    await h.write(CTRL, 1)
    await h.tick(5)
    assert await h.read(PC) == 0
    h.inputs = 3
    h.control(0)
    await h.tick(10)
    assert await h.read_word(RX) == 0xc0000000
    assert await h.read(IRQ) == 8
    assert await h.read(PC) == 5
    await h.write(IRQ, 8)
    await h.done()
    assert h.samples[-1] == 7
    # UART RX is also a program, driven at exact clock resolution.
    rx_program = (ROOT / "examples/uart_rx.asm").read_text()
    for byte in (0, 0xff, 0x55, 0xa6):
        await h.reset()
        h.inputs = 1
        h.control(0)
        await h.tick(3)
        await h.load(rx_program)
        await h.write(CTRL, 1)
        await h.tick(8)
        for bit in [0] + [(byte >> b) & 1 for b in range(8)] + [1]:
            h.inputs = bit
            h.control(0)
            await h.tick(16)
        await h.done()
        assert await h.read_word(RX) == byte << 24


@cocotb.test()
async def firmware_uart_full_waveforms_and_example(dut):
    h = Host(dut)
    payload = [0x55, 0x00, 0xff, 0xa6]
    for divider in (1, 2, 31):
        await h.reset()
        await h.write_word(DIVIDER, divider)
        await h.write_word(PINCTRL, 0x1008)
        for byte in payload:
            await h.write_word(TX, byte)
        await h.load("pull block\nset x, 7\nset pins, 0 [13]\nout pins, 1 [12]\njmp x--, 3\nset pins, 1 [13]\njmp 0")
        begin = len(h.samples)-1
        await h.write(CTRL, 1)
        await h.tick(4*145*divider + 20)
        check_frames(h.samples[begin:], payload, 14*divider)
        assert await h.read(PC) == 0  # Blocks idle high when input queue runs dry.
    await h.reset()
    program = assemble((ROOT / "examples/uart_v0.asm").read_text())
    hex_words = [int(line, 16) for line in (ROOT / "examples/uart_v0.hex").read_text().splitlines()]
    assert program == hex_words
    await h.write_word(DIVIDER, 31)
    await h.write_word(PINCTRL, 0x1008)
    await h.write_word(TX, 0x55)
    await h.load(hex_words)
    for index, word in enumerate(hex_words):
        assert await h.read_instruction(index) == word
    begin = len(h.samples)-1
    await h.write(CTRL, 1)
    await h.tick(4500)
    starts = check_frames(h.samples[begin:], [0x55], 434)
    marker = next(i for i, value in enumerate(h.samples[begin:]) if value & 2)
    assert marker == starts[0] + 4340
    assert await h.read(STATUS) == 0x10


@cocotb.test()
async def protection_pause_restart_fault_and_natural_wrap(dut):
    h = Host(dut)
    await h.reset()
    await h.load("pull block\nhalt")
    await h.write(CTRL, 1)
    await h.write_word(X, 0xdeadbeef)
    await h.write_word(DIVIDER, 999)
    await h.write(IM_ADDR, 0)
    await h.write(IM_LO, 0x80)
    await h.write(IM_HI, 0xc0)
    assert await h.read_instruction(0) == 0x80a0
    assert await h.read_word(X) == 0
    assert await h.read_word(DIVIDER) == 1
    dut.ena.value = 0
    await h.write(IM_ADDR, 12)
    h.control(STATUS | 0x20)
    await h.tick()
    assert int(dut.uio_oe.value) == 0
    h.control(0)
    await h.tick()
    dut.ena.value = 1
    assert await h.read(IM_ADDR) == 0
    await h.write(CTRL, 3)
    assert not (await h.read(STATUS)) & 1
    for invalid in (encode(3, 0x81), encode(5, 0x1b), encode(7, 0x60), encode(1, 0x62), encode(6, 0x81)):
        await h.load([invalid])
        await h.write(CTRL, 1)
        await h.tick(2)
        assert (await h.read(STATUS)) & 5 == 4
        assert await h.read(PC) == 0
    await h.load([encode(7, i & 31) for i in range(32)])
    await h.write(CTRL, 1)
    await h.tick(70)
    await h.write(CTRL, 2)
    assert await h.read(PC) == (h.samples[-1]+1) % 32
    held = h.samples[-1]
    await h.tick(5)
    assert h.samples[-1] == held
    await h.write(CTRL, 16)
    await h.tick(3)
    assert h.samples[-1] != held


@cocotb.test()
async def conditional_transfers_nonblocking_drop_and_snapshot(dut):
    h = Host(dut)
    await h.reset()
    await h.write_word(SHIFT, 3 | (8 << 4) | (8 << 9))
    await h.write_word(TX, 0x12345678)
    await h.write_word(TX, 0x87654321)
    await h.load("pull ifempty block\npull ifempty block\nout x, 8\npull ifempty block\nmov isr, osr\npush iffull block\nin null, 8\npush iffull block\nhalt")
    await h.write(CTRL, 1)
    await h.done()
    assert await h.read_word(X) == 0x78
    assert await h.read(LEVEL) == 0x10
    assert await h.read_word(RX) == 0x00876543
    # RX full + nonblocking PUSH discards exactly one word and clears ISR.
    await h.reset()
    await h.load("set x, 4\nloop: mov isr, x\npush noblock\njmp x--, loop\nhalt")
    await h.write(CTRL, 1)
    await h.done()
    assert await h.read(DEBUG) == 4
    assert await h.read_word(ISR) == 0
    assert await h.read(LEVEL) == 0x40
    for expected in (4, 3, 2, 1):
        assert await h.read_word(RX) == expected
    # A low-byte snapshot must stay coherent while X changes every clock.
    await h.reset()
    await h.load("jmp x--, 0")
    await h.write_word(X, 0x01000002)
    await h.write(DATA_ADDR, X)
    await h.write(CTRL, 16)
    low = await h.read(6)
    await h.tick(8)  # X crosses into the previous 24-bit upper value.
    high = [(await h.read(reg)) for reg in (7, 9, 10)]
    assert low | (high[0] << 8) | (high[1] << 16) | (high[2] << 24) == 0x01000001


@cocotb.test()
async def freeze_delay_and_irq_wait_semantics(dut):
    h = Host(dut)
    await h.reset()
    await h.load("set pins, 2 [31]\nset pins, 3\nhalt")
    await h.write(CTRL, 1)
    assert h.samples[-1] == 2
    dut.ena.value = 0
    await h.tick(50)
    assert h.samples[-1] == 2
    dut.ena.value = 1
    await h.tick(31)
    assert h.samples[-1] == 2
    await h.tick()
    assert h.samples[-1] == 3
    await h.done()
    await h.reset()
    await h.load("wait 1, irq, 2\nirq set, 1\nirq clear, 1\nset pins, 7\nhalt")
    await h.write(CTRL, 1)
    await h.tick(5)
    assert await h.read(PC) == 0
    await h.write_word(IRQ_SET, 4)
    await h.done()
    assert await h.read(IRQ) == 0  # WAIT 1 IRQ consumes its flag.
    assert h.samples[-1] == 7
    # Stop preserves a partial delay; resume picks up that exact state.
    await h.reset()
    await h.load("set pins, 2 [31]\nset pins, 3\nhalt")
    await h.write(CTRL, 1)
    await h.write(CTRL, 2)
    await h.tick(50)
    assert h.samples[-1] == 2
    await h.write(CTRL, 16)
    await h.tick(30)
    assert h.samples[-1] == 2
    await h.tick()
    assert h.samples[-1] == 3
