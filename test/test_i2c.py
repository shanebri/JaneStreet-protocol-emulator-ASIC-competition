"""Acceptance uses the external package pins, production encoder and driver."""
import random
import cocotb
from cocotb.utils import get_sim_time
from test import Host
from i2c_driver import I2C, Result, bits_command, read_command, START, STOP, write_command
from i2c_model import Bus


def driver(h, timeout=0.1):
    return I2C(h, timeout=timeout, clock=lambda: float(get_sim_time(unit="sec")))


@cocotb.test()
async def i2c_rates_payloads_repeated_start_and_remap(dut):
    rng = random.Random(2102)
    payload = bytes([0,255,0x55,0xaa,1,0x80] + [1 << i for i in range(8)] + [rng.randrange(256) for _ in range(8)])
    for rate, pads in ((400_000,(0,1)), (100_000,(0,1)), (10_000,(2,3)), (400_000,(3,1))):
        current_payload = payload if rate != 10_000 else payload[:6]
        h=Host(dut); await h.reset()
        bus=Bus(dut,host=h, sda=pads[0], scl=pads[1], data=current_payload, rate=rate,
                rise_ns=80 if rate==400_000 else 300, data_delay_ns=95,
                stretches={1:2300, 7:8100, 9:5000, 18:1500})
        try:
            i=driver(h, timeout=0.002 if rate == 400_000 else 0.08); await i.configure(rate,*pads)
            assert await h.read_word(0x13)=={400_000:6,100_000:24,10_000:240}[rate]
            assert await h.read_instruction(0)==0x80a0
            result=await i.transfer(0x48,current_payload,read=len(current_payload))
            assert result == Result("success",2*len(current_payload),current_payload), (result, await h.read(8), bus.bytes, bus.starts, bus.stops)
            assert bus.bytes == [0x90,*current_payload,0x91]
            assert bus.controller_acks == [0]*(len(current_payload)-1)+[1]
            assert bus.starts==2 and bus.stops==1
            assert bus.rises == 9*(2+2*len(current_payload))+2, "wrong clock pulse count"
            assert int(dut.uo_out.value)==1
            assert int(dut.uio_oe.value)&(0xf0 ^ ((1<<(pads[0]+4))|(1<<(pads[1]+4))))==0
            bus.check_timing()
            dut._log.info("I2C %d Hz pads %s: minimum low/high %.0f/%.0f ns",rate,pads,min(bus.lows),min(bus.highs))
        finally: bus.close()


@cocotb.test()
async def i2c_nacks_at_every_position(dut):
    for nack in (-1,0,1,2,3,4,5):
        h=Host(dut); await h.reset()
        bus=Bus(dut,host=h,nack_address=nack==-1,nack_data=nack)
        try:
            i=driver(h); await i.configure(400_000)
            result=await i.transfer(0x48,bytes(range(6)))
            assert result.status == ("address_nack" if nack==-1 else "data_nack")
            assert result.completed == max(0,nack)
            assert bus.stops==1 and bus.starts==1
            assert len(bus.bytes)==max(0,nack)+1+(nack>=0)
        finally: bus.close()


@cocotb.test()
async def i2c_busy_clear_timeout_abort_and_recovery(dut):
    h=Host(dut); await h.reset()
    bus=Bus(dut,host=h)
    try:
        i=driver(h,timeout=0.002); await i.configure(400_000)
        bus.stuck_sda=True; await h.tick(10)
        assert (await i.transfer(0x48,b"x")).status=="bus_busy"
        bus.clear_after=bus.rises+5
        assert (await i.bus_clear()).status=="success"
        assert min(bus.lows)>=1300, "bus-clear first low phase too short"
        assert min(bus.highs)>=600, "bus-clear high phase too short"
        assert (await i.transfer(0x48,b"x")).status=="success"
        bus.stuck_sda=True; await h.tick(10)
        assert (await i.bus_clear()).status=="bus_clear_failed"
        assert int(dut.uio_oe.value)&0xf0==0
        bus.stuck_sda=False; await i.configure(400_000)
        bus.stretches[bus.falls+1]=10_000_000
        assert (await i.transfer(0x48,b"x")).status=="timeout"
        assert int(dut.uio_oe.value)&0xf0==0
        assert await h.read(15)==0x21  # host still accessible
        bus.release_at=0; await i.configure(400_000)
        assert (await i.transfer(0x48,b"\xaa")).status=="success"
    finally: bus.close()


@cocotb.test()
async def i2c_fifo_streaming_starvation_backpressure(dut):
    h=Host(dut); await h.reset()
    data=bytes(range(20))
    bus=Bus(dut,host=h,data=data)
    try:
        i=driver(h); await i.configure(400_000)
        deadline=i.clock()+.1
        await i.send(START,deadline)
        await i.send(write_command(0x91),deadline)
        assert await i.receive(deadline)&1==0
        # Fill RX and block the fifth PUSH while continuing to feed TX in order.
        for n in range(8):
            await i.send(read_command(False),deadline)
        await h.tick(7000)
        assert (await h.read(11))>>4==4
        held=(bus.starts,bus.stops,bus.rises,bus.falls)
        await h.tick(1200)
        assert held==(bus.starts,bus.stops,bus.rises,bus.falls)
        result=[]
        for n in range(20):
            result.append((await i.receive(deadline))>>1)
            if n+8<20:
                await i.send(read_command(n+8==19),deadline)
            if n%3==0:
                await h.tick(1500)
        assert bytes(result)==data
        held=(bus.starts,bus.stops,bus.rises,bus.falls)
        await h.tick(1200)
        assert held==(bus.starts,bus.stops,bus.rises,bus.falls), "TX starvation changed wires"
        await i.stop(deadline)
        assert bus.controller_acks==[0]*19+[1]
        assert await h.read(13)==0
        bus.check_timing()
    finally: bus.close()


# The upstream GL action greps results.xml for the literal word "failure",
# including passing testcase names. Keep that word out of this test's name.
@cocotb.test()
async def i2c_reset_mid_byte_and_permanent_scl_clear_rejected(dut):
    from cocotb.triggers import Timer
    h=Host(dut); await h.reset()
    bus=Bus(dut,host=h)
    try:
        i=driver(h,timeout=.001); await i.configure(400_000)
        deadline=i.clock()+.001
        await i.send(START,deadline)
        await i.send(write_command(0x90),deadline)
        for _ in range(100):
            if bus.rises>=3: break
            await h.tick(10)
        assert bus.rises>=3
        dut.rst_n.value=0; await Timer(1,unit='ns')
        assert int(dut.uio_oe.value)==0
        await h.tick(2); dut.rst_n.value=1
        h.control(0); await h.tick(2)
        await i.configure(400_000)
        assert (await i.transfer(0x48,b'\x55')).status=='success'
        bus.stuck_scl=True; await h.tick(10)
        assert (await i.transfer(0x48,b'\x55')).status=='bus_busy'
        assert (await i.bus_clear()).status=='bus_clear_failed'
        assert int(dut.uio_oe.value)&0xf0==0
        assert await h.read(15)==0x21
        bus.stuck_scl=False
        await i.configure(400_000)
        assert (await i.transfer(0x48,read=2)).data==b'\x12\x34'
    finally: bus.close()


@cocotb.test()
async def i2c_asynchronous_target_phases_and_rise_budget(dut):
    for phase, rise, data_delay in ((1,20,20),(3,295,205),(7,175,85)):
        h=Host(dut); await h.reset()
        bus=Bus(dut,host=h,phase_ns=phase,rise_ns=rise,data_delay_ns=data_delay,
                data=b'\xa5\x5a',stretches={1:3355,9:1315})
        try:
            i=driver(h,timeout=.001); await i.configure(400_000)
            result=await i.transfer(0x48,b'\x80',read=2)
            assert result==Result('success',3,b'\xa5\x5a')
            assert bus.bytes==[0x90,0x80,0x91]
            assert bus.controller_acks==[0,1]
            assert bus.starts==2 and bus.stops==1
            bus.check_timing()
        finally: bus.close()
