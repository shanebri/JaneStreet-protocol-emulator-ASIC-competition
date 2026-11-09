"""Upload complete USB symbol scripts and launch autonomous FPGA slots."""
import asyncio
import time
from bringup.scenarios import load
from pio_host import PIOHost
from streaming.usb_ls import symbols

INFO, SEQ_LOW, SEQ_HIGH, BEGIN, WORD_LOW, WORD_HIGH, COMMIT, LAUNCH, ABORT, RELEASE, STATUS, LAUNCH_BOTH = range(15, 27)
FREE, FILL, READY, ACTIVE, COMPLETE = range(5)


async def configure(io, engine, program=None):
    """Configure disjoint three-output logical line/marker groups."""
    from pathlib import Path
    if engine not in (0, 1):
        raise ValueError('engine must be 0 or 1')
    host = PIOHost(io)
    target = host.engine(engine)
    if program is None:
        program = (Path(__file__).resolve().parents[2]/'examples/usb_ls_tx_symbols.asm').read_text()
    await target.write(0, 0x2e)
    await load(target, program)
    await target.write_word(0x1b, 0x38)
    base = engine*3
    for selector, value in ((4, 2 << base), (0x10, 3), (0x11, 0x83e0),
                            (0x12, base | (2 << 3) | ((base+2) << 17)), (0x13, 1)):
        await target.write_word(selector, value)


class Feeder:
    def __init__(self, io):
        self.io = io
        self.lock = asyncio.Lock()

    async def identify(self):
        info = await self.io.command(INFO)
        if info != bytes((1, 2, 29, 3)):
            raise ValueError('expected two-slot autonomous feeder protocol version 1')
        return info

    async def status(self, slot):
        if slot not in (0, 1):
            raise ValueError('slot must be 0 or 1')
        word = int.from_bytes(await self.io.command(STATUS, slot), 'little')
        return dict(state=word & 7, result=(word >> 3) & 3, engine=(word >> 5) & 1)

    async def submit(self, slot, engine, payload, *, sequence, data1=False):
        if slot not in (0, 1) or engine not in (0, 1) or not 0 <= sequence < 1 << 32:
            raise ValueError('invalid slot, engine or sequence')
        words, expected = symbols(payload, data1=data1)
        if not 1 <= expected['symbols'] <= 116:
            raise ValueError('script exceeds one command slot')
        async with self.lock:
            await self.io.command(SEQ_LOW, slot, sequence & 0xffff)
            await self.io.command(SEQ_HIGH, slot, sequence >> 16)
            await self.io.command(BEGIN, slot | (engine << 1), words[0])
            for word in words[1:]:
                await self.io.command(WORD_LOW, slot, word & 0xffff)
                await self.io.command(WORD_HIGH, slot, word >> 16)
            await self.io.command(COMMIT, slot)
        return expected

    async def launch(self, slot=None):
        if slot is None:
            await self.io.command(LAUNCH_BOTH)
        elif slot in (0, 1):
            await self.io.command(LAUNCH, slot)
        else:
            raise ValueError('slot must be 0, 1 or None for both')

    async def completion(self, slot, *, sequence, timeout=2):
        if timeout <= 0:
            raise ValueError('positive completion timeout required')
        clock = getattr(self.io, 'clock', time.monotonic)
        deadline = clock()+timeout
        while clock() < deadline:
            status = await self.status(slot)
            if status['state'] == COMPLETE:
                observed = int.from_bytes(await self.io.command(STATUS, slot | 2), 'little')
                terminal = int.from_bytes(await self.io.command(STATUS, slot | 4), 'little')
                if observed != sequence:
                    raise ValueError('completion sequence differs from the submitted packet')
                return dict(status, sequence=observed, words_sent=terminal & 63,
                            terminal_status=(terminal >> 6) & 255,
                            terminal_levels=(terminal >> 14) & 255,
                            terminal_errors=(terminal >> 22) & 255)
            if status['state'] != ACTIVE:
                raise ValueError('slot is not executing or complete')
        raise TimeoutError('completion polling deadline; inspect slot state before recovery')

    async def abort(self, slot):
        if slot not in (0, 1):
            raise ValueError('slot must be 0 or 1')
        await self.io.command(ABORT, slot)

    async def release(self, slot):
        if slot not in (0, 1):
            raise ValueError('slot must be 0 or 1')
        await self.io.command(RELEASE, slot)
