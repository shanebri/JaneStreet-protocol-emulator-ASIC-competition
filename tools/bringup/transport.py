"""Stop-and-wait protocol: C3 seq op addr lo hi reserved XOR (8 bytes).

Replies: C3 seq status data 0 0 0 XOR. No automatic retries of side effects.
One outstanding command; sequence, checksum, status and deadline are mandatory.
"""
import asyncio
from functools import reduce
from operator import xor
import time

READ, WRITE, RESET, WAIT, ENABLE, SAMPLE = range(1, 7)
INFO, RAW_BEAT, PADS, INPUTS, TRACE_ARM, TRACE_STATUS, TRACE_READ, TRACE_CANCEL = range(7, 15)
WIDE_REPLIES = (TRACE_STATUS, TRACE_READ, 15, 25)


class SerialTransport:
    evidence_kind = 'hardware_transport'
    def __init__(self, serial, *, timeout=2.0, trace=None):
        if timeout <= 0:
            raise ValueError('timeout must be positive')
        self.serial, self.timeout, self.trace = serial, timeout, trace
        self.sequence = 0
        self.lock = asyncio.Lock()
        self.poisoned = False

    async def command(self, op, address=0, value=0):
        async with self.lock:
            if self.poisoned:
                raise IOError('bridge session is indeterminate; reset the bridge and start a new run')
            try:
                return await asyncio.to_thread(self._command, op, address, value)
            except (OSError, TimeoutError):
                self.poisoned = True
                raise

    def _command(self, op, address, value):
        if not 0 <= op <= 255 or not 0 <= address < 16 or not 0 <= value <= 65535:
            raise ValueError('invalid bridge command fields')
        packet = bytes((0xc3, self.sequence, op, address, value & 255, value >> 8, 0))
        packet += bytes((reduce(xor, packet),))
        self.sequence = (self.sequence + 1) & 255
        if self.trace:
            self.trace('tx', packet.hex())
        written = self.serial.write(packet)
        if self.trace:
            self.trace('tx_result', dict(bytes_sent=written, requested=len(packet)))
        if written != len(packet):
            raise IOError('short bridge write')
        deadline = time.monotonic() + self.timeout
        reply = bytearray()
        while len(reply) < 8:
            if time.monotonic() >= deadline:
                if self.trace:
                    self.trace('rx_timeout', dict(partial_hex=reply.hex(), expected_bytes=8))
                raise TimeoutError('bridge response deadline; reset bridge before retrying')
            chunk = self.serial.read(8-len(reply))
            if chunk and self.trace:
                self.trace('rx_chunk', chunk.hex())
            reply.extend(chunk)
        if self.trace:
            self.trace('rx', reply.hex())
        if (reply[0] != 0xc3 or reply[1] != packet[1] or reduce(xor, reply)
                or (op not in WIDE_REPLIES and any(reply[4:7]))):
            raise IOError('corrupt/stale bridge response; reset bridge before retrying')
        if reply[2]:
            raise IOError(f'bridge rejected command: status {reply[2]}')
        return bytes(reply[3:7]) if op in WIDE_REPLIES else reply[3]

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

    async def require_v2(self):
        version = await self.command(INFO)
        if version != 2:
            raise ValueError('This suite requires the bridge v2 FPGA image')
        return version

    async def raw_beat(self, address, nibble=0, strobes=1, cycles=2):
        if not 0 <= address < 16 or not 0 <= nibble < 16 or strobes not in (0, 1, 2, 3) or not 2 <= cycles <= 255:
            raise ValueError('invalid raw nibble beat')
        return await self.command(RAW_BEAT, address, (cycles << 8) | (strobes << 4) | nibble)

    async def sample_pads(self):
        value = await self.command(PADS)
        return dict(inputs=value & 15, oe=value >> 4)

    async def sample_inputs(self):
        return await self.command(INPUTS)

    async def trace_arm(self, channel, *, falling=True, decimation=0, immediate=False):
        if not 0 <= channel < 22 or not 0 <= decimation <= 15:
            raise ValueError('invalid capture trigger or decimation')
        await self.command(TRACE_ARM, decimation, channel | (int(falling) << 5) | (int(immediate) << 6))

    async def trace_status(self):
        data = await self.command(TRACE_STATUS)
        if len(data) != 4 or not 1 <= data[3] <= 15:
            raise ValueError('invalid trace status/depth')
        return dict(armed=bool(data[0] & 1), capturing=bool(data[0] & 2),
                    done=bool(data[0] & 4), triggered=bool(data[0] & 8),
                    count=int.from_bytes(data[1:3], 'little'), depth=1 << data[3])

    async def trace_read(self, index):
        if not 0 <= index <= 65535:
            raise ValueError('capture index must fit 16 bits')
        return int.from_bytes(await self.command(TRACE_READ, value=index), 'little')

    async def trace_cancel(self):
        await self.command(TRACE_CANCEL)
