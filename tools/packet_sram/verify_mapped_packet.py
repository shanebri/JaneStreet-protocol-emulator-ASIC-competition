"""Check vendor-model gate simulation and packet Makefile plumbing early."""
import json
import os
from pathlib import Path
import shutil
import subprocess
from xml.etree import ElementTree

repo=Path(__file__).resolve().parents[2]
candidate=repo/'test/sim_build/packet_sram_buffered_production_20261030_01'
mapped=repo/'test/sim_build/packet_sram_buffered_20261030_01/run/06-yosys-synthesis/tt_um_shanebri_top.nl.v'
out=candidate/'mapped_packet_check_02'; out.mkdir(exist_ok=False)
shutil.copytree(candidate/'test',out/'test',ignore=shutil.ignore_patterns('sim_build','__pycache__','*.fst','*.vcd','results.xml','packet_results.xml','gate_level_netlist.v'))
shutil.copytree(candidate/'src',out/'src')
shutil.copytree(candidate/'examples',out/'examples')
(out/'tools').mkdir()
for py in (candidate/'tools').glob('*.py'): shutil.copy2(py,out/'tools'/py.name)
shutil.copy2(mapped,out/'test/gate_level_netlist.v')
env=dict(os.environ,PDK_ROOT='/home/shane/eda/pdk-2bbec755',PDK='ihp-sg13cmos5l',PYTHONPATH='',PYTHONDONTWRITEBYTECODE='1',
    PATH='/home/shane/eda/pio-test-venv/bin:'+os.environ['PATH'])
expat=[p for p in Path('/nix/store').glob('*-expat-*/lib') if (p/'libexpat.so.1').is_file()]
assert len(expat)==1,'Gate runtime expat dependency must be explicit and unambiguous'
env['LD_LIBRARY_PATH']=str(expat[0])+':'+env.get('LD_LIBRARY_PATH','')
with (out/'gate_test.log').open('w') as log:
    subprocess.run(['make','-B','GATES=yes','COCOTB_TEST_MODULES=test_packet_pins','COCOTB_RESULTS_FILE=packet_results.xml'],
        cwd=out/'test',env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
tree=ElementTree.parse(out/'test/packet_results.xml')
assert len(tree.findall('.//testcase'))==1 and not any(tree.findall('.//'+tag) for tag in ('failure','error','skipped'))
(out/'manifest.json').write_text(json.dumps(dict(status='pass',scope='mapped-netlist packet functional check; not routed GDS gate signoff',netlist=str(mapped)),indent=2)+'\n')
print('PASS: mapped gate packet test, vendor SRAM model, concurrent engine cycles, and separate result file')
