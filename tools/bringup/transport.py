"""Stop-and-wait protocol: C3 seq op addr lo hi reserved XOR (8 bytes).

Replies: C3 seq status data 0 0 0 XOR. No automatic retries of side effects.
One outstanding command; sequence, checksum, status and deadline are mandatory.
"""
import asyncio
from functools import reduce
from operator import xor
import time

READ, WRITE, RESET, WAIT, ENABLE, SAMPLE = range(1, 7)


class SerialTransport:
    def __init__(self, serial, *, timeout=2.0, trace=None):
        if timeout <= 0:
            raise ValueError('timeout must be positive')
        self.serial, self.timeout, self.trace = serial, timeout, trace
        self.sequence = 0
        self.lock = asyncio.Lock()

    async def command(self, op, address=0, value=0):
        async with self.lock:
            return await asyncio.to_thread(self._command, op, address, value)

    def _command(self, op, address, value):
        packet = bytes((0xc3, self.sequence, op, address, value & 255, value >> 8, 0))
        packet += bytes((reduce(xor, packet),))
        self.sequence = (self.sequence + 1) & 255
        if self.trace:
            self.trace('tx', packet.hex())
        if self.serial.write(packet) != len(packet):
            raise IOError('short bridge write')
        deadline = time.monotonic() + self.timeout
        reply = bytearray()
        while len(reply) < 8:
            if time.monotonic() >= deadline:
                raise TimeoutError('bridge response deadline; reset bridge before retrying')
            chunk = self.serial.read(8-len(reply))
            reply.extend(chunk)
        if self.trace:
            self.trace('rx', reply.hex())
        if reply[0] != 0xc3 or reply[1] != packet[1] or reduce(xor, reply) or any(reply[4:7]):
            raise IOError('corrupt/stale bridge response; reset bridge before retrying')
        if reply[2]:
            raise IOError(f'bridge rejected command: status {reply[2]}')
        return reply[3]

    async def read(self, address):
        if not 0 <= address < 16:
            raise ValueError('address must be 0..15')
        return await self.command(READ, address)

    async def write(self, address, value):
        if not 0 <= address < 16 or not 0 <= value < 256:
            raise ValueError('invalid byte transaction')
        await self.command(WRITE, address, value)

    async def reset(self):
        await self.command(RESET)

    async def enable(self, enabled):
        await self.command(ENABLE, value=int(bool(enabled)))

    async def wait(self, cycles):
        if not 0 <= cycles <= 65535:
            raise ValueError('wait must fit 16 bits')
        await self.command(WAIT, value=cycles)

    async def sample(self):
        return await self.command(SAMPLE)
