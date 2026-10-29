"""Clean production build and final qualification, from frozen active sources."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

repo = Path(__file__).resolve().parents[3]
root = repo/'test/sim_build/production_final_20261028_01'
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
    (root/'.github/workflows').mkdir(parents=True)
    shutil.copy2(repo/'.github/workflows/gds.yaml', root/'.github/workflows/gds.yaml')
    (root/'tt').symlink_to(tooling/'tt', target_is_directory=True)
    if json.loads((root/'src/config.json').read_text())['meta']['flow'] != 'PIOClosure':
        raise ValueError('Production flow is not activated')
    files = [p for folder in ('src','tools/timing','test') for p in (root/folder).rglob('*') if p.is_file()]
    files += [root/'info.yaml', root/'librelane_plugin_pio.py', root/'.github/workflows/gds.yaml']
    (root/'frozen_inputs.json').write_text(json.dumps({str(p.relative_to(root)):
        hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}, indent=2)+'\n')
    command = ['/nix/var/nix/profiles/default/bin/nix', 'develop', '--offline', '--command',
               'python3', str(Path(__file__).resolve()), '--worker']
    with (root/'launcher.log').open('w') as log:
        proc = subprocess.Popen(command, cwd='/home/shane/eda/librelane-3.1.0.dev3',
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
    (root/'process.json').write_text(json.dumps(dict(pid=proc.pid, command=command), indent=2)+'\n')
    print('Detached clean production build and qualification', proc.pid)
else:
    state = dict(status='running', scope='clean production build and exact-artifact qualification', commands=[])
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
        state['status'] = 'qualifying'; save()
        command = [sys.executable, str(root/'tools/timing/qualify_gds_artifact.py'),
            '--run', str(root/'run'), '--out', str(root/'qualification'),
            '--pdk-root', '/home/shane/eda/pdk-2bbec755', '--support-tools', str(tooling/'tt'),
            '--precheck-python', str(tooling/'precheck-venv/bin/python'),
            '--test-python', '/home/shane/eda/pio-test-venv/bin/python', '--test-source', str(root/'test')]
        state['commands'].append(command); save()
        subprocess.run(command, cwd=root, check=True)
        state['status'] = 'complete'
    except Exception as exc:
        state.update(status='failed', error=str(exc)); raise
    finally:
        save()


