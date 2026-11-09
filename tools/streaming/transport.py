"""Streaming bridge adapter over the committed stop-and-wait byte protocol.

Bridge-v2 INFO is queried without depending on the separate bring-up campaign.
Any indeterminate serial operation poisons the session; side effects are never
automatically retried.
"""
import asyncio
from bringup.transport import SerialTransport as ByteTransport

INFO = 7


class SerialTransport(ByteTransport):
    def __init__(self, serial, *, timeout=2.0, trace=None):
        super().__init__(serial, timeout=timeout, trace=trace)
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

    async def require_v2(self):
        version = await self.command(INFO)
        if version != 2:
            raise ValueError('Packed hardware validation requires the qualified bridge v2 image')
        return version
