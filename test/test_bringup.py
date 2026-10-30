"""Run the same host scenarios on the package-pin RTL testbench."""
import sys
from pathlib import Path
import cocotb
from test import Host
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from bringup.scenarios import run
from bringup.scenarios import SCENARIOS


class Pins:
    def __init__(self, dut):
        self.host, self.dut = Host(dut), dut

    async def reset(self): await self.host.reset()
    async def read(self, address): return await self.host.read(address)
    async def write(self, address, value): await self.host.write(address, value)
    async def wait(self, cycles): await self.host.tick(cycles)
    async def sample(self): return int(self.dut.uo_out.value)
    async def enable(self, value):
        self.host.control(0)
        self.dut.ena.value = int(value)
        await self.host.tick(2)


@cocotb.test()
async def bringup_smoke(dut):
    results=[]
    await run(Pins(dut), 2201, results.append)
    assert len(results)==len(SCENARIOS) and all(r['status']=='PASS' for r in results)
