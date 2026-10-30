"""Shared async scenarios, using only public host registers and package pins."""
import random
from pio_host import PIOHost, DUAL_CAPABILITIES, CAPABILITIES, SELECTED_ENGINE
from pioasm import assemble


def equal(actual, expected, context):
    if actual != expected:
        raise AssertionError(f'{context}: expected {expected:#x}, got {actual:#x}')


async def load(engine, program):
    words = assemble(program) if isinstance(program, str) else program
    if len(words) > 32:
        raise ValueError('program exceeds instruction memory')
    async with engine.transaction() as bus:
        await bus.write(2, 0)
        for word in words:
            await bus.write(3, word & 255)
            await bus.write(4, word >> 8)


async def finished(engine):
    for _ in range(100):
        status = await engine.read(1)
        if status & 4:
            raise AssertionError('PIO instruction fault')
        if not status & 1:
            return
    raise TimeoutError('PIO did not halt within 100 polls')


async def discovery(io, seed):
    host = PIOHost(io)
    for i in range(2):
        engine = host.engine(i)
        equal(await engine.read(15), 0x21, 'VERSION')
        equal(await engine.read_word(CAPABILITIES), DUAL_CAPABILITIES, 'CAPABILITIES')
        equal(await engine.read_word(SELECTED_ENGINE), i, 'engine selection')
        equal(await engine.read(11), 0, 'empty FIFOs')


async def banks(io, seed):
    host, rng = PIOHost(io), random.Random(seed)
    for _ in range(8):
        values = [rng.getrandbits(32), rng.getrandbits(32)]
        for i in range(2):
            await host.engine(i).write_word(0, values[i])
        for i in range(2):
            equal(await host.engine(i).read_word(0), values[i], f'engine {i} X isolation')
    # Interleave incomplete word commits across banks.
    for i in range(2):
        await io.write(15, i)
        await io.write(5, 1)
        for reg, byte in ((6, 0x11+i), (7, 0x22), (9, 0x33)):
            await io.write(reg, byte)
        equal(await host.engine(i).read_word(1), 0, 'partial Y must not commit')
    for i in (1, 0):
        await io.write(15, i)
        await io.write(10, 0x44)
        equal(await host.engine(i).read_word(1), 0x44332211+i, 'banked staged commit')


async def instruction_memory(io, seed):
    host, rng = PIOHost(io), random.Random(seed)
    expected = [[rng.randrange(65536) for _ in range(32)] for _ in range(2)]
    for i in range(2):
        await load(host.engine(i), expected[i])
    for i in range(2):
        async with host.engine(i).transaction() as bus:
            for address, word in enumerate(expected[i]):
                await bus.write(2, address)
                actual = await bus.read(3) | (await bus.read(4) << 8)
                equal(actual, word, f'engine {i} instruction {address}')


async def fifo_execution(io, seed):
    host, rng = PIOHost(io), random.Random(seed)
    values = [[rng.getrandbits(32) for _ in range(4)] for _ in range(2)]
    for i in range(2):
        e = host.engine(i)
        await load(e, 'pull block\nmov isr, osr\npush block\nhalt')
        for word in values[i]:
            await e.write_word(8, word)
        equal(await e.read(11), 4, 'four TX words queued')
    for n in range(4):
        # Group-start both engines, then consume and compare their independent RXs.
        await host.engine(0).write_word(0x1c, 3)
        for i in range(2):
            e = host.engine(i)
            await finished(e)
            equal((await e.read(11) >> 4) & 7, 1, 'one RX word')
            equal(await e.read_word(9), values[i][n], f'engine {i} FIFO word {n}')
            equal(await e.read(11), 3-n, 'remaining FIFO level')


async def recovery(io, seed):
    host = PIOHost(io)
    await load(host.engine(0), 'pull block\nhalt')
    await host.engine(0).write(0, 1)
    await io.wait(16)
    if not await host.engine(0).read(1) & 1:
        raise AssertionError('empty TX should block')
    await io.enable(False)
    await io.wait(8)
    await io.enable(True)
    await io.wait(2)
    await host.engine(0).write_word(8, 0x12345678)
    await finished(host.engine(0))
    await io.reset()
    await discovery(io, seed)


async def gpio_ownership(io, seed):
    host=PIOHost(io)
    for bit in range(8):
        value=1<<bit
        await host.engine(0).write_word(4,value)
        await host.engine(1).write_word(4,value^255)
        equal(await io.sample(),value,'engine 0 dedicated outputs')
        await host.engine(0).write_word(0x1b,255)
        equal(await io.sample(),value^255,'engine 1 ownership')
        await host.engine(0).write_word(0x1b,0)
        equal(await io.sample(),value,'ownership restored')


SCENARIOS = [discovery, banks, instruction_memory, fifo_execution, recovery, gpio_ownership]


async def run(io, seed, emit):
    """Fresh state per case. Stop at first failure; no retries or hidden skips."""
    for scenario in SCENARIOS:
        await io.reset()
        try:
            await scenario(io, seed)
        except Exception as exc:
            emit(dict(test=scenario.__name__, status='FAIL', error=str(exc)))
            raise
        emit(dict(test=scenario.__name__, status='PASS'))
