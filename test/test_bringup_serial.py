"""Exercise every shared scenario through actual UART RTL and nibble adapter."""
import sys
import os
from pathlib import Path
from functools import reduce
from operator import xor
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Timer, FallingEdge, with_timeout
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from bringup.transport import SerialTransport
from bringup.scenarios import run, SCENARIOS

BIT_NS=20*int(os.environ.get('BRINGUP_BIT_CYCLES','8'))


class WireTransport(SerialTransport):
    def __init__(self, dut):
        super().__init__(None)
        self.dut=dut

    async def receive(self):
        result=bytearray()
        for _ in range(8):
            await FallingEdge(self.dut.uart_tx)
            await Timer(BIT_NS*1.5, unit='ns')
            value=0
            for i in range(8):
                value |= int(self.dut.uart_tx.value)<<i
                await Timer(BIT_NS, unit='ns')
            assert int(self.dut.uart_tx.value)==1, 'UART stop bit'
            result.append(value)
        return result

    async def command(self, op, address=0, value=0, *, status=0, corrupt=False):
        packet=bytes((0xc3,self.sequence,op,address,value&255,value>>8,0))
        packet+=bytes((reduce(xor,packet)^int(corrupt),))
        response=cocotb.start_soon(self.receive())
        for byte in packet:
            for bit in [0]+[(byte>>i)&1 for i in range(8)]+[1]:
                self.dut.uart_rx.value=bit
                await Timer(BIT_NS, unit='ns')
        reply=await with_timeout(response, 2, 'ms')
        assert reply[:3]==bytes((0xc3,self.sequence,status)), reply.hex()
        assert reduce(xor,reply)==0
        self.sequence=(self.sequence+1)&255
        return reply[3]


@cocotb.test()
async def serial_bringup(dut):
    dut.reset.value=1; dut.uart_rx.value=1; dut.dedicated_in.value=0
    cocotb.start_soon(Clock(dut.clk,20,unit='ns').start())
    await Timer(400,unit='ns')
    dut.reset.value=0
    await Timer(800,unit='ns')
    records=[]
    io=WireTransport(dut)
    # A truncated packet must not poison the next command indefinitely.
    for byte in (0xc3,0x7f):
        for bit in [0]+[(byte>>i)&1 for i in range(8)]+[1]:
            dut.uart_rx.value=bit
            await Timer(BIT_NS,unit='ns')
    await Timer(BIT_NS*25,unit='ns')
    await io.command(99,status=3)
    await io.command(2,15,1,status=1,corrupt=True)
    await io.reset()
    assert await io.read(15)==0x21
    await io.enable(False)
    await io.command(1,15,status=2)
    await io.enable(True)
    if os.environ.get('BRINGUP_LINK_ONLY')=='1':
        return  # Explicit default-baud link qualification, separate from smoke.
    await run(io,2201,records.append)
    assert len(records)==len(SCENARIOS)
