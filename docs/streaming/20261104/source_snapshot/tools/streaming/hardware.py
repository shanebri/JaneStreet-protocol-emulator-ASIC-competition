"""Packed streaming peer run on the preserved bridge v2; no FPGA programming.

Requires explicit actual-image/wiring facts in the fixture, then records bounded
serial traffic and peer results. This is functional hardware evidence; waveform
and electrical measurements remain separate.
"""
import argparse
import asyncio
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import random
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from pio_host import PIOHost
from bringup.transport import SerialTransport
from spi_hardware.check_spi import Results,wait_reply
from streaming.host import Stream,configure


async def execute(io,uart_port,nano_port,fixture,emit):
    host=PIOHost(io)
    uart_payload=bytes(random.Random(fixture.get('seed',2204)).randbytes(256))
    spi_payload=bytes(range(256))
    await io.require_v2();await io.reset()
    await host.engine(0).write_word(0x1b,1<<3)
    ud=round(fixture['clock_hz']/(14*fixture.get('uart_baud',1200)))
    sd=fixture.get('spi_divider',8192)
    await configure(host.engine(0),'spi',sd,spi_mosi=0,spi_clock=1,spi_cs=2,ready_pin=1)
    await configure(host.engine(1),'uart',ud,uart_pin=3)
    # The peer's READY signal gates every CS assertion. This opt-in firmware
    # variant adds a documented wait tick outside CS, preserving SPI bit timing.
    streams=[Stream(host.engine(0),'spi',spi_payload),Stream(host.engine(1),'uart',uart_payload)]
    for stream in streams: await stream.service()
    uart_port.reset_input_buffer()
    await asyncio.to_thread(wait_reply,nano_port,'PING','PIO_SPI_NANO_V1')
    await asyncio.to_thread(wait_reply,nano_port,'ARM','ARMED 256 MODE0 MSB')
    deadline=time.monotonic()+fixture.get('timeout_seconds',60)
    results=Results()

    def read_peers():
        observed=bytearray(); nano_lines=[]
        while time.monotonic()<deadline:
            chunk=uart_port.read(256-len(observed)) if len(observed)<256 else b''
            observed.extend(chunk)
            line=nano_port.readline()
            if line:
                if not line.endswith(b'\n'): raise IOError('truncated Nano record')
                text=line.decode('ascii').strip();results.accept_nano(text)
                nano_lines.append(text)
            if results.nano_done and len(observed)==256:
                return bytes(observed),nano_lines
        raise TimeoutError('peer reception deadline')

    peers=asyncio.create_task(asyncio.to_thread(read_peers))
    emit(dict(type='intent',uart_hex=uart_payload.hex(),spi_hex=spi_payload.hex(),
              uart_divider=ud,spi_divider=sd,spi_ready_wait=True))
    try:
        await host.engine(0).write_word(0x1c,3)
        while True:
            for stream in streams: await stream.service()
            if peers.done() and peers.exception(): raise peers.exception()
            if all(s.all_transferred for s in streams):
                status=[await host.engine(i).read(1) for i in (0,1)]
                if any(s&4 for s in status): raise AssertionError('PIO fault')
                if not any(s&1 for s in status): break
            if time.monotonic()>deadline: raise TimeoutError('host streaming deadline')
        uart_observed,nano_lines=await peers
        spi_rx=streams[0].received()
        if uart_observed!=uart_payload: raise AssertionError('UART peer data mismatch')
        for i,byte in enumerate(spi_rx):
            results.accept_fpga(dict(sequence=i,tx=i,rx=byte,status=0))
        if not results.complete: raise AssertionError('incomplete SPI peer evidence')
        for i in (0,1):
            if await host.engine(i).read(13): raise AssertionError('FIFO errors')
            if await host.engine(i).read(11): raise AssertionError('residual queue data')
        emit(dict(type='result',status='PASS',uart_hex=uart_observed.hex(),spi_rx_hex=spi_rx.hex(),
                  nano_lines=nano_lines,host=[s.statistics() for s in streams],
                  evidence_kind='physical_functional_peers',waveforms='NOT_ACQUIRED'))
    finally:
        if not io.poisoned:
            await host.engine(0).write_word(0x1c,0xc0)
        if not peers.done():
            # Serial reads are bounded; do not close their ports underneath the
            # thread. Let its shared deadline expire and retain any exception.
            await asyncio.gather(peers,return_exceptions=True)


def validate_fixture(fixture):
    if fixture.get('clock_hz')!=50_000_000: raise ValueError('expected 50 MHz fixture')
    ports=[fixture.get(k,'') for k in ('port','nano_port','uart_peer_port')]
    if any(not p or p.startswith('EDIT') for p in ports) or len(set(p.casefold() for p in ports))!=3:
        raise ValueError('three distinct actual serial ports required')
    if fixture.get('concurrent_wiring_confirmed') is not True:
        raise ValueError('actual concurrent-profile wiring has not been confirmed')
    if fixture.get('programmed_image_confirmed') is not True:
        raise ValueError('operator has not identified the programmed image')
    image=Path(fixture['image'])
    qualification=json.loads((ROOT/'docs/fpga_bringup_v2_20261101_receipt.json').read_text())
    if fixture['expected_image_sha256']!=qualification['image_sha256']:
        raise ValueError('fixture does not identify the qualified bridge v2 image')
    if hashlib.sha256(image.read_bytes()).hexdigest()!=fixture['expected_image_sha256']:
        raise ValueError('local image hash differs from fixture')
    return ports


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fixture',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();fixture=json.loads(a.fixture.read_text());ports=validate_fixture(fixture)
    a.out.mkdir(parents=True,exist_ok=False)
    import serial
    with ExitStack() as stack:
        log=stack.enter_context((a.out/'traffic.jsonl').open('x'))
        def emit(value): log.write(json.dumps(value)+'\n');log.flush()
        board=stack.enter_context(serial.Serial(ports[0],fixture.get('baud',115200),timeout=.05,write_timeout=2))
        nano=stack.enter_context(serial.Serial(ports[1],115200,timeout=.05,write_timeout=2))
        uart=stack.enter_context(serial.Serial(ports[2],fixture.get('uart_baud',1200),timeout=.05,write_timeout=2))
        io=SerialTransport(board,trace=lambda kind,value:emit(dict(type='bridge',kind=kind,value=value)))
        status=dict(status='RUNNING',fixture=fixture,physical_waveforms='NOT_ACQUIRED')
        try:
            asyncio.run(execute(io,uart,nano,fixture,emit));status['status']='PASS_FUNCTIONAL_PEERS'
        except BaseException as exc:
            status.update(status='FAILED',error=repr(exc));raise
        finally:
            status['traffic_sha256']=hashlib.sha256((a.out/'traffic.jsonl').read_bytes()).hexdigest()
            (a.out/'receipt.json').write_text(json.dumps(status,indent=2)+'\n')


if __name__=='__main__':main()
