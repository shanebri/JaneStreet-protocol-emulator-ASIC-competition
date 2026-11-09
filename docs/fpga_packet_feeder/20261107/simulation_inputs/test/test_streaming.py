"""Package-pin packed streaming, finite tails, host pauses and bank isolation."""
import json
import os
from pathlib import Path

import cocotb
from cocotb.triggers import Timer
from test import Host,check_frames
from pio_host import PIOHost
from streaming.host import Stream,configure

GATES=os.environ.get('STREAM_GATES')=='1' or os.environ.get('GATES')=='yes'
DEPTH=int(os.environ.get('STREAM_DEPTH','4'))


class Pins(Host):
    def __init__(self,dut):
        super().__init__(dut)
        self.monitor=False; self.cycle=0; self.previous=64
        self.spi_index=0; self.bits=[]; self.edge=None; self.selected=None
        self.spi_div=1; self.spi_payload=b'';self.peer_payload=b'';self.ready=False
        self.stats=[dict(tx_stall=0,rx_stall=0,first_tx_stall=None,first_rx_stall=None) for _ in range(2)]
        self.cores=None if GATES else [dut.user_project.pio.engines[i].core for i in range(2)]

    def control(self,value):
        self.control_value=value
        self.dut.ui_in.value=value | ((self.inputs | (2 if self.ready else 0))<<6)

    async def tick(self,count=1):
        for _ in range(count):
            self.dut.clk.value=0
            await Timer(10,unit='ns')
            if self.monitor and self.cores:
                for i,c in enumerate(self.cores):
                    if int(c.attempt.value) and int(c.stall.value):
                        opcode,arg=int(c.opcode.value),int(c.arg.value)
                        reason=('tx_stall' if opcode==3 or (opcode==4 and arg&128)
                                else 'rx_stall' if opcode in (2,4) else None)
                        if reason:
                            self.stats[i][reason]+=1
                            if self.stats[i]['first_'+reason] is None:
                                self.stats[i]['first_'+reason]=self.cycle
            self.dut.clk.value=1
            await Timer(10,unit='ns')
            value=int(self.dut.uo_out.value);self.samples.append(value)
            if self.monitor:
                if self.previous&64 and not value&64:
                    assert not value&32
                    assert self.spi_index<len(self.spi_payload),'extra SPI frame'
                    self.bits=[]; self.selected=self.cycle;self.edge=None
                    self.inputs=(self.peer_payload[self.spi_index]>>7)&1
                    self.control(self.control_value)
                if (self.previous^value)&32:
                    assert not value&64,'SPI clock outside CS'
                    if value&32:
                        assert self.cycle-(self.selected if self.edge is None else self.edge)==8*self.spi_div
                        self.bits.append((value>>4)&1)
                    else:
                        assert self.cycle-self.edge==8*self.spi_div
                        if len(self.bits)<8:
                            self.inputs=(self.peer_payload[self.spi_index]>>(7-len(self.bits)))&1
                            self.control(self.control_value)
                    self.edge=self.cycle
                if not self.previous&64 and value&64:
                    assert len(self.bits)==8
                    assert self.cycle-self.edge==4*self.spi_div
                    byte=sum(b<<(7-i) for i,b in enumerate(self.bits))
                    assert byte==self.spi_payload[self.spi_index],(self.spi_index,byte)
                    self.spi_index+=1
                self.previous=value; self.cycle+=1


async def setup(dut,length,*,packed=True,uart_div=1,spi_div=1,ready=False):
    h=Pins(dut);await h.reset();h.spi_div=spi_div
    host=PIOHost(h)
    await host.engine(0).write_word(0x1b,1)
    await configure(host.engine(0),'spi',spi_div,packed=packed,ready_pin=1 if ready else None)
    await configure(host.engine(1),'uart',uart_div,packed=packed)
    spi=bytes((i*37+0x96)&255 for i in range(length))
    uart=bytes((i*29+0xa6)&255 for i in range(length))
    peer=bytes((i*73+0x3d)&255 for i in range(length))
    streams=[Stream(host.engine(0),'spi',spi,packed,DEPTH),Stream(host.engine(1),'uart',uart,packed,DEPTH)]
    for stream in streams: await stream.service()
    h.spi_payload=spi;h.peer_payload=peer
    h.monitor=True;h.previous=h.samples[-1];h.begin=len(h.samples)
    await host.engine(0).write_word(0x1c,3)
    return h,host,streams,uart,peer


async def complete(h,host,streams,uart,peer,*,batch=True,gap=0,uart_div=1):
    start=h.cycle;rounds=0;service_clocks=0
    deadline=h.cycle+len(uart)*max(143*uart_div,138*h.spi_div)+(gap+1000)*(len(uart)+10)+20000
    while True:
        before=h.cycle
        for stream in streams: await stream.service(batch=batch)
        service_clocks+=h.cycle-before;rounds+=1
        if all(s.all_transferred for s in streams):
            status=[await host.engine(i).read(1) for i in (0,1)]
            assert not any(s&4 for s in status),'instruction fault'
            if not any(s&1 for s in status): break
        if h.cycle>deadline: raise AssertionError('stream did not complete within bounded service deadline')
        await h.tick(gap)
    elapsed=h.cycle
    for i in (0,1):
        assert await host.engine(i).read(11)==0,'FIFO residual words'
        assert await host.engine(i).read(13)==0,'sticky FIFO errors'
    assert streams[0].received()==peer,'SPI RX payload/tail mismatch'
    assert h.spi_index==len(uart),'SPI byte count mismatch'
    starts=check_frames(h.samples[h.begin:],uart,14*uart_div)
    assert len(starts)==len(uart)
    assert all(b-a>=143*uart_div for a,b in zip(starts,starts[1:]))
    assert int(h.dut.uo_out.value)&0x61==0x41,'protocol idle levels'
    h.monitor=False
    return dict(depth=DEPTH,packed=streams[0].packed,batch=batch,payload_bytes_per_protocol=len(uart),
        uart_divider=uart_div,spi_divider=h.spi_div,extra_gap_clocks=gap,
        elapsed_clocks=elapsed,service_clocks=service_clocks,service_rounds=rounds,
        host=[s.statistics() for s in streams],stalls=None if GATES else h.stats,
        uart_frames=len(starts),spi_frames=h.spi_index,spi_rx_bytes=len(peer),
        payload_and_waveforms='pass',execution='gate_functional' if GATES else 'rtl')


async def run_case(dut,length,*,packed=True,batch=True,gap=0,uart_div=1,spi_div=1):
    h,host,streams,uart,peer=await setup(dut,length,packed=packed,uart_div=uart_div,spi_div=spi_div)
    return await complete(h,host,streams,uart,peer,batch=batch,gap=gap,uart_div=uart_div)


@cocotb.test()
async def packed_lengths_tails_and_banks(dut):
    lengths=(1,2,3,4,5,7,8,9,15,16,17,31,63) if not GATES else (1,2,3,4,5,17)
    for length in lengths:
        await run_case(dut,length,gap=32 if length%2 else 0)
    for length in (5,17): await run_case(dut,length,packed=False,batch=False,gap=16)


@cocotb.test()
async def packed_backpressure_and_reset_recovery(dut):
    h,host,streams,uart,peer=await setup(dut,65)
    # Withhold RX only while continuing to feed TX. This must stop at a safe
    # PUSH after CS release, retaining the complete next RX word in ISR.
    start=h.cycle
    while h.cycle-start<(DEPTH+2)*4*138:
        for stream in streams: await stream.service(drain_rx=False)
    assert (await host.engine(0).read(11))>>4==DEPTH
    assert int(dut.uo_out.value)&0x60==0x40
    await complete(h,host,streams,uart,peer)
    # A reset abandons the in-flight stream; a fresh header must not expose any
    # stale payload or RX tail. Existing IMEM retention remains applicable.
    h,host,streams,uart,peer=await setup(dut,33)
    await h.tick(50)
    h.monitor=False
    await run_case(dut,7,gap=256)


@cocotb.test()
async def packed_external_peer_ready(dut):
    h,host,streams,uart,peer=await setup(dut,17,ready=True)
    await h.tick(100)
    assert h.spi_index==0
    assert int(dut.uo_out.value)&0x60==0x40
    h.ready=True;h.control(h.control_value)
    await complete(h,host,streams,uart,peer)


@cocotb.test()
async def packed_delay_benchmark(dut):
    if os.environ.get('STREAM_BENCHMARK')!='1':
        await run_case(dut,9,uart_div=31,spi_div=4,gap=256)
        return
    rows=[]
    for name,ud,sd,length,gaps in (
        ('practical',31,4,32,(0,512,1024)),('fast',1,1,256,(0,64,128,512))):
        for packed,batch in ((False,False),(True,False),(True,True)):
            for gap in gaps:
                row=await run_case(dut,length,packed=packed,batch=batch,gap=gap,uart_div=ud,spi_div=sd)
                row['workload']=name;rows.append(row)
                Path(os.environ['STREAM_RESULTS']).write_text(json.dumps(dict(clock_ns=20,rows=rows),indent=2)+'\n')
                print('STREAM',name,packed,batch,gap,row['elapsed_clocks'],row['service_clocks'],flush=True)
