"""Explicit fixture-dependent protocol profiles; never silently skipped."""
import asyncio
from pathlib import Path
import time
from pio_host import PIOHost
from i2c_driver import ABORT_RELEASE, DIVIDERS, INPUT, I2C
from bringup.scenarios import load, finished, equal
from spi_hardware.check_spi import Results, wait_reply
from spi_hardware.peers import nano_peer

ROOT=Path(__file__).resolve().parents[2]


async def uart(io, fixture, emit, trace):
    import serial
    if fixture['uart_peer_port'].lower()==fixture['port'].lower():
        raise ValueError('PIO UART peer must use a different physical port')
    await io.reset()
    e=PIOHost(io).engine(0)
    await load(e,(ROOT/'examples/uart_v0.asm').read_text())
    await e.write_word(0x12,0x1008)
    await e.write_word(0x10,3)
    await e.write_word(0x13,31)
    with serial.Serial(fixture['uart_peer_port'],115200,timeout=2,write_timeout=2) as peer:
        for n in range(256):
            await e.write_word(8,n)
            await e.write(0,1)
            await finished(e)
            received=await asyncio.to_thread(peer.read,1)
            trace('uart_peer',received.hex())
            if received!=bytes((n,)):
                raise AssertionError(f'UART byte {n}: received {received.hex()}')
        if peer.in_waiting: raise AssertionError('unexpected extra UART bytes')
    emit(dict(test='uart_peer_256',status='PASS',transfers=256))


async def receive_uart_with_sender(io, fixture, emit, send):
    """Run the checked-in RX firmware on both engines with an independent sender."""
    config = fixture.get('uart_rx', {})
    if config.get('wiring_confirmed', True) is not True:
        raise ValueError('confirm adapter TX to Arty JA4 and shared ground in the UART RX fixture')
    baud = config.get('baud', 115200)
    if baud not in (9600, 19200, 38400, 57600, 115200):
        raise ValueError('unsupported UART RX baud')
    payload = bytes.fromhex(config.get('payload_hex', bytes(range(256)).hex()))
    if not 1 <= len(payload) <= 256:
        raise ValueError('UART RX needs 1..256 test bytes')
    divider = round(fixture['clock_hz']/(16*baud))
    if not 1 <= divider <= 65535:
        raise ValueError('UART RX divider is outside the hardware range')
    await io.require_v2()
    await io.reset()
    host = PIOHost(io)
    program = (ROOT/'examples/uart_rx.asm').read_text()
    for index in (0, 1):
        engine = host.engine(index)
        await load(engine, program)
        await engine.write_word(0x10, 3)
        await engine.write_word(0x13, divider)
        observed = bytearray()
        try:
            for sequence, byte in enumerate(payload):
                equal((await io.sample_inputs()) & 1, 1, 'UART RX input idle')
                await engine.write(0, 1)
                equal((await engine.read(1)) & 5, 1, 'UART RX waiting for start')
                await send(byte)
                await finished(engine)
                equal(await engine.read(11), 0x10, 'UART RX one queued word')
                word = await engine.read_word(9)
                equal(word, byte << 24, 'UART RX data and alignment')
                equal(await engine.read(11), 0, 'UART RX drained queues')
                equal(await engine.read(13), 0, 'UART RX FIFO errors')
                observed.append(word >> 24)
                emit(dict(test='uart_rx_byte', status='PASS', engine=index, sequence=sequence,
                          expected=byte, observed=word >> 24))
        finally:
            if not getattr(io, 'poisoned', False):
                await engine.write(0, 0x22)
        emit(dict(test='uart_rx_engine', status='PASS', engine=index, baud=baud, divider=divider,
                  nominal_baud=fixture['clock_hz']/(16*divider),
                  expected_hex=payload.hex(), observed_hex=observed.hex()))


async def uart_rx(io, fixture, emit, trace):
    import serial
    from bringup.concurrent_protocols import port_key
    if port_key(fixture['uart_peer_port']) == port_key(fixture['port']):
        raise ValueError('UART sender and bridge must use distinct physical ports')
    baud = fixture.get('uart_rx', {}).get('baud', 115200)
    with serial.Serial(fixture['uart_peer_port'], baud, timeout=.05, write_timeout=2,
                       rtscts=False, dsrdtr=False) as peer:
        async def send(byte):
            written = await asyncio.to_thread(peer.write, bytes((byte,)))
            trace('uart_sender', dict(byte=byte, bytes_sent=written))
            if written != 1:
                raise IOError('short UART peer write')
        await receive_uart_with_sender(io, fixture, emit, send)


async def spi(io, fixture, emit, trace):
    """Existing Nano sketch, same 256-byte independent checker, no buttons."""
    import serial
    nano_peer(fixture)
    if fixture['nano_port'].lower()==fixture['port'].lower():
        raise ValueError('Nano and bridge must use different physical ports')
    await io.reset()
    e=PIOHost(io).engine(0)
    await load(e, (ROOT/'examples/spi_mode0.asm').read_text())
    for selector,value in ((4,4),(0x12,0x20a08),(0x10,0),(0x11,0x83e0),(0x13,32)):
        await e.write_word(selector,value)
    results=Results()
    with serial.Serial(fixture['nano_port'],115200,timeout=.05,write_timeout=2) as nano:
        await asyncio.to_thread(wait_reply,nano,'PING','PIO_SPI_NANO_V1')
        await asyncio.to_thread(wait_reply,nano,'ARM','ARMED 256 MODE0 MSB')
        for n in range(256):
            deadline=time.monotonic()+5
            while not (await e.read(14)) & 2:  # READY on dedicated input 1.
                if time.monotonic()>deadline: raise TimeoutError('Nano READY')
            await e.write_word(8,n<<24)
            await e.write(0,1)
            await finished(e)
            equal((await e.read(11)>>4)&7,1,'SPI RX count')
            rx=await e.read_word(9)
            results.accept_fpga(dict(sequence=n,tx=n,rx=rx,status=0))
            line=await asyncio.to_thread(nano.readline)
            if not line.endswith(b'\n'): raise TimeoutError('Nano RX record missing/truncated')
            trace('nano',line.decode('ascii').strip())
            results.accept_nano(line.decode('ascii').strip())
            await asyncio.sleep(.01)  # Nano's documented >=5 ms re-arm interval.
        line=await asyncio.to_thread(nano.readline)
        trace('nano',line.decode('ascii').strip())
        results.accept_nano(line.decode('ascii').strip())
    if not results.complete: raise AssertionError('both endpoints must complete all 256 transfers')
    emit(dict(test='spi_peer_256',status='PASS',transfers=256))


async def i2c(io, fixture, emit, trace):
    """Exercise a deterministic peer and optionally probe an unused address."""
    config=fixture['i2c']
    address=config['address']
    rate=config.get('rate', 100_000)
    write=bytes.fromhex(config.get('write_hex', ''))
    expected=bytes.fromhex(config['expected_hex'])
    if not expected: raise ValueError('I2C profile requires a nonempty expected response')
    if type(address) is not int or not 0 <= address < 128 or rate not in DIVIDERS:
        raise ValueError('I2C profile requires a seven-bit address and a supported rate')
    nack_address=config.get('nack_address')
    if nack_address is not None and (type(nack_address) is not int
            or not 0x08 <= nack_address <= 0x77 or nack_address == address):
        raise ValueError('I2C NACK check requires a distinct, unreserved target address')
    engine=PIOHost(io).engine(0)
    driver=I2C(engine, timeout=config.get('timeout', 5), clock=getattr(io, 'clock', time.monotonic))
    cases = [('i2c_target', address, write, len(expected), 'success', expected)]
    if nack_address is not None:
        cases.append(('i2c_address_nack', nack_address, b'', 0, 'address_nack', b''))
    await io.reset()
    try:
        await driver.configure(rate=rate)
        for label, target, payload, count, status, response in cases:
            result = await driver.transfer(target, payload, count)
            want = dict(status=status, data=response.hex(), completed=len(payload)+count, idle_high=True)
            observed = dict(status=result.status, data=result.data.hex(), completed=result.completed,
                            idle_high=(await engine.read(INPUT)) & 0x0c == 0x0c)
            trace('i2c', dict(test=label, address=target, **observed))
            passed = observed == want
            emit(dict(test=label, type='assertion', status='PASS' if passed else 'FAIL',
                      address=target, expected=want, observed=observed, received=observed['data']))
            if not passed:
                raise AssertionError(f'{label} at 0x{target:02x}: expected {want}, observed {observed}')
    finally:
        if not getattr(io, 'poisoned', False):
            await engine.write(0, ABORT_RELEASE)
