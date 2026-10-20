"""PIO 0x21 FIFO I2C driver. The transport owns synchronous nibble handshakes.

Async ByteTransport implementations supply read(address), write(address, byte).
No live pad writes occur during transfers. A monotonic deadline covers every
service wait; a transport must itself have bounded I/O. See docs/i2c.md.
"""
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from pioasm import assemble

VERSION = 0x21
CTRL, STATUS, DATA_ADDR, LEVEL, IRQ, INPUT = 0, 1, 5, 11, 12, 14
DATA_BYTES = (6, 7, 9, 10)
PINS, TX, RX, SHIFT, EXEC, DIVIDER = 4, 8, 9, 0x10, 0x11, 0x13
ROUTE, DIRS, OD, FILTER = 0x16, 0x17, 0x18, 0x19
ABORT_RELEASE = 0x20
SDA_PAD, SCL_PAD = 0, 1
OUT_PAD_BASE, INPUT_PAD_BASE = 8, 2
BITS, START, LOW, STOP, ENTRY = 2, 9, 14, 16, 21
DIVIDERS = {100_000: 24, 400_000: 6, 10_000: 240}


class ByteTransport(Protocol):
    async def read(self, address: int) -> int: ...
    async def write(self, address: int, value: int) -> None: ...


@dataclass(frozen=True)
class Result:
    status: str
    completed: int
    data: bytes = b""


def bits_command(bits):
    bits = tuple(bits)
    if not 1 <= len(bits) <= 9 or any(b not in (0, 1) for b in bits):
        raise ValueError("one to nine binary wire bits required")
    return BITS | ((len(bits)-1) << 5) | sum(b << (9+i) for i, b in enumerate(bits))


def write_command(byte):
    if not 0 <= byte <= 255:
        raise ValueError("byte out of range")
    return bits_command([(byte >> i) & 1 for i in range(7, -1, -1)] + [1])


def read_command(final):
    return bits_command([1]*8 + [int(final)])


class I2C:
    def __init__(self, transport: ByteTransport, *, timeout=0.25, clock=time.monotonic):
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.io, self.timeout, self.clock = transport, timeout, clock
        self.sda, self.scl = SDA_PAD, SCL_PAD

    async def word(self, selector, value=None):
        await self.io.write(DATA_ADDR, selector)
        if value is None:
            result = 0
            for i, reg in enumerate(DATA_BYTES):
                result |= (await self.io.read(reg)) << (8*i)
            return result
        for i, reg in enumerate(DATA_BYTES):
            await self.io.write(reg, (value >> (8*i)) & 255)

    async def configure(self, rate=100_000, sda=SDA_PAD, scl=SCL_PAD):
        if rate not in DIVIDERS or not 0 <= sda < 4 or not 0 <= scl < 4 or sda == scl:
            raise ValueError("unsupported rate or pad assignment")
        if await self.io.read(15) != VERSION:
            raise RuntimeError("PIO host transport revision 0x21 required")
        self.sda, self.scl = sda, scl
        await self.io.write(CTRL, 2 | 4 | 8)
        source = (Path(__file__).resolve().parents[1] / "examples/i2c.asm").read_text()
        source = source.replace("gpio, 3", f"gpio, {INPUT_PAD_BASE+scl}")
        await self.io.write(2, 0)
        for word in assemble(source):
            await self.io.write(3, word & 255)
            await self.io.write(4, word >> 8)
        out_sda, out_scl = OUT_PAD_BASE+sda, OUT_PAD_BASE+scl
        await self.word(SHIFT, 1)  # OUT right, IN left, no automatic transfers
        await self.word(EXEC, 0x8000 | (31 << 5) | (ENTRY << 10))
        await self.word(ROUTE, 1 | (out_sda << 1) | (1 << 5) | (out_sda << 9) |
                        (1 << 13) | ((INPUT_PAD_BASE+sda) << 17) | (out_scl << 20))
        await self.word(DIVIDER, DIVIDERS[rate])
        mask = (1 << out_sda) | (1 << out_scl)
        await self.word(PINS, (await self.word(PINS)) | mask)
        await self.word(OD, (await self.word(OD)) | mask)
        await self.word(FILTER, (await self.word(FILTER)) | (mask >> 8))
        await self.word(DIRS, (await self.word(DIRS)) | mask)
        await self.io.write(IRQ, 1)
        await self.io.write(CTRL, 1)

    def check_deadline(self, deadline):
        if self.clock() >= deadline:
            raise TimeoutError("I2C service/clock-stretch deadline expired")

    async def send(self, command, deadline):
        while (await self.io.read(LEVEL)) & 15 == 4:
            self.check_deadline(deadline)
        self.check_deadline(deadline)
        await self.word(TX, command)

    async def receive(self, deadline):
        while not (await self.io.read(LEVEL)) & 0x70:
            self.check_deadline(deadline)
            if await self.io.read(STATUS) & 4:
                raise RuntimeError("PIO firmware fault")
        return await self.word(RX)

    async def stop(self, deadline):
        await self.io.write(IRQ, 1)
        await self.send(STOP, deadline)
        while not (await self.io.read(IRQ)) & 1:
            self.check_deadline(deadline)

    async def transfer(self, address, write=b"", read=0):
        if not 0 <= address < 128 or not isinstance(read, int) or read < 0:
            raise ValueError("7-bit address and nonnegative read length required")
        write = bytes(write)
        deadline = self.clock() + self.timeout
        completed, received = 0, bytearray()
        try:
            # Entry waits in firmware too; busy is reported before any START.
            mask = (1 << (INPUT_PAD_BASE+self.sda)) | (1 << (INPUT_PAD_BASE+self.scl))
            if (await self.io.read(INPUT)) & mask != mask:
                return Result("bus_busy", 0)
            phases = [(False, write)] if write or not read else []
            if read:
                phases.append((True, range(read)))
            for reading, payload in phases:
                await self.send(START, deadline)
                await self.send(write_command((address << 1) | reading), deadline)
                if (await self.receive(deadline)) & 1:
                    await self.stop(deadline)
                    return Result("address_nack", completed, bytes(received))
                for i, byte in enumerate(payload):
                    await self.send(read_command(i == read-1) if reading else write_command(byte), deadline)
                    response = await self.receive(deadline)
                    if reading:
                        received.append((response >> 1) & 255)
                    elif response & 1:
                        await self.stop(deadline)
                        return Result("data_nack", completed, bytes(received))
                    completed += 1
            await self.stop(deadline)
            return Result("success", completed, bytes(received))
        except TimeoutError:
            await self.io.write(CTRL, ABORT_RELEASE)
            return Result("timeout", completed, bytes(received))

    async def bus_clear(self):
        """At most nine pulses, then STOP; stuck SCL times out and releases pads.

        Call configure first after an abort/reset to explicitly re-arm directions.
        The entry idle check is bypassed by stopped-state ENTRY selection.
        """
        deadline = self.clock() + self.timeout
        await self.io.write(CTRL, 2 | 4)
        await self.word(EXEC, 0x8000 | (31 << 5))
        await self.io.write(CTRL, 1)
        try:
            # BITS normally follows START/another byte with SCL already low.
            # Recovery can enter from idle: establish a complete low phase first.
            await self.send(LOW, deadline)
            await self.send(bits_command([1]*9), deadline)
            await self.receive(deadline)
            await self.stop(deadline)
            # Account for input qualification after the STOP's SDA release.
            mask = (1 << (INPUT_PAD_BASE+self.sda)) | (1 << (INPUT_PAD_BASE+self.scl))
            ok = ((await self.io.read(INPUT)) & mask) == mask
            if not ok:
                await self.io.write(CTRL, ABORT_RELEASE)
            return Result("success" if ok else "bus_clear_failed", 0)
        except TimeoutError:
            await self.io.write(CTRL, ABORT_RELEASE)
            return Result("bus_clear_failed", 0)


async def read_sensor_register(transport, address=0x48, register=0):
    bus = I2C(transport)
    await bus.configure(400_000)
    return await bus.transfer(address, bytes([register]), read=2)
