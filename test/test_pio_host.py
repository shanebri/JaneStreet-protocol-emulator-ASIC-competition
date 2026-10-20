"""Host lock tests with real asyncio contention and injected transport errors."""
import asyncio
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from pio_host import PIOHost


class YieldingBus:
    def __init__(self):
        self.selected = 0
        self.trace = []
        self.raise_read = False

    async def write(self, address, value):
        await asyncio.sleep(0)
        if address == 15:
            self.selected = value
        self.trace.append((self.selected, address, value))

    async def read(self, address):
        await asyncio.sleep(0)
        if self.raise_read:
            raise TimeoutError('transport timeout')
        self.trace.append((self.selected, address, None))
        return [0x78, 0x56, 0x34, 0x12][(6, 7, 9, 10).index(address)]


class HostTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_words_and_same_engine_clients(self):
        bus = YieldingBus()
        host = PIOHost(bus)
        await asyncio.gather(host.engine(0).write_word(8, 0xaabbccdd),
                             host.engine(1).write_word(8, 0x12345678),
                             host.engine(0).write_word(0, 0x11223344))
        for offset, (engine, selector, value) in enumerate(((0, 8, 0xaabbccdd),
                                                          (1, 8, 0x12345678),
                                                          (0, 0, 0x11223344))):
            trace = bus.trace[offset*6:(offset+1)*6]
            self.assertEqual(trace[:2], [(engine, 15, engine), (engine, 5, selector)])
            self.assertEqual(trace[2:], [(engine, a, (value >> (8*i)) & 255)
                                         for i, a in enumerate((6, 7, 9, 10))])
        self.assertEqual(await host.engine(1).read_word(9), 0x12345678)

    async def test_exception_and_cancel_release_lock(self):
        bus = YieldingBus()
        host = PIOHost(bus)
        bus.raise_read = True
        with self.assertRaises(TimeoutError):
            await host.engine(0).read_word(9)
        self.assertFalse(host.lock.locked())
        bus.raise_read = False
        entered = asyncio.Event()
        async def hold():
            async with host.engine(0).transaction():
                entered.set()
                await asyncio.Event().wait()
        task = asyncio.create_task(hold())
        await entered.wait()
        pending = asyncio.create_task(host.engine(1).write_word(8, 5))
        await asyncio.sleep(0)
        self.assertFalse(pending.done())
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(pending, timeout=1)
        self.assertFalse(host.lock.locked())

    async def test_argument_validation(self):
        host = PIOHost(YieldingBus())
        for index in (-1, 2, 255):
            with self.assertRaises(ValueError):
                host.engine(index)
        for value in (-1, 1 << 32):
            with self.assertRaises(ValueError):
                await host.engine(0).write_word(8, value)


if __name__ == '__main__':
    unittest.main()
