"""Compile submission sources and run bring-up over the FPGA UART bridge."""
from pathlib import Path
import argparse
import sys
from xml.etree import ElementTree
from cocotb_tools.runner import get_runner

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--default-baud-link',action='store_true')
    args=parser.parse_args()
    cycles=434 if args.default_baud_link else 8
    sources=[]
    for line in (ROOT/'info.yaml').read_text().splitlines():
        if line.startswith('    - "'):
            sources.append(ROOT/'src'/line.split('"')[1])
    sources += [ROOT/'fpga'/name for name in ('byte_nibble_host.sv',
                'spi_test_uart_tx.sv','bringup_uart_rx.sv','bringup_bridge.sv')]
    runner=get_runner('icarus')
    runner.build(sources=sources, hdl_toplevel='bringup_bridge',
                 parameters={'BIT_CYCLES':cycles}, build_args=['-Wall','-Wno-timescale'],
                 build_dir=ROOT/'test/sim_build/bringup-serial',
                 timescale=('1ns','1ps'), always=True)
    report=runner.test(hdl_toplevel='bringup_bridge',test_module='test_bringup_serial',
                       test_dir=ROOT/'test',results_xml='bringup-default-baud.xml' if args.default_baud_link else 'bringup-serial.xml',
                       extra_env={'BRINGUP_BIT_CYCLES':str(cycles),
                                  'BRINGUP_LINK_ONLY':str(int(args.default_baud_link))})
    tree=ElementTree.parse(report)
    if not tree.findall('.//testcase') or tree.findall('.//failure') or tree.findall('.//error'):
        raise SystemExit(1)


if __name__=='__main__': main()
