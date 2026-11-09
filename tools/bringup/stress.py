"""Deterministic public-interface stress and recovery on the unmodified ASIC."""
import random
import time
from pioasm import assemble
from pio_host import DATA_ADDR, DATA_BYTES, PIOHost, GROUP_START_BOTH
from bringup.scenarios import load

ECHO = 'pull block\nmov isr, osr\npush block\njmp 0'
MARKER = 'mov x, ~null\nloop: mov pins, x\njmp x--, loop\njmp loop'


def check(emit, name, actual, expected, **context):
    passed = actual == expected
    emit(dict(test=name, type='assertion', status='PASS' if passed else 'FAIL', expected=expected,
              observed=actual, **context))
    if not passed:
        raise AssertionError(f'{name}: expected {expected!r}, observed {actual!r}')


async def word_read(bus, selector):
    await bus.write(5, selector)
    return sum([(await bus.read(address)) << (8*i) for i, address in enumerate((6, 7, 9, 10))])


async def levels(engine):
    value = await engine.read(11)
    return value & 7, (value >> 4) & 7


async def until_levels(io, engine, expected, polls=200):
    for _ in range(polls):
        actual = await levels(engine)
        if actual == expected:
            return actual
        if await engine.read(1) & 4:
            raise AssertionError('engine fault while waiting for FIFO state')
        await io.wait(64)
    raise TimeoutError(f'engine {engine.index} FIFO state {actual}, expected {expected}')


async def prepare_echo(io, emit, seed):
    await io.reset()
    host = PIOHost(io)
    words = assemble(ECHO)
    emit(dict(test='echo_firmware', type='firmware', seed=seed, assembly=ECHO, words=words))
    for index in (0, 1):
        await load(host.engine(index), words)
    return host


def tagged_word(rng, engine, sequence):
    return (engine << 31) | ((sequence & 0x7fff) << 16) | rng.getrandbits(16)


async def dual_engine_stress(io, seed, emit, *, rounds=64, duration_seconds=0, recorder=None, **unused):
    if rounds < 1 or duration_seconds < 0:
        raise ValueError('stress rounds must be positive and duration nonnegative')
    await io.require_v2()
    await io.reset()
    host, rng = PIOHost(io), random.Random(seed)
    emit(dict(test='marker_firmware', type='firmware', assembly=MARKER, words=assemble(MARKER), seed=seed))
    await host.engine(0).write_word(0x1b, 0xf0)
    for index, divider in enumerate((257, 389)):
        engine = host.engine(index)
        await load(engine, MARKER)
        await engine.write_word(0x12, 0x20 | (4*index))
        await engine.write_word(0x13, divider)
    if recorder:
        # At 50 MHz, 8192 samples cover about 42 ms, long enough to see
        # the next host access on USB serial without losing marker edges.
        await recorder.arm('dual-markers', channel='out0', decimation=8,
                           expected=dict(kind='markers', seed=seed, masks=[15, 240]))
    await host.engine(0).write_word(0x1c, 3)
    previous = [await host.engine(i).read_word(0) for i in (0, 1)]
    # Unlike short smoke firmware, these programs keep executing throughout
    # bank selection, coherent snapshots, FIFO writes and IMEM readback.
    for iteration in range(8):
        await io.wait(6224)
        order = [0, 1]; rng.shuffle(order)
        for index in order:
            engine = host.engine(index)
            await engine.write_word(1, rng.getrandbits(32))  # protected while running
            check(emit, 'running_config_protection', await engine.read_word(1), 0,
                  engine=index, iteration=iteration)
            now = await engine.read_word(0)
            delta = (previous[index]-now) & 0xffffffff
            check(emit, 'continued_engine_progress', 0 < delta < 0x80000000, True,
                  engine=index, iteration=iteration, before=previous[index], after=now, decrements=delta)
            previous[index] = now
            check(emit, 'marker_running_no_fault', (await engine.read(1)) & 5, 1, engine=index)
    if recorder:
        await recorder.finish()
    await host.engine(0).write(0, 2)
    await host.engine(1).write(0, 2)
    host = await prepare_echo(io, emit, seed)
    payload_rng, scheduling_rng = random.Random(seed ^ 0xd0a1e), random.Random(seed ^ 0x5ced)
    await host.engine(0).write_word(0x1c, 3)
    clock = getattr(io, 'clock', time.monotonic)
    started = clock()
    deadline = started+duration_seconds
    sequence = 0
    while sequence < rounds or clock() < deadline:
        expected = [tagged_word(payload_rng, i, sequence) for i in (0, 1)]
        emit(dict(test='dual_word', type='intent', seed=seed, sequence=sequence, expected=expected))
        order = [0, 1]; scheduling_rng.shuffle(order)
        for index in order:
            await host.engine(index).write_word(8, expected[index])
        observed = [None, None]
        for index in reversed(order):
            engine = host.engine(index)
            await until_levels(io, engine, (0, 1))
            observed[index] = await engine.read_word(9)
            check(emit, 'fifo_order_and_bank_isolation', observed[index], expected[index],
                  engine=index, sequence=sequence, seed=seed)
            check(emit, 'empty_after_drain', list(await levels(engine)), [0, 0], engine=index)
            check(emit, 'no_unexpected_fifo_flags', await engine.read(13), 0, engine=index)
        emit(dict(test='dual_word', status='PASS', seed=seed, sequence=sequence,
                  expected=expected, observed=observed))
        sequence += 1
    await host.engine(0).write(0, 2)
    await host.engine(1).write(0, 2)
    emit(dict(test='dual_engine_stress', status='PASS', seed=seed, rounds=sequence,
              words_per_engine=sequence, marker_observations=16, elapsed_seconds=clock()-started))


async def saturate(io, host, emit, rng):
    expected = [[tagged_word(rng, index, n) for n in range(9)] for index in (0, 1)]
    for index in (0, 1):
        for word in expected[index][:4]:
            await host.engine(index).write_word(8, word)
    await host.engine(0).write_word(0x1c, 3)
    for index in (0, 1):
        engine = host.engine(index)
        await until_levels(io, engine, (0, 4))
        await engine.write_word(8, expected[index][4])
        await until_levels(io, engine, (0, 4))
        # The fifth echo is now held at PUSH, with RX full. Four further TX
        # words fill the independent input FIFO behind that blocked operation.
        for word in expected[index][5:]:
            await engine.write_word(8, word)
        await until_levels(io, engine, (4, 4))
        check(emit, 'full_backpressure_stall', (await engine.read(1)) & 7, 3, engine=index)
    return expected


async def drain_expected(io, host, emit, expected, label):
    for sequence in range(len(expected[0])):
        for index in (1, 0):
            engine = host.engine(index)
            for _ in range(200):
                if (await levels(engine))[1]:
                    break
                await io.wait(64)
            else:
                raise TimeoutError('expected RX data did not arrive')
            check(emit, label, await engine.read_word(9), expected[index][sequence],
                  engine=index, sequence=sequence)
    for index in (0, 1):
        await until_levels(io, host.engine(index), (0, 0))


async def boundaries(io, seed, emit, **unused):
    await io.require_v2()
    host = await prepare_echo(io, emit, seed)
    rng = random.Random(seed)
    expected = await saturate(io, host, emit, rng)
    for index in (0, 1):
        engine = host.engine(index)
        await engine.write_word(8, 0xdead0000 | index)
        check(emit, 'overflow_flag', (await engine.read(13)) & 1, 1, engine=index)
        check(emit, 'overflow_did_not_change_levels', list(await levels(engine)), [4, 4], engine=index)
    await drain_expected(io, host, emit, expected, 'backpressure_order')
    for index in (0, 1):
        engine = host.engine(index)
        check(emit, 'empty_rx_value', await engine.read_word(9), 0, engine=index)
        check(emit, 'underflow_flag', (await engine.read(13)) & 3, 3, engine=index)
        await engine.write(0, 8)
        check(emit, 'clear_fifo_flags', await engine.read(13), 0, engine=index)
        check(emit, 'tx_starvation_stall', (await engine.read(1)) & 7, 3, engine=index)
        check(emit, 'tx_starvation_pc', await engine.read(8), 0, engine=index)
    refill = [[tagged_word(rng, index, n+100) for n in range(3)] for index in (0, 1)]
    for n in range(3):
        for index in (0, 1):
            await host.engine(index).write_word(8, refill[index][n])
    await drain_expected(io, host, emit, refill, 'refill_after_starvation')
    for index in (0, 1):
        await host.engine(index).write(0, 2)
    emit(dict(test='boundaries', status='PASS', seed=seed, expected=expected, refill=refill))


async def recovery(io, seed, emit, *, recorder=None, **unused):
    await io.require_v2()
    host = await prepare_echo(io, emit, seed)
    rng = random.Random(seed)
    # Drive pad0 low before running. Disable is a freeze and retains this drive;
    # reset/ABORT are the operations whose contract releases the protocol pads.
    await host.engine(0).write_word(4, 0)
    await host.engine(0).write_word(0x17, 0x100)
    expected = await saturate(io, host, emit, rng)
    e = host.engine(0)
    stage = rng.getrandbits(24)
    async with e.transaction() as bus:
        await bus.write(5, 1)
        for address, shift in ((6, 0), (7, 8), (9, 16)):
            await bus.write(address, (stage >> shift) & 255)
    await io.raw_beat(6, 5)
    if recorder:
        await recorder.arm('disable-freeze', channel='enabled', decimation=8,
                           expected=dict(kind='freeze', pad=0, drive_retained=True))
    await io.enable(False)
    check(emit, 'disable_retains_pad_drive', (await io.sample_pads())['oe'] & 1, 1)
    await io.wait(128)
    await io.enable(True)
    await io.raw_beat(6, 10)
    await io.raw_beat(6, strobes=3)  # discard the new first nibble, not a byte commit
    for index in (0, 1):
        check(emit, 'disable_preserves_full_fifos', list(await levels(host.engine(index))), [4, 4], engine=index)
    await drain_expected(io, host, emit, expected, 'disable_preserved_order')
    for index in (0, 1):
        await host.engine(index).write(0, 2)
    await e.write(5, 1)
    await e.write(10, 0x44)
    check(emit, 'partial_byte_discard_and_word_stage_retention', await e.read_word(1), (0x44 << 24) | stage)
    if recorder:
        await recorder.finish()
    # Establish that raw beats really span packet boundaries before testing reset.
    await e.write(5, 1)
    await io.raw_beat(6, 11)
    await io.raw_beat(6, 10)
    await e.write(10, 0x55)
    check(emit, 'raw_two_nibble_control', (await e.read_word(1)) & 255, 0xab)
    # Reset while both engines have live, full FIFO state and a partial host byte.
    host = await prepare_echo(io, emit, seed)
    await host.engine(0).write_word(4, 0)
    await host.engine(0).write_word(0x17, 0x100)
    await saturate(io, host, emit, rng)
    await host.engine(0).write(5, 1)
    await io.raw_beat(6, 3)
    if recorder:
        await recorder.arm('reset-release', channel='rst_n', decimation=8,
                           expected=dict(kind='reset', pad=0, releases=True))
    await io.reset()
    check(emit, 'reset_releases_pad_logic', (await io.sample_pads())['oe'], 0)
    check(emit, 'reset_selects_engine0', await word_read(io, 0x1e), 0)
    await io.write(5, 1)
    await io.raw_beat(6, 12)
    await io.raw_beat(6, strobes=3)
    await io.write(10, 0x66)
    check(emit, 'reset_clears_partial_byte_and_stage', await word_read(io, 1), 0x66000000)
    for index in (0, 1):
        engine = host.engine(index)
        check(emit, 'reset_fifo_levels', list(await levels(engine)), [0, 0], engine=index)
        check(emit, 'reset_error_flags', await engine.read(13), 0, engine=index)
        check(emit, 'reset_directions', await engine.read_word(0x17), 0xff, engine=index)
        async with engine.transaction() as bus:
            for address, word in enumerate(assemble(ECHO)):
                await bus.write(2, address)
                observed = await bus.read(3) | ((await bus.read(4)) << 8)
                check(emit, 'reset_imem_retention', observed, word, engine=index, address=address)
    if recorder:
        await recorder.finish()
    refill = [[tagged_word(rng, index, 200)] for index in (0, 1)]
    for index in (0, 1):
        await host.engine(index).write_word(8, refill[index][0])
    await host.engine(0).write_word(0x1c, 3)
    await drain_expected(io, host, emit, refill, 'restart_after_reset')
    await host.engine(0).write(0, 0x20)
    await host.engine(1).write(0, 0x20)
    check(emit, 'abort_releases_pad_logic', (await io.sample_pads())['oe'], 0)
    await partial_read_recovery(io, seed, emit)
    emit(dict(test='recovery', status='PASS', seed=seed,
              disable_contract='freeze including retained protocol drive; host partial byte discarded',
              reset_contract='architectural/FIFO clear, IMEM retention and protocol drive release'))


async def partial_read_recovery(io, seed, emit):
    # DATA_0 accepts/pops on its FIRST read nibble. Disable discards the
    # adapter's saved high nibble; it must not roll that FIFO pop back.
    host = await prepare_echo(io, emit, seed)
    expected = [[0x1234562a, 0x56789ac7, 0x23456785],
                [0x92345631, 0xb6789ad8, 0xc3456796]]
    for index in (0, 1):
        for word in expected[index]:
            await host.engine(index).write_word(8, word)
    await host.engine(0).write_word(0x1c, GROUP_START_BOTH)
    await io.wait(512)
    e = host.engine(0)
    await e.write(5, 9)
    low = await io.raw_beat(6, strobes=2)
    check(emit, 'partial_read_accepts_first_word', low, expected[0][0] & 15)
    await io.enable(False)
    await io.enable(True)
    low = await io.raw_beat(6, strobes=2)
    high = await io.raw_beat(6, strobes=2)
    await io.raw_beat(6, strobes=3)
    snapshot = low | (high << 4)
    for address, shift in ((7, 8), (9, 16), (10, 24)):
        snapshot |= (await e.read(address)) << shift
    check(emit, 'disable_discards_read_half_without_undoing_first_pop', snapshot, expected[0][1])
    check(emit, 'read_high_half_does_not_pop_twice', list(await levels(e)), [0, 1])
    check(emit, 'partial_read_remaining_word', await e.read_word(9), expected[0][2])
    for word in expected[1]:
        check(emit, 'partial_read_other_bank_preserved', await host.engine(1).read_word(9), word)
    # A reset after another accepted first read clears the bank snapshot and
    # host read context, as well as the remaining live FIFO state.
    await e.write_word(8, 0x6d4c2b1a)
    await io.wait(512)
    await e.write(5, 9)
    check(emit, 'pre_reset_partial_read', await io.raw_beat(6, strobes=2), 10)
    await io.reset()
    check(emit, 'reset_clears_read_snapshot', await io.read(7), 0)
    for index in (0, 1):
        check(emit, 'partial_read_reset_fifo_levels', list(await levels(host.engine(index))), [0, 0], engine=index)


async def pads(io, seed, emit, *, fixture, recorder=None, **unused):
    await io.require_v2()
    config = fixture.get('pads', {})
    if (config.get('pullups_confirmed') is not True or config.get('active_peers_disconnected') is not True
            or fixture.get('capture', {}).get('loopbacks')):
        raise ValueError('pads suite requires confirmed external 3.3 V pullups, disconnected active peers, and removed output loopbacks')
    await io.reset()
    host = PIOHost(io)
    for index in (0, 1):
        await host.engine(index).write_word(0x17, 0)
    for owner in (0, 1):
        await host.engine(0).write_word(0x1b, 0xf00 if owner else 0)
        check(emit, 'pad_owner_readback', await host.engine(0).read_word(0x1b), 0xf00 if owner else 0)
        engine = host.engine(owner)
        await engine.write_word(0x18, 0xf00)
        await engine.write_word(4, 0xf00)
        await engine.write_word(0x17, 0xf00)
        for bit in range(4):
            await engine.write_word(4, (15 ^ (1 << bit)) << 8)
            sample = await io.sample_pads()
            check(emit, 'open_drain_low', sample, dict(inputs=15 ^ (1 << bit), oe=1 << bit), owner=owner, pad=bit)
            # Ownership cannot change while either engine still declares drive.
            await host.engine(0).write_word(0x1b, 0 if owner else 0xf00)
            check(emit, 'reject_driven_ownership_transfer', await engine.read_word(0x1b), 0xf00 if owner else 0)
            # Stage the release before arming. Only the final byte commits it,
            # so the capture window need only cover one serial command.
            release = (0xf00).to_bytes(4, 'little')
            async with engine.transaction() as bus:
                await bus.write(DATA_ADDR, 4)
                for address, value in zip(DATA_BYTES[:-1], release[:-1]):
                    await bus.write(address, value)
                if recorder:
                    await recorder.arm(f'open-drain-{owner}-{bit}', channel=f'pad{bit}', immediate=True,
                                       decimation=8, expected=dict(kind='open_drain', pad=bit, owner=owner))
                await bus.write(DATA_BYTES[-1], release[-1])
            check(emit, 'open_drain_release_with_pullup', await io.sample_pads(), dict(inputs=15, oe=0), owner=owner, pad=bit)
            if recorder:
                await recorder.finish()
        await engine.write_word(0x17, 0)
    # A reset after driven-low output must release all four pads to the fixture pulls.
    await host.engine(1).write_word(4, 0)
    await host.engine(1).write_word(0x17, 0xf00)
    if recorder:
        await recorder.arm('pads-reset-release', channel='rst_n', decimation=8,
                           expected=dict(kind='reset', pad=0, releases=True))
    await io.reset()
    check(emit, 'reset_release_with_external_pullups', await io.sample_pads(), dict(inputs=15, oe=0))
    if recorder:
        await recorder.finish()
    emit(dict(test='pads', status='PASS', seed=seed,
              scope='digital input levels with declared pulls and logical OE; analog impedance/rise time unmeasured'))
