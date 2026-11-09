"""Compile submission sources and run bring-up over the FPGA UART bridge."""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib
import json
import shutil
import sys
from xml.etree import ElementTree
from cocotb_tools.runner import get_runner

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--default-baud-link',action='store_true')
    parser.add_argument('--extended', action='store_true')
    parser.add_argument('--packet-feeder', action='store_true')
    parser.add_argument('--out', type=Path, help='fresh simulation directory')
    parser.add_argument('--test-filter', help='explicit diagnostic subset, recorded in run.json')
    args=parser.parse_args()
    if sum((args.extended,args.default_baud_link,args.packet_feeder)) > 1:
        parser.error('choose one simulation suite')
    cycles=434 if args.default_baud_link else 8
    sources=[]
    for line in (ROOT/'info.yaml').read_text().splitlines():
        if line.startswith('    - "'):
            sources.append(ROOT/'src'/line.split('"')[1])
    sources += [ROOT/'fpga'/name for name in ('byte_nibble_host.sv',
                'spi_test_uart_tx.sv','bringup_uart_rx.sv','bringup_trace.sv',
                'packet_feeder.sv','packet_feeder_bank.sv','bringup_bridge.sv')]
    sources.append(ROOT/'test/bringup_bridge_tb.sv')
    kind='feeder' if args.packet_feeder else ('extended' if args.extended else ('default-baud' if args.default_baud_link else 'smoke'))
    out=(args.out or ROOT/'test/sim_build'/('bringup-'+kind)/datetime.now().strftime('%Y%m%d-%H%M%S-%f')).resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out/'.gitignore').write_text('*\n')
    metadata=dict(status='RUNNING', evidence_kind='simulation', kind=kind,
                  test_filter=args.test_filter, started=datetime.now(timezone.utc).isoformat(),
                  source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    (out/'run.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print('Simulation evidence:',out,flush=True)
    try:
        runner=get_runner('icarus')
        runner.build(sources=sources, hdl_toplevel='bringup_bridge_tb',
                     parameters={'BIT_CYCLES':cycles, 'TRACE_DEPTH':8192 if args.packet_feeder else (1024 if args.extended else 256),
                                 'FEEDER_ENABLED':int(args.packet_feeder)},
                     build_args=['-Wall','-Wno-timescale'], build_dir=out,
                     timescale=('1ns','1ps'), always=True,log_file=out/'build.log')
        report=runner.test(hdl_toplevel='bringup_bridge_tb',
            test_module='test_bringup_feeder' if args.packet_feeder else ('test_bringup_extended' if args.extended else 'test_bringup_serial'),
            test_dir=ROOT/'test', results_xml=str(out/'results.xml'), test_filter=args.test_filter,
            log_file=out/'simulator.log',
            extra_env={'BRINGUP_BIT_CYCLES':str(cycles),'BRINGUP_LINK_ONLY':str(int(args.default_baud_link)),
                       'BRINGUP_SIM_OUT':str(out)})
        tree=ElementTree.parse(report)
        metadata['tests']=len(tree.findall('.//testcase'))
        metadata['failures']=len(tree.findall('.//failure'))+len(tree.findall('.//error'))
        metadata['skips']=len(tree.findall('.//skipped'))
        metadata['executed_tests'] = metadata['tests']-metadata['skips']
        metadata['scope'] = 'diagnostic subset' if args.test_filter else 'complete suite'
        if not metadata['executed_tests'] or metadata['failures'] or (metadata['skips'] and not args.test_filter):
            raise RuntimeError('simulation failed; inspect the retained simulator.log and results.xml')
        if not args.test_filter and metadata['tests'] != (6 if args.packet_feeder else (7 if args.extended else 1)):
            raise RuntimeError('unexpected regression test count')
        metadata['status']='PASS'
    except BaseException as exc:
        metadata.update(status='FAIL',error=str(exc))
        raise
    finally:
        metadata['finished']=datetime.now(timezone.utc).isoformat()
        (out/'run.json').write_text(json.dumps(metadata,indent=2)+'\n')
        if (out/'results.xml').exists():
            name='bringup-feeder.xml' if args.packet_feeder else ('bringup-extended.xml' if args.extended else ('bringup-default-baud.xml' if args.default_baud_link else 'bringup-serial.xml'))
            shutil.copy2(out/'results.xml',ROOT/'test'/name)


if __name__=='__main__': main()
