"""Durable launcher for the bounded shared-acceptance experiment."""
import json
from pathlib import Path
import subprocess
import sys
import os

repo = Path(__file__).resolve().parents[3]
root = repo/'test/sim_build/data_upstream_20261027'
evidence = repo/'docs/timing/20261027-data-upstream'
tool = repo/'tools/timing'
sdk = Path('/home/shane/eda/librelane-3.1.0.dev3')
if '--worker' not in sys.argv:
    root.mkdir(parents=True, exist_ok=False)
    command = ['/nix/var/nix/profiles/default/bin/nix','develop','--offline','--command',
               'python3',str(Path(__file__).resolve()),'--worker']
    with (root/'launcher.log').open('w') as log:
        process = subprocess.Popen(command, cwd=sdk, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    (root/'process.json').write_text(json.dumps(dict(pid=process.pid, command=command, cwd=str(sdk)),indent=2)+'\n')
    print('Detached worker', process.pid, root)
else:
    state = dict(status='running', pid=os.getpid(), commands=[])
    commands = [
        [sys.executable,str(tool/'data_eco_suite.py'),'--suite','upstream','--jobs','2',
         '--base',str(repo/'test/sim_build/clock_factors/clock_split8-01'),
         '--prepared',str(repo/'test/sim_build/data_eco_20261027/input'),
         '--archive-root','/home/shane/eda/timing-20261024/current',
         '--pdk-root','/home/shane/eda/pdk-2bbec755','--root',str(root),'--evidence',str(evidence)],
        [sys.executable,str(tool/'summarize_data_eco.py'),'--suite','upstream','--root',str(root),
         '--evidence',str(evidence),'--reference-metrics',
         str(repo/'docs/timing/20261026-clock-factors/clock_split8-01/sta/metrics.json')]]
    for command in commands:
        state['commands'].append(command)
        (root/'job.json').write_text(json.dumps(state,indent=2)+'\n')
        result = subprocess.run(command)
        if result.returncode:
            state.update(status='failed', returncode=result.returncode)
            break
    else:
        state['status']='complete'
    (root/'job.json').write_text(json.dumps(state,indent=2)+'\n')
