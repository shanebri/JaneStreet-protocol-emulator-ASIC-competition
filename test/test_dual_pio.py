"""Dual-engine contract tests using only package pins (also gate-netlist usable)."""
import random

import cocotb
from cocotb.triggers import Timer
from cocotb.utils import get_sim_time
from test import (Host, ROOT, DATA_BYTES, CTRL, STATUS, PC, IRQ, DEBUG, INPUT,
                  IM_ADDR, IM_LO, IM_HI, DATA_ADDR, X, Y, OSR, ISR, PINS,
                  TX, RX, SHIFT, EXEC, PINCTRL, DIVIDER, LEVEL, check_frames)
from test_pio21 import route
from i2c_driver import I2C, Result
from i2c_model import Bus

CAPS, OWNER, GROUP, GLOBAL, SELECTED = range(0x1a, 0x1f)


async def select(h, engine):
    await h.write(15, engine)


async def setup(h, engine, program, *, base=0, divider=1):
    await select(h, engine)
    await h.write_word(PINCTRL, base | (1 << 3) | (base << 8) | (1 << 11))
    await h.write_word(DIVIDER, divider)
    await h.load(program)


@cocotb.test()
async def dual_discovery_and_banked_transactions(dut):
    h = Host(dut)
    await h.reset()
    assert await h.read(15) == 0x21
    assert await h.read_word(CAPS) == 0x50490102
    assert await h.read_word(GLOBAL) == 0x1010
    assert await h.read_word(OWNER) == 0
    assert await h.read_word(SELECTED) == 0
    await select(h, 1)
    await select(h, 255)  # Invalid values do not alias bit zero.
    assert await h.read_word(SELECTED) == 1
    assert await h.read(15) == 0x21
    rng = random.Random(2201)
    for _ in range(12):
        words = [rng.getrandbits(32), rng.getrandbits(32)]
        selectors = [X, Y]
        for e in range(2):
            await select(h, e)
            await h.write(DATA_ADDR, selectors[e])
        for i, register in enumerate(DATA_BYTES):
            for e in (1, 0):
                await select(h, e)
                await h.write(register, (words[e] >> (8*i)) & 255)
        for e in range(2):
            await select(h, e)
            assert await h.read_word(selectors[e]) == words[e]
        # Snapshot both, change live values, then interleave saved high bytes.
        lows = []
        for e in range(2):
            await select(h, e)
            lows.append(await h.read(6))
            await h.write_word(selectors[e], ~words[e] & 0xffffffff)
        restored = lows[:]
        for i, register in enumerate(DATA_BYTES[1:], 1):
            for e in range(2):
                await select(h, e)
                restored[e] |= (await h.read(register)) << (8*i)
        assert restored == words
    # IMEM low-byte staging and auto-increment belong to their original bank.
    for e in range(2):
        await select(h, e)
        await h.write(IM_ADDR, 31)
        await h.write(IM_LO, 0x31 + e)
    for e in (1, 0):
        await select(h, e)
        await h.write(IM_HI, 0xa0 + e, held=3)
        assert await h.read(IM_ADDR) == 0
        assert await h.read_instruction(31) == ((0xa0+e) << 8) | (0x31+e)
    # All common read-only registers ignore commits; GROUP reads zero.
    for address in (CAPS, GLOBAL, SELECTED):
        before = await h.read_word(address)
        await h.write_word(address, 0xffffffff)
        assert await h.read_word(address) == before
    assert await h.read_word(GROUP) == 0
    await h.reset()
    assert await h.read_word(SELECTED) == 0
    assert await h.read_instruction(31) == 0xa031


@cocotb.test()
async def dual_partial_transport_and_disable(dut):
    h = Host(dut)
    await h.reset()
    # A lone low nibble must not select engine 1.
    h.control(0x1f); dut.uio_in.value = 1
    await h.tick(4)
    h.control(0x0f); await h.tick(10)
    assert await h.read_word(SELECTED) == 0  # Address change abandons the byte.
    await select(h, 1)
    await h.write(DATA_ADDR, X)
    await h.write(6, 0x11); await h.write(7, 0x22); await h.write(9, 0x33)
    # Disable drops only physical transport phase, not selected bank or staging.
    h.control(0x1f); dut.uio_in.value = 0
    await h.tick()
    dut.ena.value = 0; await h.tick(3)
    assert int(dut.uio_oe.value) & 15 == 0
    h.control(0); dut.ena.value = 1; await h.tick()
    await h.write(10, 0x44)
    assert await h.read_word(X) == 0x44332211
    assert await h.read_word(SELECTED) == 1
    # RD+WR resynchronization cannot change selection.
    h.control(0x3f); dut.uio_in.value = 0; await h.tick(3)
    assert int(dut.uio_oe.value) & 15 == 0
    h.control(0); await h.tick()
    assert await h.read_word(SELECTED) == 1
    await select(h, 0)
    assert await h.read_word(X) == 0


@cocotb.test()
async def dual_group_start_zero_cycle_wrap_and_branch(dut):
    h = Host(dut)
    await h.reset()
    await setup(h, 0, 'set pins, 0\nset pins, 1')
    await h.write_word(EXEC, 1 << 5)  # Two-instruction hardware wrap.
    await setup(h, 1, 'set pins, 0\nset pins, 1', base=1)
    await h.write_word(EXEC, 1 << 5)
    await h.write_word(OWNER, 2)
    begin = len(h.samples)
    await h.write_word(GROUP, 3)
    await h.tick(15)
    assert h.samples[begin+19:begin+35] == [0, 3]*8
    # Both stop on one edge, resume without resetting phase, restart together.
    await h.write_word(GROUP, 3 << 2)
    frozen = h.samples[-1]
    await h.tick(8)
    assert h.samples[-8:] == [frozen]*8
    await h.write_word(GROUP, 3 << 4)
    begin = len(h.samples)
    await h.tick(8)
    assert all((v & 1) == ((v >> 1) & 1) for v in h.samples[begin:])
    await h.write_word(GROUP, 3 << 2)
    for e in range(2):
        await select(h, e)
        await h.load('set pins, 0\njmp 3\nset pins, 0\nset pins, 1\njmp 0')
        await h.write_word(EXEC, 31 << 5)
    begin = len(h.samples)
    await h.write_word(GROUP, 3)
    await h.tick(15)
    assert h.samples[begin+19:begin+35] == [0, 0, 3, 3]*4


@cocotb.test()
async def dual_independent_dividers_exec_and_load(dut):
    h = Host(dut)
    await h.reset()
    await setup(h, 0, 'set pins, 0\nset pins, 1', divider=1)
    await h.write_word(EXEC, 1 << 5)
    await setup(h, 1, 'set pins, 0\nset pins, 1', base=1, divider=3)
    await h.write_word(EXEC, 1 << 5)
    await h.write_word(OWNER, 2)
    begin = len(h.samples)
    await h.write_word(GROUP, 3)
    await h.tick(17)
    samples = h.samples[begin+19:begin+37]
    assert [v & 1 for v in samples] == [0, 1]*9
    assert [(v >> 1) & 1 for v in samples] == [0]*3+[1]*3+[0]*3+[1]*3+[0]*3+[1]*3
    await h.write(CTRL, 2)  # Stop only currently selected engine 1.
    begin = len(h.samples)
    await h.load('pull block\nmov exec, osr\nhalt')
    await h.write_word(EXEC, 31 << 5)
    await h.write_word(DIVIDER, 1)
    assert all((h.samples[i] ^ h.samples[i+1]) & 1 for i in range(begin, len(h.samples)-1))
    from pioasm import assemble
    await h.write_word(TX, assemble('set x, 27')[0])
    await h.write(CTRL, 1); await h.done()
    assert await h.read_word(X) == 27
    # Engine 0 IMEM remains write-protected while engine 1 was reloaded.
    await select(h, 0)
    original = await h.read_instruction(0)
    await h.load('halt')
    assert await h.read_instruction(0) == original
    assert await h.read(STATUS) & 1
    await h.write_word(GROUP, (3 << 2) | 3)  # STOP wins START on both.
    assert (await h.read_word(GLOBAL) & 0x0101) == 0


@cocotb.test()
async def dual_gpio_owner_values_directions_od_and_abort(dut):
    h = Host(dut)
    await h.reset()
    for mask in [0, 0xfff, *[1 << bit for bit in range(12)], 0xa55]:
        for e in range(2):
            await select(h, e); await h.write_word(0x17, 0)
        await h.write_word(OWNER, mask | 0xfffff000)
        assert await h.read_word(OWNER) == mask
        for e, value, dirs, od in ((0, 0xa55, 0x500, 0x300), (1, 0x5aa, 0xa00, 0xc00)):
            await select(h, e)
            await h.write_word(PINS, value)
            await h.write_word(0x18, od)
            await h.write_word(0x17, dirs)
        expected = (0xa55 & ~mask) | (0x5aa & mask)
        direction = (5 & ~(mask >> 8)) | (10 & (mask >> 8))
        od = (3 & ~(mask >> 8)) | (12 & (mask >> 8))
        assert int(dut.uo_out.value) == expected & 255
        assert int(dut.uio_out.value) >> 4 == ((expected >> 8) & ~od)
        assert int(dut.uio_oe.value) >> 4 == direction & ~(od & (expected >> 8))
    # Changing a driven pad rejects the entire word, including dedicated bits.
    await h.write_word(OWNER, 0)
    assert await h.read_word(OWNER) == 0xa55
    await select(h, 0); await h.write(CTRL, 0x20)
    assert await h.read_word(0x17) == 255
    await select(h, 1)
    assert await h.read_word(0x17) == 0xaff
    await h.write(CTRL, 0x20)
    await h.write_word(OWNER, 0)
    assert await h.read_word(OWNER) == 0
    await h.load('pull block\nhalt'); await h.write(CTRL, 1)
    await h.write_word(OWNER, 0xfff)
    assert await h.read_word(OWNER) == 0
    await select(h, 0)
    await h.write_word(OWNER, 1)
    assert await h.read_word(OWNER) == 0  # Peer running blocks too.
    # Immediate OE reset gating; ownership resets synchronously.
    await h.write_word(0x17, 0xf00); await h.write_word(PINS, 0)
    assert int(dut.uio_oe.value) >> 4 == 15
    dut.rst_n.value = 0
    await Timer(1, unit='ns')
    assert int(dut.uio_oe.value) == 0
    await h.reset()
    assert await h.read_word(OWNER) == 0


@cocotb.test()
async def dual_conflicting_pin_instructions_and_local_irqs(dut):
    h = Host(dut)
    await h.reset()
    for e in range(2):
        await setup(h, e, '.sideset\nset pins, 0 side 1\nirq wait, 3\nset pins, 1 side 0\nhalt', base=0)
        await h.write_word(PINCTRL, 8 | (1 << 11) | (1 << 17))
        await h.write_word(EXEC, 0x83e0)
    await h.write_word(OWNER, 1)  # Engine 1 owns output0; engine 0 owns side-set1.
    await h.write_word(GROUP, 3)
    for e in range(2):
        await select(h, e)
        assert await h.read(IRQ) == 8
        assert await h.read(PC) == 1
    assert int(dut.uo_out.value) & 3 == 2
    await select(h, 0); await h.write(IRQ, 8); await h.done()
    assert int(dut.uo_out.value) & 3 == 0  # Non-owner SET0 changes only shadow.
    await select(h, 1)
    assert await h.read(IRQ) == 8
    assert await h.read(PC) == 1
    await h.write(IRQ, 8); await h.done()
    assert int(dut.uo_out.value) & 3 == 1
    await h.write_word(0x14, 0xa5)
    await select(h, 0); await h.write_word(0x14, 0x5a)
    assert await h.read_word(GLOBAL) == 0xa55a3030


@cocotb.test()
async def dual_fifo_isolation_clear_and_rx_snapshots(dut):
    h = Host(dut)
    await h.reset()
    words = [[0x10203040+i for i in range(4)], [0xa1b2c3d0+i for i in range(4)]]
    for e in range(2):
        await setup(h, e, 'wait 1, gpio, 0\npull block\nmov isr, osr\npush block\njmp 1')
        for value in words[e]:
            await h.write_word(TX, value)
    await h.write_word(GROUP, 3)
    h.inputs = 1; h.control(0); await h.tick(24)
    for e in range(2):
        await select(h, e)
        assert await h.read(LEVEL) == 0x40
        await h.write(DATA_ADDR, RX)
    # Pop/snapshot each bank, then interleave the saved high bytes.
    result = [0, 0]
    for i, register in enumerate(DATA_BYTES):
        for e in range(2):
            await select(h, e)
            result[e] |= (await h.read(register, held=3)) << (8*i)
    assert result == [words[0][0], words[1][0]]
    for e in range(2):
        await select(h, e)
        assert await h.read(LEVEL) == 0x30
    await select(h, 0); await h.write(CTRL, 2 | 4)
    assert await h.read(LEVEL) == 0
    await select(h, 1)
    assert await h.read(LEVEL) == 0x30
    assert await h.read(STATUS) & 1
    for value in words[1][1:]:
        assert await h.read_word(RX) == value
    assert await h.read(DEBUG) == 0
    await h.read_word(RX)
    assert await h.read(DEBUG) == 2
    await select(h, 0)
    assert await h.read(DEBUG) == 0


@cocotb.test()
async def dual_shared_sampling_independent_filters(dut):
    h = Host(dut)
    await h.reset()
    for e in range(2):
        await setup(h, e, 'wait 1, gpio, 2\nset pins, 1\nhalt', base=e)
        await h.write_word(PINS, 0)
        await h.write_word(0x19, e)  # Only engine 1 qualifies pad0.
    await h.write_word(OWNER, 2)
    await h.write_word(GROUP, 3)
    dut.uio_in.value = 0x10
    await h.tick(2)
    dut.uio_in.value = 0
    await h.tick(8)
    assert int(dut.uo_out.value) == 1
    dut.ena.value = 0
    dut.uio_in.value = 0x10
    await h.tick(8)  # Sampling/filtering continue while both engines freeze.
    assert int(dut.uo_out.value) == 1
    dut.ena.value = 1; h.control(0)
    await h.tick(3)
    assert int(dut.uo_out.value) == 3
    for e in range(2):
        await select(h, e)
        assert await h.read(INPUT) == 4


@cocotb.test()
async def dual_i2c_uart_concurrent_roles(dut):
    # Exercise the production I2C driver on either engine with a concurrent UART.
    for i2c_engine in range(2):
        h = Host(dut)
        await h.reset()
        await h.write_word(OWNER, 0xff if i2c_engine == 0 else 0xf00)
        await select(h, 1-i2c_engine)
        await h.write_word(PINCTRL, 0x1008)
        await h.write_word(DIVIDER, 31)
        await h.load((ROOT / 'examples/uart_v0.asm').read_text())
        await h.write_word(TX, 0x55)
        bus = Bus(dut, host=h, data=b'\xa6', stretches={7:2300})
        try:
            await select(h, i2c_engine)
            i2c = I2C(h, clock=lambda: float(get_sim_time(unit='sec')))
            await i2c.configure(400_000)
            await select(h, 1-i2c_engine)
            begin = len(h.samples)
            await h.write(CTRL, 1)
            await select(h, i2c_engine)
            result = await i2c.transfer(0x48, b'\x12', read=1)
            assert result == Result('success', 2, b'\xa6')
            check_frames(h.samples[begin:], [0x55], 434)
            bus.check_timing()
            assert bus.bytes == [0x90, 0x12, 0x91]
        finally:
            bus.close()


@cocotb.test()
async def dual_all_shift_widths_simultaneous(dut):
    h = Host(dut)
    rng = random.Random(2202)
    for right in (False, True):
        for width in range(1, 33):
            await h.reset()
            values = [rng.getrandbits(32), rng.getrandbits(32)]
            widths = [width, 33-width]
            for e in range(2):
                await select(h, e)
                await h.write_word(SHIFT, 3 if right else 0)
                await h.write_word(TX, values[e])
                await h.load(f'pull block\nout x, {widths[e]}\nin x, {widths[e]}\npush block\nhalt')
            await h.write_word(GROUP, 3)
            await h.tick(8)
            for e in range(2):
                await select(h, e)
                count = widths[e]
                mask = (1 << count)-1
                extracted = (values[e] & mask) if right else values[e] >> (32-count)
                assert await h.read_word(X) == extracted
                assert await h.read_word(OSR) == (values[e] >> count if right else (values[e] << count) & 0xffffffff)
                assert await h.read_word(RX) == (extracted << (32-count) if right else extracted)
                assert not await h.read(STATUS) & 5


@cocotb.test()
async def dual_fault_group_priority_and_enable_freeze(dut):
    h = Host(dut)
    await h.reset()
    await setup(h, 0, [0xffff])  # Invalid SET destination.
    await setup(h, 1, 'set pins, 0\nset pins, 1', base=1)
    await h.write_word(EXEC, 1 << 5)
    await h.write_word(OWNER, 2)
    await h.write_word(GROUP, 3)
    await h.tick(4)
    await select(h, 0)
    assert await h.read(STATUS) & 5 == 4
    begin = len(h.samples)
    await h.tick(8)
    assert all((h.samples[i] ^ h.samples[i+1]) & 2 for i in range(begin, len(h.samples)-1))
    dut.ena.value = 0; h.control(0)
    frozen = h.samples[-1]
    await h.tick(9)
    assert h.samples[-9:] == [frozen]*9
    dut.ena.value = 1; await h.tick()
    assert h.samples[-1] ^ frozen == 2
    # RESUME cannot clear a fault; START does clear it, STOP takes priority.
    await h.write_word(GROUP, 1 << 4)
    assert await h.read(STATUS) & 5 == 4
    await h.load('pull block\nhalt')
    await h.write_word(0x17, 0xf00)
    await h.write_word(TX, 0xa5)
    # Faulted stopped engine: abort wins start/stop/resume; clear queue permitted.
    await h.write_word(GROUP, 1 | (1<<2) | (1<<4) | (1<<6) | (1<<8))
    assert await h.read_word(0x17) == 255
    assert await h.read(LEVEL) == 0
    assert await h.read(STATUS) & 5 == 4
    await h.write_word(GROUP, 1)
    assert await h.read(STATUS) & 5 == 1
    # Starting faulted peer never stopped the other engine.
    await select(h, 1)
    assert await h.read(STATUS) & 5 == 1
    await h.write_word(GROUP, (3 << 2) | (3 << 4))
    assert (await h.read_word(GLOBAL) & 0x0101) == 0


@cocotb.test()
async def dual_spi_uart_concurrent(dut):
    h = Host(dut)
    await h.reset()
    await h.write_word(OWNER, 1)  # UART1 on output0; SPI0 on outputs4,5,6.
    await select(h, 1)
    await h.write_word(PINCTRL, 8 | (1 << 11))  # UART completion also only output0.
    await h.write_word(DIVIDER, 31)
    await h.load((ROOT / 'examples/uart_v0.asm').read_text())
    await h.write_word(TX, 0xa6)
    await select(h, 0)
    await h.write_word(PINS, 1 << 6)
    await h.write_word(SHIFT, 0)
    await h.write_word(EXEC, 0x83e0)
    await h.write_word(PINCTRL, 4 | (1 << 3) | (6 << 8) | (1 << 11) | (5 << 17))
    await h.write_word(DIVIDER, 5)
    await h.load((ROOT / 'examples/spi_mode0.asm').read_text())
    await h.write_word(TX, 0x96000000)
    begin = len(h.samples)
    await h.write_word(GROUP, 3)
    rx_byte, pending = 0x3d, None
    previous = h.samples[-1]
    rises, falls, bits = [], [], []
    selected_at = released_at = None
    for cycle in range(5000):
        await h.tick()
        value = h.samples[-1]
        if pending is not None and cycle == pending[0]:
            h.inputs = pending[1]
            h.control(0)
            pending = None
        if (previous & 64) and not (value & 64):
            selected_at = cycle
            pending = (cycle+1, rx_byte >> 7)
        if not (previous & 64) and value & 64:
            released_at = cycle
        if (previous ^ value) & 32:
            assert not value & 64
            if value & 32:
                rises.append(cycle); bits.append((value >> 4) & 1)
            else:
                falls.append(cycle)
                if len(falls) < 8:
                    pending = (cycle+1, (rx_byte >> (7-len(falls))) & 1)
        previous = value
    assert bits == [(0x96 >> bit) & 1 for bit in range(7, -1, -1)]
    assert len(rises) == len(falls) == 8
    assert all(f-r == 40 for r, f in zip(rises, falls))
    assert all(rises[i+1]-falls[i] == 40 for i in range(7))
    assert rises[0]-selected_at == 40
    assert released_at-falls[-1] == 20
    assert await h.read_word(RX) == rx_byte
    check_frames(h.samples[begin:], [0xa6], 434)
