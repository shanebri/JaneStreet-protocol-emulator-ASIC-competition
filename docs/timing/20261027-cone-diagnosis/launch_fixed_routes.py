"""Preserve unaffected wires: matched control and one final fanout repair, sequential workers."""
import json
from pathlib import Path
import os
import shutil
import subprocess
import sys

repo=Path(__file__).resolve().parents[3]
root=repo/'test/sim_build/data_fixed_routes_20261028_01'
evidence=repo/'docs/timing/20261028-data-fixed-routes'
base=repo/'test/sim_build/data_incremental_20261027_03/incremental_fanout-01'
tool=repo/'tools/timing'
pdk='/home/shane/eda/pdk-2bbec755'
if '--worker' not in sys.argv:
    root.mkdir(parents=True,exist_ok=False)
    command=['/nix/var/nix/profiles/default/bin/nix','develop','--offline','--command',
             'python3',str(Path(__file__).resolve()),'--worker']
    with (root/'launcher.log').open('w') as log:
        proc=subprocess.Popen(command,cwd='/home/shane/eda/librelane-3.1.0.dev3',stdin=subprocess.DEVNULL,
            stdout=log,stderr=subprocess.STDOUT,start_new_session=True,
            env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    (root/'process.json').write_text(json.dumps(dict(pid=proc.pid,command=command),indent=2)+'\n')
    print('Detached incremental worker',proc.pid)
else:
    state=dict(status='running',pid=os.getpid(),cases={})
    def save(): (root/'job.json').write_text(json.dumps(state,indent=2)+'\n')
    save()
    try:
        for case in ('control','last_fanout'):
            name='incremental_'+case+'-01'; trial=root/name; out=evidence/name
            state['cases'][case]=dict(status='physical'); save()
            command=[sys.executable,str(tool/'incremental_trial.py'),'--base',str(base),
                     '--pdk-root',pdk,'--archive-root','/home/shane/eda/timing-20261024/current',
                     '--out',str(trial),'--case',case,'--preserve-routes']
            state['cases'][case]['command']=command; save()
            with (root/(case+'.log')).open('w') as log:
                subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
            manifest=json.loads((trial/'experiment.json').read_text())
            if manifest['status'] not in ('screen_complete','rejected_signoff'):
                raise ValueError('Incremental physical/audit failure: '+str(manifest))
            state['cases'][case]['status']='collecting'; save()
            with (root/(case+'_collect.log')).open('w') as log:
                subprocess.run([sys.executable,str(tool/'closure_collect.py'),'--trial',str(trial),
                    '--pdk-root',pdk,'--out',str(out/'sta')],stdout=log,stderr=subprocess.STDOUT,check=True)
            for file in ('experiment.json','recipe.json','runner.py','eco.tcl','eco_audit.json','eco_audit.log'):
                shutil.copy2(trial/file,out/file)
            final=json.loads(next((trial/'run').glob('*-openroad-stapostpnr/state_out.json')).read_text())
            with (out/'clock_audit.log').open('w') as log:
                subprocess.run(['openroad','-no_init','-exit','-python',str(tool/'audit_clock_tree.py'),
                    '--odb',final['odb'],'--out',str(out/'clock_audit.json')],stdout=log,stderr=subprocess.STDOUT,check=True)
            state['cases'][case].update(status='complete',strict_signoff_exit=manifest['signoff_exit']); save()
        state['status']='complete'
    except Exception as exc:
        state.update(status='failed',error=str(exc))
        raise
    finally: save()


