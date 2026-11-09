"""Persistent UART/SPI firmware with independent USB UART and Nano peers."""
import asyncio
from contextlib import ExitStack
from pathlib import Path
import random
import time
import math

from pio_host import PIOHost, GROUP_START_BOTH, GROUP_STOP_BOTH, GROUP_RESUME_BOTH
from spi_hardware.check_spi import Results, wait_reply
from spi_hardware.peers import nano_peer
from bringup.scenarios import load
from bringup.stress import check, levels

ROOT = Path(__file__).resolve().parents[2]
UART = '''pull block
set x, 7
set pins, 0 [13]
bits: out pins, 1 [12]
jmp x--, bits
set pins, 1 [13]
jmp 0
'''
SPI = (ROOT/'examples/spi_mode0.asm').read_text().replace('halt side 0', 'jmp 0 side 0')


def port_key(value):
    return str(value).replace('\\\\.\\', '').casefold()


class TracedPort:
    def __init__(self, port, name, trace):
        self.port, self.name, self.trace = port, name, trace

    def write(self, data):
        count = self.port.write(data)
        self.trace(self.name+'_tx', dict(hex=data.hex(), bytes_sent=count))
        return count

    def read(self, count=1):
        data = self.port.read(count)
        if data:
            self.trace(self.name+'_rx', data.hex())
        return data

    def readline(self):
        data = self.port.readline()
        if data:
            self.trace(self.name+'_rx', data.hex())
        return data


class HardwarePeers:
    def __init__(self, fixture, trace, baud):
        self.fixture, self.trace, self.baud = fixture, trace, baud
        self.stack = ExitStack()
        self.results = Results()

    def __enter__(self):
        import serial
        ports = [self.fixture[key] for key in ('port', 'nano_port', 'uart_peer_port')]
        if len(set(map(port_key, ports))) != 3:
            raise ValueError('Bridge, Nano and UART receiver must use three distinct physical serial ports')
        nano_peer(self.fixture)
        try:
            nano = self.stack.enter_context(serial.Serial(ports[1], 115200, timeout=.05, write_timeout=2))
            uart = self.stack.enter_context(serial.Serial(ports[2], self.baud, timeout=5, write_timeout=2))
            self.nano, self.uart = TracedPort(nano, 'nano', self.trace), TracedPort(uart, 'uart_peer', self.trace)
            return self
        except BaseException:
            self.stack.close()
            raise

    def __exit__(self, *args):
        self.stack.close()

    async def arm(self, count):
        if count != 256:
            raise ValueError('Existing Nano ARM/checker protocol requires exactly 256 transfers')
        startup = self.uart.port.in_waiting
        if startup:
            data = await asyncio.to_thread(self.uart.read, startup)
            self.trace('uart_peer_startup_discard', dict(hex=data.hex(),
                reason='receiver opened during reset/configuration; no test burst has started'))
        await asyncio.to_thread(wait_reply, self.nano, 'PING', 'PIO_SPI_NANO_V1')
        await asyncio.to_thread(wait_reply, self.nano, 'ARM', 'ARMED 256 MODE0 MSB')

    async def prepare(self, sequence, uart_expected):
        pass  # hardware UART buffers and SPIS are already receiving independently

    async def received(self, sequence, uart_expected, spi_rx):
        data = await asyncio.to_thread(self.uart.read, len(uart_expected))
        line = await asyncio.to_thread(self.nano.readline)
        if not line.endswith(b'\n'):
            raise TimeoutError('missing/truncated Nano transaction record')
        self.results.accept_fpga(dict(sequence=sequence, tx=sequence, rx=spi_rx, status=0))
        self.results.accept_nano(line.decode('ascii').strip())
        return data, line.decode('ascii').strip()

    async def finish(self):
        line = await asyncio.to_thread(self.nano.readline)
        if not line.endswith(b'\n'):
            raise TimeoutError('missing Nano DONE record')
        self.results.accept_nano(line.decode('ascii').strip())
        if not self.results.complete or self.uart.port.in_waiting or self.nano.port.in_waiting:
            raise AssertionError('incomplete SPI endpoints or unexpected trailing peer data')


async def run_with_peers(io, fixture, seed, emit, trace, peers, *, recorder=None):
    await io.require_v2()
    config = fixture.get('concurrent', {})
    count = config.get('transfers', 256)
    baud = config.get('uart_baud', 1200)
    divider = round(fixture['clock_hz']/(14*baud))
    spi_divider = config.get('spi_divider', 8192)
    if not 1 <= count <= 256 or not 1 <= divider <= 65535 or not 1 <= spi_divider <= 65535:
        raise ValueError('invalid concurrent transfer count or divider')
    capture_rounds = config.get('capture_rounds', [85, 170])
    if any(type(n) is not int or not 0 <= n < count for n in capture_rounds):
        raise ValueError('capture_rounds must name actual transfer indices')
    capture_config = fixture.get('capture', {})
    if capture_config.get('mode', 'none') == 'fpga':
        if (capture_config.get('loopbacks_confirmed') is not True
                or capture_config.get('loopbacks') != {'pad0':'out0', 'pad1':'out2', 'pad2':'out3', 'pad3':'out1'}):
            raise ValueError('concurrent capture requires confirmed JA1->JC1, JA3->JC2, JB1->JC3 and JA2->JC4 loopbacks')
        depth = (await io.trace_status())['depth']
        nominal_baud = fixture['clock_hz']/(14*divider)
        required_window = 1.05*max(47/nominal_baud, 160*spi_divider/fixture['clock_hz'])
        decimation = capture_config.get('decimation', 'auto')
        if decimation == 'auto':
            decimation = max(0, math.ceil(math.log2(required_window*fixture['clock_hz']/depth)))
        if type(decimation) is not int or not 0 <= decimation <= 15:
            raise ValueError('capture decimation must be auto or an integer in 0..15')
        sample_period = (1 << decimation)/fixture['clock_hz']
        if sample_period*depth < required_window or sample_period > 1/(8*max(nominal_baud, fixture['clock_hz']/(16*spi_divider))):
            raise ValueError('capture depth/decimation cannot cover the burst with eight samples per bit; reduce rates or import a larger external capture')
    else:
        decimation = 0
    await io.reset()
    host, rng = PIOHost(io), random.Random(seed)
    spi, uart = host.engine(0), host.engine(1)
    await load(spi, SPI)
    await load(uart, UART)
    # Engine 1 owns only its UART output; SPI keeps outputs 0..2.
    await spi.write_word(0x1b, 1 << 3)
    for selector, value in ((4, 4), (0x12, 0x20a08), (0x10, 0), (0x11, 0x83e0), (0x13, spi_divider)):
        await spi.write_word(selector, value)
    for selector, value in ((4, 1 << 3), (0x12, 0xb0b), (0x10, 3), (0x13, divider)):
        await uart.write_word(selector, value)
    check(emit, 'loopback_pads_are_inputs', (await io.sample_pads())['oe'], 0)
    emit(dict(test='concurrent_firmware', type='firmware', seed=seed, spi=SPI, uart=UART,
              uart_divider=divider, uart_baud_requested=baud,
              uart_baud_nominal=fixture['clock_hz']/(14*divider), spi_divider=spi_divider,
              spi_clock_nominal_hz=fixture['clock_hz']/(16*spi_divider)))
    await peers.arm(count)
    clock = getattr(io, 'clock', time.monotonic)
    for sequence in range(count):
        # Persistent programs pause between bursts; START is used only once.
        # Group RESUME releases both engines on the same core edge thereafter.
        if sequence:
            await spi.write_word(0x1c, GROUP_STOP_BOTH)
        deadline = clock()+config.get('timeout_seconds', 5)
        while not (await spi.read(14)) & 2:
            if clock() > deadline:
                raise TimeoutError('Nano READY did not assert')
            await io.wait(256)
        payload = bytes(rng.randrange(256) for _ in range(4))
        emit(dict(test='concurrent_round', type='intent', sequence=sequence, seed=seed,
                  expected=dict(uart_hex=payload.hex(), spi_mosi=sequence, spi_miso=sequence ^ 0xa5)))
        await spi.write_word(8, sequence << 24)
        for byte in payload:
            await uart.write_word(8, byte)
        await peers.prepare(sequence, payload)
        if recorder and sequence in capture_rounds:
            await recorder.arm(f'concurrent-{sequence:03d}', channel='pad2',
                decimation=decimation,
                expected=dict(kind='uart_spi', seed=seed, sequence=sequence, uart_hex=payload.hex(),
                    uart_baud=fixture['clock_hz']/(14*divider), spi_mosi=sequence,
                    spi_miso=sequence ^ 0xa5, spi_clock_hz=fixture['clock_hz']/(16*spi_divider),
                    uart_channel='pad2', sclk_channel='pad3', mosi_channel='pad0',
                    miso_channel='in0', cs_channel='pad1'))
        await spi.write_word(0x1c, GROUP_START_BOTH if sequence == 0 else GROUP_RESUME_BOTH)
        last_poll = None
        for poll in range(200):
            # These real host reads are also visible in capture activity bins.
            status = [await host.engine(index).read(1) for index in (0, 1)]
            if any(value & 4 for value in status):
                raise AssertionError('PIO fault during concurrent protocol execution')
            uart_pc = await uart.read(8)
            spi_levels, uart_levels = await levels(spi), await levels(uart)
            last_poll = dict(status=status, uart_pc=uart_pc, spi_levels=list(spi_levels), uart_levels=list(uart_levels))
            if poll == 0:
                emit(dict(test='concurrent_poll', type='observation', sequence=sequence, **last_poll))
            if spi_levels == (0, 1) and uart_levels == (0, 0) and uart_pc == 0 and status[1] & 2:
                break
            if clock() > deadline:
                raise TimeoutError(f'concurrent burst did not reach its next blocked PULL: {last_poll}')
            await io.wait(65535)
        else:
            raise TimeoutError(f'concurrent burst poll limit: {last_poll}')
        observed_spi = await spi.read_word(9)
        check(emit, 'loopback_pads_remain_inputs', (await io.sample_pads())['oe'], 0, sequence=sequence)
        check(emit, 'concurrent_spi_rx', observed_spi, sequence ^ 0xa5, sequence=sequence)
        observed_uart, nano_line = await peers.received(sequence, payload, observed_spi)
        check(emit, 'concurrent_uart_rx', observed_uart.hex(), payload.hex(), sequence=sequence)
        for index in (0, 1):
            check(emit, 'concurrent_no_fifo_errors', await host.engine(index).read(13), 0, engine=index, sequence=sequence)
        emit(dict(test='concurrent_round', status='PASS', sequence=sequence, seed=seed,
                  expected=dict(uart_hex=payload.hex(), spi_mosi=sequence, spi_miso=sequence ^ 0xa5),
                  observed=dict(uart_hex=observed_uart.hex(), spi_miso=observed_spi, nano=nano_line)))
        if recorder and sequence in capture_rounds:
            await recorder.finish()
    await peers.finish()
    await spi.write(0, 0x20)
    await uart.write(0, 0x20)
    emit(dict(test='concurrent', status='PASS', seed=seed, spi_transfers=count, uart_bytes=count*4,
              execution='persistent firmware; synchronized START/RESUME bursts, paused between bursts'))


async def concurrent(io, fixture, seed, emit, trace, *, recorder=None):
    baud = fixture.get('concurrent', {}).get('uart_baud', 1200)
    with HardwarePeers(fixture, trace, baud) as peers:
        await run_with_peers(io, fixture, seed, emit, trace, peers, recorder=recorder)
