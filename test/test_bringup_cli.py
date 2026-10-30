"""Exercise the ad-hoc loader against real package-pin RTL."""
import argparse
import cocotb
from test_bringup import Pins
from pioasm import assemble
from bringup.firmware import execute


@cocotb.test()
async def firmware_loader(dut):
    args=argparse.Namespace(no_reset=False,engine=1,preset='none',set=[],
                            tx=[0x1234abcd],rx=1,start=True,timeout=5)
    await execute(Pins(dut),args,assemble('pull block\nmov isr, osr\npush block\nhalt'))
