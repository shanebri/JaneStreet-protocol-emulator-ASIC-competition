"""Digital USB-LS symbol timing on the unchanged PIO; no physical USB claims."""
import json
import os
from pathlib import Path

import cocotb
from test import Host
from pio_host import PIOHost
from pioasm import assemble
from streaming.host import Stream
from streaming.usb_ls import symbols,inspect

ROOT=Path(__file__).resolve().parents[1]


async def transmit(dut,payload,*,data1=False,gap=0):
    h=Host(dut);await h.reset();host=PIOHost(h);engine=host.engine(0)
    words,expected=symbols(payload,data1=data1)
    commands=b''.join(w.to_bytes(4,'little') for w in words[1:])[:expected['symbols']]
    stream=Stream(engine,'uart',commands)
    assert stream.tx==words
    await engine.write(0,14)
    async with engine.transaction() as bus:
        await bus.write(2,0)
        for word in assemble((ROOT/'examples/usb_ls_tx_symbols.asm').read_text()):
            await bus.write(3,word&255);await bus.write(4,word>>8)
    for selector,value in ((4,2),(0x10,3),(0x11,0x83e0),(0x12,0x40010),(0x13,1)):
        await engine.write_word(selector,value)
    await stream.service();begin=len(h.samples)
    await engine.write(0,1)
    for _ in range(2000):
        await stream.service()
        if stream.all_transferred and not (await engine.read(1))&1: break
        await h.tick(gap)
    else: raise AssertionError('symbol packet timed out')
    await h.tick(5)
    assert await engine.read(13)==0
    assert await engine.read(11)==0
    return h.samples[begin:],expected


@cocotb.test()
async def usb_ls_data_packet_timing(dut):
    rows=[]
    for payload in (b'',b'\x00',b'\xff',bytes(range(8)),bytes([255])*8,
                    bytes.fromhex('00112233445566'),bytes.fromhex('fe7fff00')):
        for data1 in (False,True):
            samples,expected=await transmit(dut,payload,data1=data1)
            observed=inspect(samples)
            assert observed['payload_hex']==payload.hex()
            assert observed['data1']==data1
            assert observed['symbols']==expected['symbols']
            assert observed['total_clocks']==expected['total_clocks']
            assert observed['edge_quantization_min_clocks']>=-2/3
            rows.append(dict(expected=expected,observed=observed))
            if payload==bytes([255])*8 and not data1:
                trace=Path(os.environ['STREAM_RESULTS']).parent/'usb_ls_ff8_samples.csv'
                trace.write_text('clock,logical_dp,logical_dm,tx_marker\n'+''.join(
                    f'{i},{s&1},{(s>>1)&1},{(s>>2)&1}\n' for i,s in enumerate(samples)))
    Path(os.environ['STREAM_RESULTS']).write_text(json.dumps(dict(
        scope='digital packet TX prototype; no PHY, RX, handshake or enumeration',rows=rows),indent=2)+'\n')


@cocotb.test()
async def usb_ls_host_starvation_is_invalid_timing(dut):
    samples,_=await transmit(dut,bytes([255])*8,gap=1024)
    try: inspect(samples)
    except ValueError: pass
    else: raise AssertionError('stretched packet incorrectly accepted as valid USB timing')
