"""Reuse the completed audited control; run one adaptive electrical trial."""
import json
from pathlib import Path
import subprocess
import sys
import shutil
import os

repo=Path(__file__).resolve().parents[3]
root=repo/'test/sim_build/data_fanout_tail_20261027'
evidence=repo/'docs/timing/20261027-data-fanout-tail'
control='electrical_sink_local-01'
previous=repo/'test/sim_build/data_sink_local_20261027'
if '--worker' not in sys.argv:
    if json.loads((previous/'job.json').read_text())['status']!='complete':
        raise ValueError('Prior audited comparison incomplete')
    root.mkdir(parents=True,exist_ok=False)
    (root/control).symlink_to(previous/control,target_is_directory=True)
    shutil.copytree(repo/'docs/timing/20261027-data-sink-local'/control,evidence/control)
    (root/'reused_control.json').write_text(json.dumps(dict(trial=str(previous/control),
        comparison=str(repo/'docs/timing/20261027-data-sink-local/comparison.json')),indent=2)+'\n')
    command=['/nix/var/nix/profiles/default/bin/nix','develop','--offline','--command',
             'python3',str(Path(__file__).resolve()),'--worker']
    with (root/'launcher.log').open('w') as log:
        proc=subprocess.Popen(command,cwd='/home/shane/eda/librelane-3.1.0.dev3',stdin=subprocess.DEVNULL,
                              stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    (root/'process.json').write_text(json.dumps(dict(pid=proc.pid,command=command),indent=2)+'\n')
    print('Detached adaptive worker',proc.pid)
else:
    tool=repo/'tools/timing'
    commands=[
        [sys.executable,str(tool/'data_eco_suite.py'),'--suite','fanout_tail','--jobs','1',
         '--base',str(repo/'test/sim_build/clock_factors/clock_split8-01'),
         '--prepared',str(repo/'test/sim_build/data_eco_20261027/input'),
         '--archive-root','/home/shane/eda/timing-20261024/current','--pdk-root','/home/shane/eda/pdk-2bbec755',
         '--root',str(root),'--evidence',str(evidence)],
        [sys.executable,str(tool/'summarize_data_eco.py'),'--suite','fanout_tail','--root',str(root),
         '--evidence',str(evidence),'--reference-metrics',
         str(repo/'docs/timing/20261026-clock-factors/clock_split8-01/sta/metrics.json')]]
    state=dict(status='running',pid=os.getpid(),commands=commands)
    (root/'job.json').write_text(json.dumps(state,indent=2)+'\n')
    for command in commands:
        result=subprocess.run(command)
        if result.returncode:
            state.update(status='failed',returncode=result.returncode)
            break
    else: state['status']='complete'
    (root/'job.json').write_text(json.dumps(state,indent=2)+'\n')
