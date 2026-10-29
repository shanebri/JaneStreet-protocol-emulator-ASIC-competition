"""Clean integration candidate through the normal CLI; no archived physical state.

The frozen config selects the prepared flow. Repository production activation
and all independent final-artifact qualifications remain separate decisions.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

repo = Path(__file__).resolve().parents[3]
root = repo/'test/sim_build/production_candidate_20261028_02'
tooling = repo/'test/sim_build/production_tooling'
evidence = Path(__file__).resolve().parent
if '--worker' not in sys.argv:
    root.mkdir(parents=True, exist_ok=False)
    (root/'run').mkdir()
    for folder in ('src', 'tools/timing', 'test'):
        if folder == 'test':
            shutil.copytree(repo/folder, root/folder,
                ignore=shutil.ignore_patterns('sim_build', '__pycache__', '*.fst', '*.vcd', 'gate_level_netlist.v', 'results.xml'))
        else:
            shutil.copytree(repo/folder, root/folder, ignore=shutil.ignore_patterns('__pycache__'))
    for file in ('info.yaml', 'librelane_plugin_pio.py'):
        shutil.copy2(repo/file, root/file)
    for name in ('sink-local', 'fanout', 'last_fanout'):
        shutil.copy2(evidence/(name+'-structural-targets.json'), root/'tools/timing'/(name+'-targets.json'))
    (root/'tt').symlink_to(tooling/'tt', target_is_directory=True)
    config = json.loads((root/'src/config.json').read_text())
    config.update(meta={'flow': 'PIOClosure'}, PL_TIMING_DRIVEN=True, GRT_ADJUSTMENT=.25,
        OPENROAD_THREADS=8, MAGIC_EXT_USE_GDS=True,
        PIO_ECO_CONTRACT='dir::../tools/timing/sink-local-targets.json',
        PIO_INCREMENTAL_ECO_CONTRACTS=['dir::../tools/timing/fanout-targets.json',
                                      'dir::../tools/timing/last_fanout-targets.json'])
    (root/'src/config.json').write_text(json.dumps(config, indent=2)+'\n')
    files = [p for folder in ('src','tools/timing','test') for p in (root/folder).rglob('*') if p.is_file()]
    files += [root/'info.yaml', root/'librelane_plugin_pio.py']
    (root/'frozen_inputs.json').write_text(json.dumps({str(p.relative_to(root)):
        hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}, indent=2)+'\n')
    command = ['/nix/var/nix/profiles/default/bin/nix', 'develop', '--offline', '--command',
               'python3', str(Path(__file__).resolve()), '--worker']
    with (root/'launcher.log').open('w') as log:
        proc = subprocess.Popen(command, cwd='/home/shane/eda/librelane-3.1.0.dev3',
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
    (root/'process.json').write_text(json.dumps(dict(pid=proc.pid, command=command), indent=2)+'\n')
    print('Detached clean integration candidate', proc.pid)
else:
    state = dict(status='running', scope='clean integration candidate; qualification pending', commands=[])
    def save(): (root/'job.json').write_text(json.dumps(state, indent=2)+'\n')
    save()
    try:
        env = dict(os.environ, PYTHONPATH='', PATH=str(tooling/'venv/bin')+':'+os.environ['PATH'],
                   XDG_CACHE_HOME=str(root/'.cache'))
        command = [str(tooling/'venv/bin/python'), str(root/'tt/tt_tool.py'), '--create-user-config', '--ihp']
        state['commands'].append(command); save()
        subprocess.run(command, cwd=root, env=env, check=True)
        command = [sys.executable, '-m', 'librelane', '--pdk', 'ihp-sg13cmos5l', '--manual-pdk',
            '--pdk-root', '/home/shane/eda/pdk-2bbec755', '--run-tag', 'clean', '--force-run-dir',
            str(root/'run'), 'src/config_merged.json']
        state['commands'].append(command); save()
        subprocess.run(command, cwd=root, check=True)
        state['status'] = 'complete'
    except Exception as exc:
        state.update(status='failed', error=str(exc)); raise
    finally:
        save()

