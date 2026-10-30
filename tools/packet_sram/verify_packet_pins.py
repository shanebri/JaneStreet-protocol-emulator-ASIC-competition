"""Run the new packet regression through package pins with official SRAM models."""
from pathlib import Path
import shutil
import sys
from xml.etree import ElementTree
from cocotb_tools.runner import get_runner
import production_trial as trial

root=Path(sys.argv[1]).resolve()
shutil.copy2(Path(__file__).with_name('test_packet_pins.py'),root/'test/test_packet_pins.py')
for file in (trial.REPO/'tools').glob('*.py'): shutil.copy2(file,root/'tools'/file.name)
sources=[]
for line in (root/'info.yaml').read_text().split('  source_files:\n')[1].splitlines():
    if not line.startswith('    - '): break
    sources.append(root/'src'/line.split('"')[1])
models=trial.PDK/'ihp-sg13cmos5l/libs.ref/sg13cmos5l_sram/verilog'
sources += [models/'RM_IHPSG13_1P_64x16_c2.v',models/'RM_IHPSG13_1P_core_behavioral.v',root/'test/tb.v']
runner=get_runner('icarus')
runner.build(sources=sources,hdl_toplevel='tb',build_dir=root/'test/sim_build/packet_pins',
    defines={'COCOTB_RUNNER':1,'FUNCTIONAL':1},always=True,timescale=('1ns','1ps'))
results=runner.test(hdl_toplevel='tb',test_module='test_packet_pins',test_dir=root/'test',results_xml=root/'test/packet_results.xml')
tree=ElementTree.parse(results)
assert len(tree.findall('.//testcase'))==1
assert not any(tree.findall('.//'+tag) for tag in ('failure','error','skipped'))
