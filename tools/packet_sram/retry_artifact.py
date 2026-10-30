"""Rerun exact-artifact qualification after a local simulation-runtime failure.

All original strict physical/view checks and old/new gate tests run again. No
native-flow failure is bypassed and no input netlist, layout or SDC is modified.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
from gate_runtime import gate_environment,provenance
import production_trial as trial

root=trial.REPO/'test/sim_build/packet_sram_buffered_production_20261030_01'
if not (root/'run/final/metrics.json').is_file():
    raise ValueError('No completed final production artifact to qualify')
out=root/'qualification_runtime_02'
if out.exists(): raise ValueError('Fresh qualification output required')
command=[sys.executable,str(root/'tools/timing/qualify_gds_artifact.py'),'--run',str(root/'run'),
    '--out',str(out),'--pdk-root',str(trial.PDK),'--support-tools',str(trial.TOOLING/'tt'),
    '--precheck-python',str(trial.TOOLING/'precheck-venv/bin/python'),'--test-python','/home/shane/eda/pio-test-venv/bin/python',
    '--test-source',str(root/'test')]
(root/'retry_gate_runtime.json').write_text(json.dumps(dict(runtime=provenance(),command=command),indent=2)+'\n')
with (root/'artifact_qualification_runtime_02.log').open('w') as log:
    subprocess.run(command,cwd=root,env=gate_environment(os.environ),stdout=log,stderr=subprocess.STDOUT,check=True)
print('Exact-artifact qualification passed with documented simulator runtime; exact fast macro model remains a release block')
