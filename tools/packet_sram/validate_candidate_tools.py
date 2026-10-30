"""Validate macro-aware replay/clock audits on an immutable extracted artifact."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
from install_candidate_tools import install

repo=Path(__file__).resolve().parents[2]
base=repo/'test/sim_build/packet_sram_repair_20261030_04'
root=repo/'test/sim_build/packet_tool_validation_20261030_01'
root.mkdir(exist_ok=False)
shutil.copytree(base/'tools/timing',root/'tools/timing',ignore=shutil.ignore_patterns('__pycache__'))
install(root)
commands=[
    ['openroad','-exit','-python',str(root/'tools/timing/audit_clock_tree.py'),'--odb',str(base/'extracted_diagnostic_01/run/1-openroad-fillinsertion/tt_um_shanebri_top.odb'),
     '--expected-odb',str(base/'run/13-openroad-floorplan/tt_um_shanebri_top.odb'),'--out',str(root/'clock_audit.json')],
    [sys.executable,'-B',str(root/'tools/timing/replay.py'),'--run',str(base/'extracted_diagnostic_01/run'),
     '--macro-config',str(base/'run/resolved.json'),'--pdk-root','/home/shane/eda/pdk-2bbec755','--out',str(root/'replay'),'--reset-active']]
for i,command in enumerate(commands):
    with (root/f'validation_{i}.log').open('w') as log:
        subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    print((root/f'validation_{i}.log').read_text()[-1400:],flush=True)
sys.path.insert(0,str(root/'tools/timing'))
from collect_implementation import selected_metrics,validate_replay
state=json.loads((base/'extracted_diagnostic_01/run/3-openroad-stapostpnr/state_out.json').read_text())
manifest=json.loads((root/'replay/manifest.json').read_text())
validate_replay(manifest,selected_metrics(state['metrics']))
print('PASS: macro-aware replay agrees with native extracted STA; full source clock pin set retained')
