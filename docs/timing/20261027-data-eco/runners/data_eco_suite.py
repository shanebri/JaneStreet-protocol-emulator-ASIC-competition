"""Finish the critical pair, then run single-source electrical ECOs, four at a time."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from data_eco_trial import recipes


def choose_attempt(root,name):
    candidates=sorted(root.glob(name+'-[0-9][0-9]'))
    completed=[v for v in candidates if (v/'experiment.json').exists() and
        json.loads((v/'experiment.json').read_text())['status'] in ('screen_complete','rejected_signoff')
        and (v/'eco_audit.json').exists()]
    if completed:
        return completed[-1]
    attempt=max((int(v.name.rsplit('-',1)[1]) for v in candidates),default=0)+1
    return root/f'{name}-{attempt:02d}'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('base','prepared','archive-root','pdk-root','root','evidence'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--jobs',type=int,default=4)
    a=p.parse_args()
    if not 1<=a.jobs<=4:
        p.error('Use one to four workers, each with eight OpenROAD threads')
    tool=Path(__file__).resolve().parent
    a.evidence.mkdir(parents=True,exist_ok=True)
    names=list(recipes())
    critical=names[:3]
    while any(not (a.root/f'{n}-01/experiment.json').exists() for n in critical) or any(
              json.loads(path.read_text())['status']=='running'
              for path in a.root.glob('*-*/experiment.json')):
        time.sleep(5)
    state={}; lock=threading.Lock()

    def update(name,**values):
        with lock:
            state.setdefault(name,{}).update(values)
            temporary=a.root/'suite_state.tmp'
            temporary.write_text(json.dumps(state,indent=2)+'\n')
            temporary.replace(a.root/'suite_state.json')
        print(name,values.get('status',''),flush=True)

    def one(name):
        try:
            trial=choose_attempt(a.root,name); out=a.evidence/trial.name
            manifest=trial/'experiment.json'
            if not manifest.exists():
                command=[sys.executable,str(tool/'data_eco_trial.py'),'--base',str(a.base),
                    '--prepared',str(a.prepared),'--archive-root',str(a.archive_root),
                    '--pdk-root',str(a.pdk_root),'--trial',name,'--out',str(trial),'--threads','8']
                update(name,status='physical',command=command)
                with (a.root/f'{name}.log').open('w') as log:
                    result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
                update(name,physical_exit=result.returncode)
            data=json.loads(manifest.read_text())
            if data['status'] not in ('screen_complete','rejected_signoff'):
                raise ValueError('Physical flow or logical audit failed: '+data['status'])
            update(name,status='collecting')
            if not (out/'sta/provenance.json').exists():
                with (a.root/f'{name}_collect.log').open('w') as log:
                    subprocess.run([sys.executable,str(tool/'closure_collect.py'),'--trial',str(trial),
                        '--pdk-root',str(a.pdk_root),'--out',str(out/'sta')],stdout=log,stderr=subprocess.STDOUT,check=True)
            for file in ('experiment.json','runner.py','eco.tcl','recipe.json','eco_audit.json','eco_audit.log'):
                shutil.copy2(trial/file,out/file)
            update(name,status='complete',strict_signoff_exit=data['signoff_exit'])
        except Exception as exc:
            update(name,status='failed',error=str(exc))

    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        futures=[pool.submit(one,n) for n in names]
        for future in as_completed(futures):
            future.result()
    if any(v['status']!='complete' for v in state.values()):
        p.exit(1,'Some experiments failed; inspect suite_state.json\n')
    print('All isolated physical screens and replay collections complete',flush=True)


if __name__=='__main__':
    main()
