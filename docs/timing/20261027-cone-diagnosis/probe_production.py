"""Probe clean synthesis/configuration through the real production entrypoint.

Only the frozen probe config selects the candidate flow. Stops after native
structural synthesis checks; does not claim production timing qualification.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

repo=Path(__file__).resolve().parents[3]
root=repo/'test/sim_build/production_probe_20261027_02'
tooling=repo/'test/sim_build/production_tooling'
if '--worker' not in sys.argv:
    root.mkdir(parents=True,exist_ok=False)
    (root/'run').mkdir()
    shutil.copytree(repo/'src',root/'src')
    shutil.copy2(repo/'info.yaml',root/'info.yaml')
    shutil.copy2(repo/'librelane_plugin_pio.py',root/'librelane_plugin_pio.py')
    shutil.copytree(repo/'tools/timing',root/'tools/timing',ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(repo/'docs/timing/20261027-cone-diagnosis/sink-local-structural-targets.json',root/'tools/timing/production_targets.json')
    (root/'tt').symlink_to(tooling/'tt',target_is_directory=True)
    config=json.loads((root/'src/config.json').read_text())
    config.update(meta={'flow':'PIOClosure'},PL_TIMING_DRIVEN=True,GRT_ADJUSTMENT=.25,
        OPENROAD_THREADS=8,MAGIC_EXT_USE_GDS=True,PIO_ECO_CONTRACT='dir::../tools/timing/production_targets.json')
    (root/'src/config.json').write_text(json.dumps(config,indent=2)+'\n')
    command=['/nix/var/nix/profiles/default/bin/nix','develop','--offline','--command',
             'python3',str(Path(__file__).resolve()),'--worker']
    with (root/'launcher.log').open('w') as log:
        proc=subprocess.Popen(command,cwd='/home/shane/eda/librelane-3.1.0.dev3',stdin=subprocess.DEVNULL,
            stdout=log,stderr=subprocess.STDOUT,start_new_session=True,
            env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    (root/'process.json').write_text(json.dumps(dict(pid=proc.pid,command=command),indent=2)+'\n')
    print('Detached production configuration probe',proc.pid)
else:
    state=dict(status='running',scope='clean synthesis/configuration probe only',commands=[])
    def save(): (root/'job.json').write_text(json.dumps(state,indent=2)+'\n')
    save()
    try:
        env=dict(os.environ,PYTHONPATH='',PATH=str(tooling/'venv/bin')+':'+os.environ['PATH'],
                 XDG_CACHE_HOME=str(root/'.cache'))
        command=[str(tooling/'venv/bin/python'),str(root/'tt/tt_tool.py'),'--create-user-config','--ihp']
        state['commands'].append(command); save()
        subprocess.run(command,cwd=root,env=env,check=True)
        command=[sys.executable,'-m','librelane','--pdk','ihp-sg13cmos5l','--manual-pdk',
            '--pdk-root','/home/shane/eda/pdk-2bbec755','--run-tag','probe','--force-run-dir',str(root/'run'),
            '--to','Checker.NetlistAssignStatements','src/config_merged.json']
        state['commands'].append(command); save()
        subprocess.run(command,cwd=root,check=True)
        state['status']='complete'
    except Exception as exc:
        state.update(status='failed',error=str(exc))
        raise
    finally:
        state['source_sha256']={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in (root/'src').rglob('*') if p.is_file()}
        save()
