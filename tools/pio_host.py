"""Serialize dual-PIO engine selection and host transactions.

EngineTransport implements the existing async read/write byte transport, so it
can be passed directly to I2C. Different engine clients can interleave bytes:
the hardware banks selectors, write staging and snapshots. For clients sharing
one engine, hold transaction() over the complete logical operation. All clients
must use the same PIOHost instance (or share its lock); raw bus access bypasses
serialization. The underlying transport remains responsible for bounded I/O.
"""
import asyncio
from contextlib import asynccontextmanager

SM_SELECT = 15
DATA_ADDR = 5
DATA_BYTES = (6, 7, 9, 10)
CAPABILITIES = 0x1a
GPIO_OWNER = 0x1b
GROUP_CONTROL = 0x1c
GLOBAL_STATUS = 0x1d
SELECTED_ENGINE = 0x1e
DUAL_CAPABILITIES = 0x50490102


class PIOHost:
    def __init__(self, transport, *, lock=None):
        self.transport = transport
        self.lock = lock if lock is not None else asyncio.Lock()

    def engine(self, index):
        if index not in (0, 1):
            raise ValueError("engine must be 0 or 1")
        return EngineTransport(self, index)


class EngineTransport:
    def __init__(self, host, index):
        self.host, self.index = host, index

    @asynccontextmanager
    async def transaction(self):
        """Yield the selected byte bus while holding the shared transport lock.

        Use the yielded bus inside the context; calling this wrapper there would
        try to acquire the same non-reentrant lock again.
        """
        async with self.host.lock:
            await self.host.transport.write(SM_SELECT, self.index)
            yield self.host.transport

    async def read(self, address):
        async with self.transaction() as bus:
            return await bus.read(address)

    async def write(self, address, value):
        async with self.transaction() as bus:
            await bus.write(address, value)

    async def read_word(self, selector):
        async with self.transaction() as bus:
            await bus.write(DATA_ADDR, selector)
            value = 0
            for i, address in enumerate(DATA_BYTES):
                value |= (await bus.read(address)) << (8*i)
            return value

    async def write_word(self, selector, value):
        if not 0 <= value <= 0xffffffff:
            raise ValueError("word must fit in 32 bits")
        async with self.transaction() as bus:
            await bus.write(DATA_ADDR, selector)
            for i, address in enumerate(DATA_BYTES):
                await bus.write(address, (value >> (8*i)) & 255)
