"""Explicit fixture-dependent protocol profiles; never silently skipped."""
import asyncio
from pathlib import Path
import time
from pio_host import PIOHost
from i2c_driver import I2C
from bringup.scenarios import load, finished, equal
from spi_hardware.check_spi import Results, wait_reply

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


async def spi(io, fixture, emit, trace):
    """Existing Nano sketch, same 256-byte independent checker, no buttons."""
    import serial
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
    """Fixture specifies deterministic target response; uses production I2C driver."""
    config=fixture['i2c']
    expected=bytes.fromhex(config['expected_hex'])
    if not expected: raise ValueError('I2C profile requires a nonempty expected response')
    await io.reset()
    engine=PIOHost(io).engine(0)
    driver=I2C(engine,timeout=config.get('timeout',5))
    await driver.configure(rate=config.get('rate',100000))
    result=await driver.transfer(config['address'],bytes.fromhex(config.get('write_hex','')),len(expected))
    trace('i2c',dict(status=result.status,data=result.data.hex(),completed=result.completed))
    if (result.status!='success' or result.data!=expected or
            result.completed!=len(bytes.fromhex(config.get('write_hex','')))+len(expected)):
        raise AssertionError(f'I2C target mismatch: {result}')
    await engine.write(0,0x20)  # Release pads after the transaction.
    emit(dict(test='i2c_target',status='PASS',received=result.data.hex()))
