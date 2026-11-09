"""Autonomous feeder through the existing byte adapter and PIO package pins."""
import json
import os
from pathlib import Path

import cocotb
from cocotb.triggers import Timer

from pio_host import PIOHost
from streaming.usb_ls import inspect, symbols
from test import Host

ROOT = Path(__file__).resolve().parents[1]
BEGIN, WORD, COMMIT, LAUNCH, ABORT, RELEASE = range(6)
FREE, FILL, READY, ACTIVE, COMPLETE = range(5)


class FeederFixture:
    def __init__(self, dut):
        self.dut = dut
        self.host = Host(dut)
        self.engine = PIOHost(self.host).engine(0)

    async def reset(self):
        self.dut.cmd_valid.value = 0
        self.dut.cmd.value = 0
        self.dut.cmd_data.value = 0
        self.dut.cmd_length_minus_one.value = 0
        self.dut.ena.value = 1
        self.dut.rst_n.value = 0
        self.host.control(0)
        self.dut.uio_in.value = 0
        # Gate-level outputs may be unknown while reset propagates. The first
        # scored sample is after reset has had three clocks to settle.
        for _ in range(3):
            self.dut.clk.value = 0
            await Timer(10, unit='ns')
            self.dut.clk.value = 1
            await Timer(10, unit='ns')
        self.dut.rst_n.value = 1
        await self.host.tick()
        assert self.host.samples[-1] == 1
        assert int(self.dut.uio_oe.value) == 0
        assert int(self.dut.slot_state.value) == FREE

    async def configure(self, program=None):
        if program is None:
            program = (ROOT / 'examples/usb_ls_tx_symbols.asm').read_text()
        async with self.engine.transaction():
            await self.host.load(program)
        for selector, value in ((4, 2), (0x10, 3), (0x11, 0x83e0), (0x12, 0x40010), (0x13, 1)):
            await self.engine.write_word(selector, value)

    async def command(self, op, data=0, length=0, accepted=True):
        self.dut.cmd.value = op
        self.dut.cmd_data.value = data
        self.dut.cmd_length_minus_one.value = length
        self.dut.cmd_valid.value = 1
        await Timer(1, unit='ns')
        assert bool(self.dut.cmd_ready.value) == accepted
        await self.host.tick()
        self.dut.cmd_valid.value = 0
        await Timer(1, unit='ns')

    async def submit(self, words, sequence):
        await self.command(BEGIN, sequence, words[0])
        for word in words[1:]:
            await self.command(WORD, word)
        await self.command(COMMIT)

    async def complete(self, timeout=6000):
        commits = []
        previous = int(self.dut.words_sent.value)
        for _ in range(timeout):
            if int(self.dut.slot_state.value) == COMPLETE:
                return commits
            assert not self.dut.cmd_valid.value, 'PC must stay silent during execution'
            await self.host.tick()
            count = int(self.dut.words_sent.value)
            if count != previous:
                assert count == previous + 1
                commits.append(len(self.host.samples))
                previous = count
        raise AssertionError('autonomous packet did not complete')


@cocotb.test()
async def autonomous_usb_waveforms(dut):
    f = FeederFixture(dut)
    await f.reset()
    await f.configure()
    rows = []
    cases = ((b'', False), (bytes(range(8)), True), (bytes([255]) * 8, False), (b'\xff', True))
    for sequence, (payload, data1) in enumerate(cases):
        words, expected = symbols(payload, data1=data1)
        await f.submit(words, sequence)
        begin = len(f.host.samples)
        await f.command(LAUNCH)
        commits = await f.complete()
        assert int(dut.result.value) == 0
        assert int(dut.completion_sequence.value) == sequence
        assert int(dut.words_sent.value) == len(words) == len(commits)
        assert int(dut.terminal_levels.value) == int(dut.terminal_errors.value) == 0
        assert int(dut.terminal_status.value) & 5 == 0
        observed = inspect(f.host.samples[begin:])
        for key in ('payload_hex', 'data1', 'symbols', 'total_clocks'):
            assert observed[key] == expected[key]
        rows.append(dict(observed, sequence=sequence, words=len(words), pc_requests_after_launch=0,
                         launch_to_completion_clocks=len(f.host.samples) - begin,
                         max_intercommit_clocks=max(b - a for a, b in zip(commits, commits[1:]))))
        await f.command(RELEASE)
    Path(os.environ['STREAM_RESULTS']).write_text(json.dumps(rows, indent=2) + '\n')


@cocotb.test()
async def upload_ownership_and_capacity(dut):
    f = FeederFixture(dut)
    await f.reset()
    await f.command(BEGIN, length=116, accepted=False)
    await f.command(BEGIN, data=0x5678, length=115)
    assert int(dut.slot_state.value) == FILL
    await f.command(LAUNCH, accepted=False)
    for word in range(28):
        await f.command(WORD, word)
    await f.command(COMMIT, accepted=False)
    await f.command(WORD, 28)
    await f.command(WORD, 29, accepted=False)
    await f.command(COMMIT)
    assert int(dut.slot_state.value) == READY
    await f.command(BEGIN, accepted=False)
    await f.command(WORD, 0, accepted=False)
    await f.host.tick(20)
    assert int(dut.bus_request.value) == 0
    await f.command(ABORT)
    assert int(dut.slot_state.value) == FREE
    await f.command(LAUNCH, accepted=False)


@cocotb.test()
async def abort_and_shared_reset(dut):
    f = FeederFixture(dut)
    await f.reset()
    await f.configure()
    words, _ = symbols(bytes([255]) * 8)
    await f.submit(words, 10)
    # An immediate abort must select engine 0 before cleanup.
    await f.host.write(15, 1)
    await f.host.write_word(8, 0x13579bdf)
    await f.command(LAUNCH)
    await f.command(ABORT)
    await f.complete()
    assert int(dut.result.value) == 1
    assert int(dut.words_sent.value) == 0
    assert await PIOHost(f.host).engine(1).read(11) == 1
    await f.command(RELEASE)

    await f.submit(words, 11)
    await f.command(LAUNCH)
    for _ in range(500):
        if int(dut.bus_request.value) == 0x1a and int(dut.words_sent.value) == 4:
            break
        await f.host.tick()
    else:
        raise AssertionError('no in-flight fifth FIFO word commit')
    await f.command(LAUNCH, accepted=False)
    await f.command(ABORT)
    await f.complete()
    assert int(dut.result.value) == 1
    assert int(dut.words_sent.value) == 5
    assert await f.engine.read(11) == 0
    assert not (await f.engine.read(1)) & 1
    await f.command(RELEASE)

    await f.submit(words, 12)
    await f.command(LAUNCH)
    for _ in range(40):
        if int(dut.control.value) & 0x30:
            break
        await f.host.tick()
    else:
        raise AssertionError('no in-flight nibble at reset')
    assert int(dut.slot_state.value) == ACTIVE
    await f.reset()
    assert int(dut.completion_sequence.value) == int(dut.bus_request.value) == 0
    assert await f.engine.read(11) == 0
    await f.command(LAUNCH, accepted=False)
    await f.configure()
    await f.submit(words, 13)
    await f.command(LAUNCH)
    await f.complete()
    assert int(dut.result.value) == 0


@cocotb.test()
async def early_halt_is_error(dut):
    f = FeederFixture(dut)
    await f.reset()
    await f.configure('halt')
    words, _ = symbols(bytes([255]) * 8)
    await f.submit(words, 9)
    await f.command(LAUNCH)
    await f.complete()
    assert int(dut.result.value) == 2
    assert int(dut.terminal_levels.value) == 4
    assert int(dut.words_sent.value) == 4
    assert await f.engine.read(11) == 0


@cocotb.test()
async def complete_with_all_words_prefilled(dut):
    f = FeederFixture(dut)
    await f.reset()
    await f.configure('pull block\npull block\nhalt')
    await f.submit([0, 0x15], 20)
    await f.command(LAUNCH)
    await f.complete()
    assert int(dut.result.value) == 0
    assert int(dut.words_sent.value) == 2
    assert int(dut.terminal_levels.value) == 0
