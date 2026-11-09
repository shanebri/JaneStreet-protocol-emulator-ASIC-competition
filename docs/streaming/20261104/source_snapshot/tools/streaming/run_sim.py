"""Fresh pin-level streaming runs on RTL or the exact active qualified netlist."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
ACTIVE=ROOT/'test/sim_build/timing_headroom_20261104_01/production'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--gates',action='store_true')
    p.add_argument('--benchmark',action='store_true')
    p.add_argument('--depth',type=int,choices=(4,8),default=4)
    p.add_argument('--module',choices=('test_streaming','test_streaming_long','test_usb_ls_tx'),default='test_streaming')
    a=p.parse_args(); out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    if a.gates and a.depth!=4: p.error('Only the active four-word netlist is qualified')
    from cocotb_tools.runner import get_runner
    os.environ['STREAM_DEPTH']=str(a.depth)
    os.environ['STREAM_RESULTS']=str(out/'measurements.json')
    os.environ['STREAM_GATES']='1' if a.gates else '0'
    os.environ['STREAM_BENCHMARK']='1' if a.benchmark else '0'
    defines={'COCOTB_RUNNER':1}
    software=[*sorted((ROOT/'tools/streaming').glob('*.py')),
              ROOT/'examples/uart_packed_stream.asm',ROOT/'examples/spi_packed_stream.asm',
              ROOT/'examples/usb_ls_tx_symbols.asm',ROOT/'test'/(a.module+'.py'),
              ROOT/'test/test.py',ROOT/'tools/pio_host.py',ROOT/'tools/pioasm.py']
    software=sorted(set([*software,ROOT/'test/test_streaming.py']))
    hashes={str(s.relative_to(ROOT)):hashlib.sha256(s.read_bytes()).hexdigest() for s in software}
    for source in software:
        target=out/'sources'/source.relative_to(ROOT)
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    (out/'software_inputs.json').write_text(json.dumps(hashes,indent=2)+'\n')
    if a.gates:
        state=next((ACTIVE/'run').glob('*-openroad-stapostpnr/state_out.json'))
        netlist=Path(json.loads(state.read_text())['nl'])
        pdk=Path('/home/shane/eda/pdk-2bbec755/ihp-sg13cmos5l/libs.ref')
        sources=[pdk/'sg13cmos5l_stdcell/verilog/sg13cmos5l_udp.v',
                 pdk/'sg13cmos5l_io/verilog/sg13cmos5l_io.v',
                 pdk/'sg13cmos5l_stdcell/verilog/sg13cmos5l_stdcell.v',netlist]
        defines.update(GL_TEST=1,FUNCTIONAL=1,SIM=1)
    else:
        design=ROOT if a.depth==4 else ROOT/'test/sim_build/deep_fifo_20261104_01/depth8'
        lines=(design/'info.yaml').read_text().split('  source_files:\n',1)[1].splitlines()
        sources=[design/'src'/s.split('"')[1] for s in lines if s.startswith('    - ')]
    sources.append(ROOT/'test/tb.v')
    sys.path.insert(0,str(ROOT/'test'));sys.path.insert(0,str(ROOT/'tools'))
    runner=get_runner('icarus')
    runner.build(sources=sources,hdl_toplevel='tb',build_dir=out/'build',
                 defines=defines,timescale=('1ns','1ps'),always=True)
    results=runner.test(hdl_toplevel='tb',test_module=a.module,test_dir=out,results_xml=out/'results.xml')
    report=ET.parse(results)
    receipt=dict(kind='functional_gate_simulation' if a.gates else 'rtl_simulation',
        tests=len(report.findall('.//testcase')),failures=len(report.findall('.//failure')),
        errors=len(report.findall('.//error')),skipped=len(report.findall('.//skipped')),
        source_sha256={str(s):hashlib.sha256(s.read_bytes()).hexdigest() for s in sources})
    receipt['software_sha256']=hashes
    receipt['software_changes']=[str(s.relative_to(ROOT)) for s in software
        if hashlib.sha256(s.read_bytes()).hexdigest()!=hashes[str(s.relative_to(ROOT))]]
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    if not receipt['tests'] or receipt['software_changes'] or any(receipt[k] for k in ('failures','errors','skipped')):
        raise RuntimeError('Streaming regression did not pass completely')
    print('PASS',receipt['kind'],receipt['tests'])


if __name__=='__main__': main()
