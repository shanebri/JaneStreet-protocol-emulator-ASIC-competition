"""Exercise concurrent slots against the ASIC pins with no serial scheduling."""
import json
import os
from pathlib import Path
import cocotb
from cocotb.triggers import Timer
from test import Host
from streaming.feeder import configure
from streaming.usb_ls import inspect, symbols


class Fixture:
    def __init__(self, dut):
        self.dut, self.host = dut, Host(dut)

    async def reset(self):
        self.dut.cmd_valid.value=0
        self.dut.cmd.value=0
        self.dut.cmd_slot.value=0
        self.dut.cmd_engine.value=0
        self.dut.cmd_both.value=0
        self.dut.cmd_data.value=0
        self.dut.cmd_length_minus_one.value=0
        self.dut.query_slot.value=0
        self.dut.query.value=0
        await self.host.reset()

    async def command(self, cmd, slot=0, data=0, length=0, engine=0, both=False):
        self.dut.cmd.value=cmd
        self.dut.cmd_slot.value=slot
        self.dut.cmd_data.value=data
        self.dut.cmd_length_minus_one.value=length
        self.dut.cmd_engine.value=engine
        self.dut.cmd_both.value=both
        self.dut.cmd_valid.value=1
        await Timer(1, unit='ns')
        assert self.dut.cmd_ready.value
        await self.host.tick()
        self.dut.cmd_valid.value=0
        await Timer(1, unit='ns')

    async def upload(self, slot, engine, payload, sequence, data1=False):
        words, expected=symbols(payload, data1=data1)
        await self.command(0,slot,sequence,words[0],engine)
        for word in words[1:]:
            await self.command(1,slot,word)
        await self.command(2,slot)
        return expected

    async def complete(self):
        states=[0,0]
        for cycle in range(25000):
            slot=cycle & 1
            self.dut.query_slot.value=slot
            self.dut.query.value=0
            await self.host.tick()
            states[slot]=int(self.dut.query_data.value) & 7
            if states==[4,4]:
                break
        else:
            raise AssertionError('slots did not finish within their watchdog bounds')
        results=[]
        for slot in (0,1):
            fields=[]
            self.dut.query_slot.value=slot
            for query in (0,1,2):
                self.dut.query.value=query
                await self.host.tick()
                fields.append(int(self.dut.query_data.value))
            results.append(dict(result=(fields[0]>>3)&3, sequence=fields[1], words_sent=fields[2]&63,
                                terminal_levels=(fields[2]>>14)&255, terminal_errors=(fields[2]>>22)&255))
        return results


@cocotb.test()
async def dual_maximum_packets(dut):
    f=Fixture(dut)
    await f.reset()
    await configure(f.host,0)
    await configure(f.host,1)
    await f.upload(0,1,b'\xff'*8,0x12345678,True)
    await f.upload(1,0,bytes(range(8)),0x9abcdef0)
    begin=len(f.host.samples)
    await f.command(3,both=True)
    results=await f.complete()
    assert [r['result'] for r in results]==[0,0]
    assert [r['sequence'] for r in results]==[0x12345678,0x9abcdef0]
    samples=f.host.samples[begin:]
    decoded=[inspect([word>>shift for word in samples]) for shift in (0,3)]
    assert [r['payload_hex'] for r in decoded]==[bytes(range(8)).hex(),'ff'*8]
    Path(os.environ['STREAM_RESULTS']).write_text(json.dumps(dict(results=results,decoded=decoded),indent=2)+'\n')


@cocotb.test()
async def upload_during_execution_and_watchdog_isolation(dut):
    f=Fixture(dut)
    await f.reset()
    await configure(f.host,0,'wait 1, gpio, 0\nhalt')
    await configure(f.host,1)
    await f.upload(0,0,b'\xff'*8,1)
    await f.command(3,0)
    await f.upload(1,1,b'\xa5',2)
    assert dut.busy.value
    begin=len(f.host.samples)
    await f.command(3,1)
    results=await f.complete()
    assert [r['result'] for r in results]==[3,0]
    assert [r['terminal_levels'] for r in results]==[4,0]
    observed=inspect([word>>3 for word in f.host.samples[begin:]])
    assert observed['payload_hex']=='a5'
