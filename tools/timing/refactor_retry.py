"""Retry all qualification checks on an unchanged completed clean-production GDS.

The failed attempt is retained. The only checker change is creating its report
directory before execution. A successful receipt is written only after the
entire precheck and all 39 exact-netlist gate tests pass and all inputs match.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
PDK = Path('/home/shane/eda/pdk-2bbec755')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def changed(root, manifest):
    return [name for name,expected in manifest.items() if sha(root/name) != expected]


def prepare(root, parent):
    root = root.resolve(); parent = parent.resolve()
    if (parent/'qualification_resume.json').exists():
        raise ValueError('A successful retry receipt already exists; never overwrite it')
    frozen = json.loads((parent/'frozen_inputs.json').read_text())
    if changed(parent, frozen):
        raise ValueError('Original clean-production sources changed')
    if not (parent/'run/final/metrics.json').is_file():
        raise ValueError('Original native production flow is incomplete')
    comparisons = list((parent/'run').glob('*-pio-routeacceptance/parent_comparison.json'))
    if len(comparisons) != 1 or json.loads(comparisons[0].read_text())['status'] != 'numeric_checks_pass':
        raise ValueError('Original clean-production run fails parent-margin acceptance')
    root.mkdir(parents=True, exist_ok=False)
    shutil.copytree(parent/'tools/timing', root/'tools/timing', ignore=shutil.ignore_patterns('__pycache__'))
    qualifier = root/'tools/timing/qualify_gds_artifact.py'
    before = qualifier.read_text()
    marker = "        (out/'tech').symlink_to("
    if before.count(marker) != 1 or "(out/'precheck/reports').mkdir" in before:
        raise ValueError('Unexpected original qualifier; cannot apply the output-directory-only repair')
    qualifier.write_text(before.replace(marker,
        "        (out/'precheck/reports').mkdir(parents=True, exist_ok=True)\n"+marker, 1))
    shutil.copy2(Path(__file__),root/'retry_runner.py')
    scope = dict(original_parent=str(parent), native_run=str((parent/'run').resolve()),
        original_job_sha256=sha(parent/'job.json'),
        frozen_inputs_manifest_sha256=sha(parent/'frozen_inputs.json'),
        tooling_path=json.loads((parent/'scope.json').read_text())['tooling_path'],
        repair='Create precheck report output directory; no check or acceptance predicate changed',
        original_qualifier_sha256=sha(parent/'tools/timing/qualify_gds_artifact.py'),
        corrected_qualifier_sha256=sha(qualifier), rerouted=False)
    (root/'scope.json').write_text(json.dumps(scope,indent=2)+'\n')
    files = [p for p in root.rglob('*') if p.is_file()]
    (root/'frozen_inputs.json').write_text(json.dumps({str(p.relative_to(root)):sha(p) for p in files},indent=2)+'\n')


def worker(root):
    if (root/'job.json').exists():
        raise ValueError('Qualification retry output was already attempted')
    scope=json.loads((root/'scope.json').read_text())
    parent=Path(scope['original_parent']); tooling=Path(scope['tooling_path'])
    frozen=json.loads((root/'frozen_inputs.json').read_text())
    original=json.loads((parent/'frozen_inputs.json').read_text())
    state=dict(status='qualifying',physical_signoff=False,candidate_promoted=False,commands=[],
               native_run=scope['native_run'],rerouted=False)
    def save(): (root/'job.json').write_text(json.dumps(state,indent=2)+'\n')
    save()
    try:
        if changed(root,frozen) or changed(parent,original) or sha(parent/'job.json')!=scope['original_job_sha256']:
            raise ValueError('Retry or original inputs changed before qualification')
        expat=Path('/nix/store/d8927sznk6qnqln6hl9p4d42h8pq49vg-expat-2.8.0/lib')
        if not (expat/'libexpat.so.1').is_file():
            raise ValueError('Pinned simulation-runtime dependency missing')
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',
                 LD_LIBRARY_PATH=':'.join(filter(None,(str(expat),os.environ.get('LD_LIBRARY_PATH','')))))
        command=[sys.executable,str(root/'tools/timing/qualify_gds_artifact.py'),
            '--run',scope['native_run'],'--out',str(root/'qualification'),'--pdk-root',str(PDK),
            '--support-tools',str(tooling/'tt'),'--precheck-python',str(tooling/'precheck-venv/bin/python'),
            '--test-python','/home/shane/eda/pio-test-venv/bin/python','--test-source',str(parent/'test')]
        state['commands'].append(command); save()
        with (root/'qualification.log').open('w') as log:
            subprocess.run(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        if changed(root,frozen) or changed(parent,original) or sha(parent/'job.json')!=scope['original_job_sha256']:
            raise ValueError('Inputs changed during qualification')
        qualification=root/'qualification/manifest.json'
        result=json.loads(qualification.read_text())
        if result['status']!='complete' or any(sha(Path(p))!=expected for p,expected in result['sha256'].items()):
            raise ValueError('Incomplete or modified successful qualification')
        source=next((parent/'run').glob('*-openroad-stapostpnr/state_out.json'))
        receipt=dict(status='complete',physical_signoff=True,frozen_input_changes=[],
            native_run=scope['native_run'],original_job_sha256=scope['original_job_sha256'],
            frozen_inputs_manifest_sha256=scope['frozen_inputs_manifest_sha256'],
            qualification_manifest=str(qualification),qualification_manifest_sha256=sha(qualification),
            run_state_sha256=sha(source),retry_scope=str(root/'scope.json'),rerouted=False)
        with (parent/'qualification_resume.json').open('x') as stream:
            json.dump(receipt,stream,indent=2); stream.write('\n')
        state.update(status='complete',physical_signoff=True,frozen_input_changes=[])
    except Exception as exc:
        state.update(status='failed',error=str(exc),physical_signoff=False)
    finally:
        save()
    return int(not state['physical_signoff'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parent',type=Path)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--launch',action='store_true')
    p.add_argument('--worker',action='store_true')
    a=p.parse_args(); root=a.out.resolve()
    if a.worker:
        return worker(root)
    if not a.parent or not root.is_relative_to((REPO/'test/sim_build').resolve()):
        p.error('Require original parent and a fresh output inside test/sim_build')
    prepare(root,a.parent)
    if a.launch:
        command=['/nix/var/nix/profiles/default/bin/nix','develop','--offline','--command',
                 'python3','-B',str(root/'retry_runner.py'),'--out',str(root),'--worker']
        with (root/'launcher.log').open('w') as log:
            proc=subprocess.Popen(command,cwd='/home/shane/eda/librelane-3.1.0.dev3',stdin=subprocess.DEVNULL,
                stdout=log,stderr=subprocess.STDOUT,start_new_session=True,
                env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
        (root/'process.json').write_text(json.dumps(dict(pid=proc.pid,command=command),indent=2)+'\n')
        print('Launched complete qualification retry on unchanged GDS',proc.pid)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
