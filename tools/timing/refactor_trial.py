"""Freeze qualified sources and run an isolated, ordinary production increment.

Run from the existing pinned Nix environment through --launch. Neither a passing
screen nor positive slack promotes a candidate. The parent comparison precedes
route acceptance, and complete GDS qualification is required afterward.
"""
import argparse
import hashlib
import io
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile


REPO = Path(__file__).resolve().parents[2]
QUALIFIED = "bb7c5ef3c54a7ae2733bbfae82aa940016375007"
PDK = Path("/home/shane/eda/pdk-2bbec755")
TOOLING = REPO / "test/sim_build/production_tooling"
PARENT = REPO / "docs/timing/20261030-control-refactor/qualified-parent/69-openroad-stapostpnr/state_out.json"
PARENT_SHA256 = 'af8ced2439790ea47598651acacfbb0eb9d9848a858972a1124358e074ec0ae5'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("Expected exactly one patch location: " + old[:100])
    return text.replace(old, new, 1)


def validated_parent(root):
    """Validate a normal completion or a complete same-artifact qualification retry.

    A retry preserves the failed job and binds the successful qualification to
    the original clean run, immutable source manifest and original job hash.
    No physical checks or failing implementation may be bypassed this way.
    """
    from check_signoff import find_state, check_metrics
    root = root.resolve()
    job_path = root/'job.json'
    if not job_path.is_file():
        raise ValueError('Incremental parent lacks complete clean production/GDS qualification')
    job = json.loads(job_path.read_text())
    qualification_path = root/'qualification/manifest.json'
    receipt = None
    if job.get('status') != 'complete' or job.get('physical_signoff') is not True:
        retry = root/'qualification_resume.json'
        if not retry.is_file():
            raise ValueError('Incremental parent lacks complete clean production/GDS qualification')
        receipt = json.loads(retry.read_text())
        if (receipt.get('status') != 'complete' or receipt.get('physical_signoff') is not True
                or receipt.get('frozen_input_changes') != []):
            raise ValueError('Incremental parent lacks complete clean production/GDS qualification')
        if receipt.get('original_job_sha256') != sha(job_path):
            raise ValueError('Qualification retry original attempt changed')
        if receipt.get('frozen_inputs_manifest_sha256') != sha(root/'frozen_inputs.json'):
            raise ValueError('Qualification retry original source manifest changed')
        qualification_path = Path(receipt['qualification_manifest'])
        if receipt.get('qualification_manifest_sha256') != sha(qualification_path):
            raise ValueError('Qualification retry successful manifest changed')
    if not qualification_path.is_file():
        raise ValueError('Incremental parent lacks complete clean production/GDS qualification')
    qualification = json.loads(qualification_path.read_text())
    if job.get('frozen_input_changes') != [] or qualification.get('status') != 'complete':
        raise ValueError('Incremental parent lacks complete clean production/GDS qualification')
    if receipt is not None:
        original_qualification = json.loads((root/'qualification/manifest.json').read_text())
        if original_qualification.get('sha256') != qualification.get('sha256'):
            raise ValueError('Qualification retry physical views differ from the original clean build')
    frozen = json.loads((root/'frozen_inputs.json').read_text())
    if any(sha(root/name) != expected for name,expected in frozen.items()):
        raise ValueError('Incremental parent frozen sources changed after qualification')
    if any(sha(Path(name)) != expected for name,expected in qualification['sha256'].items()):
        raise ValueError('Incremental parent qualified physical artifact changed')
    state = find_state((root/'run').resolve())
    if qualification['sha256'].get(str(state)) != sha(state) or check_metrics(json.loads(state.read_text())['metrics']):
        raise ValueError('Incremental parent state changed or fails strict checks')
    if receipt is not None:
        if receipt.get('native_run') != str((root/'run').resolve()) or receipt.get('run_state_sha256') != sha(state):
            raise ValueError('Qualification retry is for a different physical run')
    checks = qualification.get('checks', {})
    required = ('strict_metrics','native_routing_drc_antenna','independent_gds_lvs',
                'final_view_identity','pin_geometry','route_acceptance')
    if any(checks.get(name) != 'pass' for name in required):
        raise ValueError('Incremental parent lacks required physical qualification checks')
    if (checks.get('tt_precheck',{}).get('status') != 'pass'
            or checks.get('tt_precheck',{}).get('tests',0) < 1
            or checks.get('gate_tests',{}).get('status') != 'pass'
            or checks.get('gate_tests',{}).get('tests') != 39
            or checks.get('gate_tests',{}).get('netlist_sha256') != sha(Path(json.loads(state.read_text())['nl']))):
        raise ValueError('Incremental parent lacks complete precheck and exact-netlist gate tests')
    return state, qualification_path


def freeze(root, variant, passing_parent=None):
    parent_state = PARENT
    if passing_parent is None and sha(parent_state) != PARENT_SHA256:
        raise ValueError('Qualified baseline reference was changed')
    if passing_parent is not None:
        passing_parent = passing_parent.resolve()
        parent_state, _ = validated_parent(passing_parent)
    root.mkdir(parents=True, exist_ok=False)
    (root / "run").mkdir()
    archive = subprocess.check_output(
        ["git", "archive", QUALIFIED, "src", "tools", "test", "examples", "info.yaml",
         "librelane_plugin_pio.py", ".github/workflows/gds.yaml"], cwd=REPO)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            dest = (root / member.name).resolve()
            if not dest.is_relative_to(root.resolve()) or not (member.isfile() or member.isdir()):
                raise ValueError("Unsupported archive entry: " + member.name)
        tar.extractall(root, filter="data")
    (root / "tt").symlink_to(TOOLING / "tt", target_is_directory=True)
    parent = root / "parent/69-openroad-stapostpnr/state_out.json"
    parent.parent.mkdir(parents=True)
    shutil.copy2(parent_state, parent)
    shutil.copy2(REPO / "tools/packet_sram/compare_timing.py", root / "tools/timing/compare_timing.py")
    shutil.copy2(Path(__file__), root / "trial_runner.py")
    flow = root / "tools/timing/production_flow.py"
    flow.write_text(replace_once(flow.read_text(),
        "        with (Path(self.step_dir)/'qualification.log').open('w') as log:",
        """        parent = Path(self.config['DESIGN_DIR']).parent/'parent/69-openroad-stapostpnr/state_out.json'
        comparison = [sys.executable, str(TOOL/'compare_timing.py'), '--parent', str(parent),
                      '--candidate', str(Path(self.step_dir).parent), '--out',
                      str(Path(self.step_dir)/'parent_comparison.json')]
        with (Path(self.step_dir)/'parent_comparison.log').open('w') as log:
            subprocess.run(comparison, stdout=log, stderr=subprocess.STDOUT, check=True)
        with (Path(self.step_dir)/'qualification.log').open('w') as log:"""))
    # Prepare output directories and existing gate-test dependencies.
    qualifier = root / "tools/timing/qualify_gds_artifact.py"
    qualifier.write_text(replace_once(qualifier.read_text(),
        "        (out/'tech').symlink_to(",
        "        (out/'precheck/reports').mkdir(parents=True, exist_ok=True)\n        (out/'tech').symlink_to("))
    qualifier.write_text(replace_once(qualifier.read_text(),
        "        gate_env = dict(env,", """        support = a.test_source.resolve().parent
        shutil.copytree(support/'tools', out/'tools', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(support/'examples', out/'examples')
        gate_env = dict(env,"""))
    if variant != "control":
        contract = REPO / "docs/timing/20261030-control-refactor" / (variant + ".json")
        shutil.copy2(contract, root / "tools/timing/production/last-fanout.json")
        if passing_parent is not None:
            previous = json.loads((passing_parent/'tools/timing/production/last-fanout.json').read_text())['entries']
            current = json.loads(contract.read_text())['entries']
            for entry in previous:
                if entry not in current:
                    raise ValueError('Candidate removes or changes an accepted parent repair')
        required = set()
        for entry in json.loads(contract.read_text())['entries']:
            op = entry['operation']
            if op.get('old'):
                required.add(op['old'])
            if op['kind'] == 'size':
                required.add(op['new'])
            if op['kind'] == 'buffer':
                required.add('sg13cmos5l_buf_4')
        for suffix in ('slow_1p08V_125C', 'typ_1p20V_25C', 'fast_1p32V_m40C'):
            library = PDK/'ihp-sg13cmos5l/libs.ref/sg13cmos5l_stdcell/lib'/('sg13cmos5l_stdcell_'+suffix+'.lib')
            available = set(re.findall(r'cell\s*\(\s*([A-Za-z0-9_]+)\s*\)', library.read_text()))
            if not required <= available:
                raise ValueError('Unavailable required cells in '+str(library)+': '+repr(sorted(required-available)))
    if variant == 'host_clone':
        shutil.copy2(REPO/'tools/timing/refactor_eco.py', root/'tools/timing/refactor_eco.py')
        text = flow.read_text()
        text = replace_once(text, 'from incremental_trial import incremental_script',
                            'from incremental_trial import incremental_script\nfrom refactor_eco import render_script as clone_script')
        text = replace_once(text, "    contract_index = 1\n", """    contract_index = 1

    def render_script(self, operations):
        return clone_script(operations)
""")
        text = replace_once(text, "run_tool(self, 'audit_data_eco.py',", "run_tool(self, 'refactor_eco.py' if any(op['kind']=='clone' for op in operations) else 'audit_data_eco.py',")
        flow.write_text(text)
    # Validate the actual comparator entry point before an expensive build.
    subprocess.run([sys.executable, str(root/'tools/timing/compare_timing.py'),
                    '--parent', str(parent), '--candidate', str(parent),
                    '--out', str(root/'parent_comparison_selfcheck.json')], check=True)
    (root / "scope.json").write_text(json.dumps(dict(
        qualified_source_parent=QUALIFIED, variant=variant, production_flow="PIOClosure",
        tooling_path=str(TOOLING),
        parent_state_sha256=sha(parent_state), incremental_parent=str(passing_parent) if passing_parent else None,
        active_production_modified=False,
        acceptance="Unchanged signoff plus no loss of setup/hold margin in any required corner",
        qualification="Complete normal production flow, nine-session replay, GDS LVS/DRC, precheck and 39 gate tests"), indent=2)+"\n")
    files = [p for p in root.rglob("*") if p.is_file() and not p.is_symlink() and "tt" not in p.relative_to(root).parts]
    (root / "frozen_inputs.json").write_text(json.dumps({str(p.relative_to(root)): sha(p) for p in sorted(files)}, indent=2)+"\n")


def worker(root):
    if (root/'job.json').exists():
        raise ValueError('A trial worker cannot reuse an already attempted output')
    frozen = json.loads((root/'frozen_inputs.json').read_text())
    if any(sha(root/name) != expected for name,expected in frozen.items()):
        raise ValueError('Frozen candidate sources changed before launch')
    tooling = Path(json.loads((root/'scope.json').read_text())['tooling_path'])
    state = dict(status="running", physical_signoff=False, candidate_promoted=False, commands=[])
    def save():
        (root / "job.json").write_text(json.dumps(state, indent=2)+"\n")
    def run(command, name, env=None):
        state["commands"].append(command)
        save()
        with (root / (name+".log")).open("w") as log:
            subprocess.run(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    try:
        env = dict(os.environ, PYTHONPATH="", PYTHONDONTWRITEBYTECODE="1",
                   PATH=str(tooling/"venv/bin")+":"+os.environ["PATH"], XDG_CACHE_HOME=str(root/".cache"))
        run([str(tooling/"venv/bin/python"), str(root/"tt/tt_tool.py"), "--create-user-config", "--ihp"], "configure", env)
        run([sys.executable, "-m", "librelane", "--pdk", "ihp-sg13cmos5l", "--manual-pdk",
             "--pdk-root", str(PDK), "--run-tag", "refactor", "--force-run-dir", str(root/"run"),
             "src/config_merged.json"], "production")
        state["status"] = "qualifying"
        save()
        expat = Path('/nix/store/d8927sznk6qnqln6hl9p4d42h8pq49vg-expat-2.8.0/lib/libexpat.so.1')
        if not expat.is_file():
            raise ValueError('Pinned gate-simulation runtime dependency missing')
        qualification_env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
            LD_LIBRARY_PATH=':'.join(filter(None, (str(expat.parent), os.environ.get('LD_LIBRARY_PATH', '')))))
        state['gate_runtime_library'] = dict(path=str(expat.resolve()), sha256=sha(expat.resolve()))
        run([sys.executable, str(root/"tools/timing/qualify_gds_artifact.py"), "--run", str(root/"run"),
             "--out", str(root/"qualification"), "--pdk-root", str(PDK), "--support-tools", str(tooling/"tt"),
             "--precheck-python", str(tooling/"precheck-venv/bin/python"), "--test-python",
             "/home/shane/eda/pio-test-venv/bin/python", "--test-source", str(root/"test")], "qualification", qualification_env)
        state.update(status="complete", physical_signoff=True)
    except Exception as exc:
        state.update(status="rejected_or_failed", error=str(exc))
    finally:
        changed = [name for name, expected in json.loads((root/"frozen_inputs.json").read_text()).items()
                   if sha(root/name) != expected]
        state["frozen_input_changes"] = changed
        if changed:
            state.update(status="rejected_frozen_input_change", physical_signoff=False)
        save()
    return int(not state["physical_signoff"])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--variant", choices=("control", "hold", "host_drive", "host_clone", "host_buffer", "buffer_hold"), default="control")
    p.add_argument('--passing-parent', type=Path, help='A completed, immutable, fully qualified production trial')
    p.add_argument("--launch", action="store_true")
    p.add_argument("--worker", action="store_true")
    a = p.parse_args()
    root = a.out.resolve()
    if a.worker:
        return worker(root)
    if not root.is_relative_to((REPO/"test/sim_build").resolve()):
        p.error("Trial output must be isolated under this repository's test/sim_build")
    freeze(root, a.variant, a.passing_parent)
    if a.launch:
        command = ["/nix/var/nix/profiles/default/bin/nix", "develop", "--offline", "--command",
                   "python3", "-B", str(root/'trial_runner.py'), "--out", str(root), "--worker"]
        with (root/"launcher.log").open("w") as log:
            proc = subprocess.Popen(command, cwd="/home/shane/eda/librelane-3.1.0.dev3", stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                                    env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        (root/"process.json").write_text(json.dumps(dict(pid=proc.pid, command=command), indent=2)+"\n")
        print("Launched isolated normal production trial", proc.pid, root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
