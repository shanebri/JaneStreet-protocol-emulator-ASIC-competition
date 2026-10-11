# SPDX-License-Identifier: Apache-2.0
"""Pin-only V0 regression, also usable against the hardened gate-level netlist."""
from pathlib import Path

import cocotb
from cocotb.triggers import Timer

CTRL, STATUS, IM_ADDR, IM_LO, IM_HI, DM_ADDR, DM_LO, DM_HI, PC, ACC_LO, ACC_HI = range(11)
GPIO, UART_DATA, UART_DIV, UART_STATUS = 0x10, 0x11, 0x12, 0x13


def ins(op, value=0):
    assert 0 <= op < 16 and 0 <= value < 4096
    return (op << 12) | value


class Host:
    def __init__(self, dut):
        self.dut = dut
        self.samples = []

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
        self.dut.ui_in.value = 0
        self.dut.uio_in.value = 0
        self.dut.rst_n.value = 0
        await self.tick(3)
        self.dut.rst_n.value = 1
        await self.tick()
        assert self.samples[-1] == 1  # TX idle high, GPIO zero
        assert int(self.dut.uio_oe.value) == 0

    async def write(self, address, value, held=1):
        self.dut.ui_in.value = address | 0x10
        self.dut.uio_in.value = value
        await self.tick(held)
        assert int(self.dut.uio_oe.value) == 0
        self.dut.ui_in.value = address
        await self.tick()

    async def read(self, address):
        self.dut.ui_in.value = address | 0x20
        self.dut.uio_in.value = 0  # external host releases the physical bus
        await self.tick()
        assert int(self.dut.uio_oe.value) == 255
        value = int(self.dut.uio_out.value)
        self.dut.ui_in.value = address
        await self.tick()
        assert int(self.dut.uio_oe.value) == 0
        return value

    async def load(self, words, address=0):
        await self.write(IM_ADDR, address)
        for word in words:
            await self.write(IM_LO, word & 255)
            await self.write(IM_HI, word >> 8)

    async def read_instruction(self, address):
        await self.write(IM_ADDR, address)
        return await self.read(IM_LO) | ((await self.read(IM_HI)) << 8)

    async def write_word(self, address, value):
        await self.write(DM_ADDR, address)
        await self.write(DM_LO, value & 255)
        await self.write(DM_HI, value >> 8)

    async def read_word(self, address):
        await self.write(DM_ADDR, address)
        return await self.read(DM_LO) | ((await self.read(DM_HI)) << 8)

    async def accumulator(self):
        return await self.read(ACC_LO) | ((await self.read(ACC_HI)) << 8)

    async def done(self, timeout=100):
        for _ in range(timeout):
            status = await self.read(STATUS)
            assert status & 4 == 0, "CPU reported illegal instruction"
            if status & 3 == 0:
                return
        assert False, "CPU/UART did not finish within bounded timeout"


def check_frames(samples, payload, divider):
    """Check the entire waveform, including start/stop and every bit boundary."""
    tx = [sample & 1 for sample in samples]
    cursor = 1
    starts = []
    for byte in payload:
        while cursor < len(tx) and not (tx[cursor - 1] == 1 and tx[cursor] == 0):
            cursor += 1
        assert cursor < len(tx), f"Missing UART start for {byte:#x}"
        starts.append(cursor)
        expected = [0] + [(byte >> bit) & 1 for bit in range(8)] + [1]
        waveform = [bit for bit in expected for _ in range(divider)]
        assert tx[cursor:cursor + 10 * divider] == waveform, f"Bad UART frame {byte:#x}"
        cursor += 10 * divider
    assert all(tx[cursor:]), "Unexpected extra UART frame after payload"
    return starts


@cocotb.test()
async def host_bus_memory_and_reset(dut):
    h = Host(dut)
    await h.reset()
    assert await h.read(STATUS) == 0
    assert await h.read(PC) == 0
    assert await h.accumulator() == 0
    assert await h.read_word(UART_DIV) == 434
    for address in range(8):
        assert await h.read_word(address) == 0
        await h.write_word(address, 0xA500 + address)
        assert await h.read_word(address) == 0xA500 + address

    # Commit only on HI; a held WR must neither repeat nor increment repeatedly.
    await h.load([0xABCD], 31)
    assert await h.read(IM_ADDR) == 0
    await h.write(IM_LO, 0x34)
    await h.write(IM_HI, 0x12, held=5)
    assert await h.read(IM_ADDR) == 1
    assert await h.read_instruction(0) == 0x1234
    assert await h.read_instruction(31) == 0xABCD
    await h.write(IM_LO, 0xEE)
    assert await h.read_instruction(31) == 0xABCD

    # Read data stays latched while RD remains high even if address changes.
    dut.ui_in.value = IM_ADDR | 0x20
    await h.tick()
    assert int(dut.uio_out.value) == 31
    dut.ui_in.value = STATUS | 0x20
    await h.tick(3)
    assert int(dut.uio_out.value) == 31
    dut.ui_in.value = 0
    await h.tick()

    # Conflicting strobes do not write, and the design releases the bus.
    dut.ui_in.value = IM_ADDR | 0x30
    dut.uio_in.value = 9
    await h.tick(3)
    assert int(dut.uio_oe.value) == 0
    dut.ui_in.value = 0
    await h.tick()
    assert await h.read(IM_ADDR) == 31
    await h.write_word(GPIO, 0xFFFF)
    assert int(dut.uo_out.value) == 255
    assert await h.read_word(GPIO) == 0x7F
    await h.write_word(0xFF, 0x1234)
    assert await h.read_word(0xFF) == 0
    assert await h.read(15) == 0
    await h.reset()
    assert await h.read_word(0) == 0
    assert await h.read_instruction(0) == 0x1234  # program RAM survives reset


@cocotb.test()
async def execution_load_store_alu_and_branches(dut):
    h = Host(dut)
    await h.reset()
    await h.write_word(7, 0xFFFF)
    program = [
        ins(2, 7), ins(4, 1), ins(9, 4), ins(15),  # 16-bit wrap, JZ taken
        ins(5, 1), ins(3, 0),                       # 0 - 1 = FFFF
        ins(6, 0xFF), ins(7, 0xAA), ins(14),        # AND, XOR, SHL => AA
        ins(3, 1), ins(1, 3), ins(5, 1), ins(10, 11),  # decrement loop
        ins(10, 3), ins(4, 5), ins(9, 3),           # untaken JNZ and JZ
        ins(8, 18), ins(15), ins(0), ins(3, GPIO), ins(13),
    ]
    await h.load(program)
    await h.write(CTRL, 1)
    await h.done()
    assert await h.read_word(0) == 0xFFFF
    assert await h.read_word(1) == 0xAA
    assert await h.accumulator() == 5
    assert int(dut.uo_out.value) >> 1 == 5
    assert await h.read(PC) == 20
    await h.tick(10)
    assert await h.read(PC) == 20


@cocotb.test()
async def exact_wait_timing(dut):
    h = Host(dut)
    for delay in (0, 1, 7, 4095):
        await h.reset()
        await h.load([ins(1, 1), ins(3, GPIO), ins(11, delay),
                      ins(1, 2), ins(3, GPIO), ins(13)])
        begin = len(h.samples)
        await h.write(CTRL, 1)
        await h.tick(delay + 10)
        values = [sample >> 1 for sample in h.samples[begin:]]
        assert values.index(2) - values.index(1) == delay + 3
        assert await h.read(STATUS) == 0


@cocotb.test()
async def uart_end_to_end_multiple_bytes_and_dividers(dut):
    h = Host(dut)
    payload = [0x55, 0x00, 0xFF, 0xA6]
    for programmed_divider in (0, 1, 2, 7, 434):
        await h.reset()
        divider = max(1, programmed_divider)
        program = [ins(1, programmed_divider), ins(3, UART_DIV)]
        for byte in payload:
            program += [ins(1, byte), ins(3, UART_DATA)]  # busy ST must stall
        program += [ins(12), ins(1, 1), ins(3, GPIO), ins(13)]
        await h.load(program)
        begin = len(h.samples) - 1
        await h.write(CTRL, 1)
        await h.tick(len(payload) * (10 * divider + 4) + 20)
        starts = check_frames(h.samples[begin:], payload, divider)
        assert h.samples[begin + starts[-1] + 10 * divider - 1] >> 1 == 0
        assert int(dut.uo_out.value) >> 1 == 1
        assert await h.read(STATUS) == 0
        assert await h.read_word(UART_STATUS) == 0
        assert await h.read_word(UART_DATA) == payload[-1]
        assert await h.read_word(UART_DIV) == divider


@cocotb.test()
async def documented_uart_demo(dut):
    h = Host(dut)
    await h.reset()
    demo = Path(__file__).resolve().parents[1] / "examples" / "uart_v0.hex"
    words = [int(line, 16) for line in demo.read_text().splitlines()]
    await h.load(words)
    for address, word in enumerate(words):
        assert await h.read_instruction(address) == word
    begin = len(h.samples) - 1
    await h.write(CTRL, 1)
    await h.tick(4400)
    check_frames(h.samples[begin:], [0x55], 434)
    assert await h.read(STATUS) == 0
    assert await h.read_word(0) == 0x55
    assert int(dut.uo_out.value) == 3


@cocotb.test()
async def uart_status_polling_and_halt_completion(dut):
    h = Host(dut)
    await h.reset()
    await h.write_word(UART_DIV, 7)
    await h.load([ins(1, 0x81), ins(3, UART_DATA), ins(2, UART_STATUS),
                  ins(10, 2), ins(1, 0x7E), ins(3, UART_DATA), ins(13)])
    begin = len(h.samples) - 1
    await h.write(CTRL, 1)
    await h.tick(85)
    assert await h.read(STATUS) == 2  # HALT allows the last frame to finish
    await h.tick(80)
    check_frames(h.samples[begin:], [0x81, 0x7E], 7)
    assert await h.read(STATUS) == 0


@cocotb.test()
async def running_protection_stop_restart_and_faults(dut):
    h = Host(dut)
    await h.reset()
    await h.write_word(0, 0x1234)
    await h.load([ins(11, 4095), ins(8, 0)])
    await h.write(CTRL, 1)
    assert await h.read(STATUS) == 9
    await h.write(IM_ADDR, 0)
    await h.write(IM_LO, 0)
    await h.write(IM_HI, 0xD0)
    assert await h.read(IM_ADDR) == 0
    assert await h.read_instruction(0) == ins(11, 4095)
    await h.write_word(0, 0xBEEF)
    await h.write_word(GPIO, 127)
    assert await h.read_word(0) == 0x1234
    assert int(dut.uo_out.value) == 1
    await h.write(CTRL, 3)  # STOP takes precedence over START
    assert await h.read(STATUS) == 0
    for invalid in (ins(15), ins(8, 32), ins(9, 0xFFF), ins(10, 32)):
        await h.load([invalid])
        await h.write(CTRL, 1)
        await h.tick(2)
        assert await h.read(STATUS) == 4
        assert await h.read(PC) == 0
    await h.load([ins(1, 9), ins(13)])
    await h.write(CTRL, 1)
    await h.done()
    assert await h.accumulator() == 9
    await h.write(CTRL, 1)  # restart from PC=0 clears fault and accumulator
    await h.done()
    assert await h.accumulator() == 9


@cocotb.test()
async def uart_abort_and_disabled_interface(dut):
    h = Host(dut)
    for reset_abort in (False, True):
        await h.reset()
        await h.load([ins(1, 0), ins(3, UART_DATA), ins(12), ins(13)])
        await h.write(CTRL, 1)
        await h.tick(5)
        assert await h.read(STATUS) == 11
        assert int(dut.uo_out.value) & 1 == 0
        if reset_abort:
            await h.reset()
        else:
            await h.write(CTRL, 2)
        assert int(dut.uo_out.value) & 1 == 1
        assert await h.read(STATUS) == 0

    dut.ena.value = 0
    await h.write(IM_ADDR, 12)
    dut.ui_in.value = STATUS | 0x20
    await h.tick()
    assert int(dut.uio_oe.value) == 0
    dut.ui_in.value = 0
    await h.tick()
    dut.ena.value = 1
    assert await h.read(IM_ADDR) == 0


@cocotb.test()
async def host_uart_write_and_divider_snapshot(dut):
    h = Host(dut)
    await h.reset()
    await h.write_word(UART_DIV, 16)
    begin = len(h.samples) - 1
    await h.write_word(UART_DATA, 0x96)
    assert await h.read(STATUS) == 2
    await h.write_word(UART_DATA, 0x55)  # busy host write is ignored
    await h.write_word(UART_DIV, 2)     # active frame keeps captured divider
    await h.tick(170)
    check_frames(h.samples[begin:], [0x96], 16)
    assert await h.read_word(UART_DATA) == 0x96
    assert await h.read_word(UART_DIV) == 2


@cocotb.test()
async def program_counter_wraps_at_32_words(dut):
    h = Host(dut)
    await h.reset()
    await h.load([ins(4, 1)] * 32)
    await h.write(CTRL, 1)
    await h.tick(70)
    await h.write(CTRL, 2)
    value = await h.accumulator()
    assert value >= 71
    assert await h.read(PC) == value % 32
