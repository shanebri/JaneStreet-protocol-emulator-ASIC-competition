"""Validate and activate one fully qualified physical-only headroom increment.

Original qualification receipts remain immutable. The new receipt explicitly
supersedes the previous active recipe and binds the actual production artifacts.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from activate_refactor import FLOW_CHECK, input_comparison, normalized, replay_inputs
from check_signoff import REQUIRED_CORNERS, check_metrics
from headroom_campaign import ACTIVATION, reference, write_json
from refactor_trial import REPO, PARENT_SHA256, sha, validated_parent


RECIPE = Path('tools/timing/production/last-fanout.json')
FLOW = Path('tools/timing/production_flow.py')


def checked_precheck(report):
    tree = ET.parse(report)
    cases = tree.findall('.//testcase')
    names = [(case.get('classname', ''), case.get('name')) for case in cases]
    if (len(cases) != 9 or len(set(names)) != 9 or any(not name for _, name in names)
            or any(tree.findall('.//' + kind) for kind in ('failure', 'error', 'skipped'))):
        raise ValueError('Require nine distinct precheck tests, all passed without skips')
    return dict(report=str(report), sha256=sha(report), tests=9, names=[list(name) for name in names])


def comparison(parent, candidate):
    errors = ['parent: ' + error for error in check_metrics(parent)]
    errors += ['candidate: ' + error for error in check_metrics(candidate)]
    margins = {}
    for corner in REQUIRED_CORNERS:
        margins[corner] = {}
        for analysis in ('setup', 'hold'):
            key = f'timing__{analysis}__ws__corner:{corner}'
            consumed = parent[key] - candidate[key]
            margins[corner][analysis] = dict(parent_ns=parent[key], candidate_ns=candidate[key], consumed_ns=consumed)
            if consumed > 0.000001:
                errors.append(corner + ' ' + analysis + ' exceeds the fixed campaign reserve')
    return dict(status='rejected' if errors else 'pass', margins=margins, errors=errors,
                numeric_tie_tolerance_ns=0.000001)


def source_comparison(candidate, *, activated):
    frozen = json.loads((candidate / 'frozen_inputs.json').read_text())
    rows = {}
    planned = {}
    for name, expected in frozen.items():
        path = candidate / name
        if sha(path) != expected:
            raise ValueError('Candidate frozen input changed: ' + name)
        if not (name.startswith('src/') or name.startswith('tools/timing/')
                or name in ('info.yaml', 'librelane_plugin_pio.py', '.github/workflows/gds.yaml')):
            continue
        if '__pycache__' in Path(name).parts or name.endswith('.pyc'):
            continue
        if name == 'tools/timing/compare_timing.py':
            # Candidate-only reserve gate; active production has no local parent path.
            continue
        tested = normalized(path)
        if name == FLOW.as_posix():
            text = tested.decode()
            if text.count(FLOW_CHECK) != 1:
                raise ValueError('Unexpected candidate production acceptance gate')
            tested = text.replace(FLOW_CHECK, '', 1).encode()
        active = REPO / name
        if name in (RECIPE.as_posix(), FLOW.as_posix()):
            planned[name] = tested
            if not activated:
                continue
        if normalized(active) != tested:
            raise ValueError('Active/tested input differs: ' + name)
        rows[name] = dict(active_sha256=sha(active), tested_sha256=sha(path), newline_normalized_match=True)
    return rows, planned


def qualification(candidate):
    state_path, qualification_path = validated_parent(candidate)
    scope = json.loads((candidate / 'scope.json').read_text())
    if scope.get('variant') not in ('headroom_combined', 'headroom_hold_cluster', 'headroom_setup_local'):
        raise ValueError('Unexpected headroom candidate scope')
    parent = Path(scope['incremental_parent'])
    parent_state, parent_qualification = validated_parent(parent)
    if (scope['parent_state_sha256'] != sha(parent_state)
            or sha(candidate / 'parent/69-openroad-stapostpnr/state_out.json') != sha(parent_state)):
        raise ValueError('Candidate is not bound to the qualified immediate parent')
    compared = comparison(json.loads(parent_state.read_text())['metrics'], json.loads(state_path.read_text())['metrics'])
    if compared['errors']:
        raise ValueError('Qualified candidate requires a separate margin-budget decision: ' + repr(compared['errors']))
    checks = json.loads(qualification_path.read_text())['checks']
    if checks['tt_precheck'].get('tests') != 9 or checks['gate_tests'].get('tests') != 39:
        raise ValueError('Incomplete precheck or exact-netlist gate regression')
    baseline = REPO / 'docs/timing/20261030-control-refactor/qualified-parent/69-openroad-stapostpnr/state_out.json'
    if sha(baseline) != PARENT_SHA256:
        raise ValueError('Fixed original qualified-release state changed')
    return dict(state=str(state_path), state_sha256=sha(state_path),
                qualification_manifest=str(qualification_path), qualification_manifest_sha256=sha(qualification_path),
                parent=str(parent), parent_state=str(parent_state), parent_state_sha256=sha(parent_state),
                parent_qualification_sha256=sha(parent_qualification),
                parent_comparison=compared,
                fixed_ci_release_comparison=comparison(json.loads(baseline.read_text())['metrics'],
                                                       json.loads(state_path.read_text())['metrics']),
                precheck_evidence=checked_precheck(candidate / 'qualification/precheck/reports/results.xml'),
                timing_replay_input_sha256=replay_inputs(candidate), checks=checks)


def activate(candidate, out, apply):
    verified = qualification(candidate)
    if out.exists() or not out.resolve().is_relative_to(REPO):
        raise ValueError('Activation receipt must be a fresh repository path')
    # This also verifies the currently active old qualification and source bytes.
    parent, state, binding = reference()
    if str(parent) != verified['parent'] or sha(state) != verified['parent_state_sha256']:
        raise ValueError('Current active implementation is not this candidate\'s parent')
    rows, planned = source_comparison(candidate, activated=False)
    result = dict(status='qualified_ready_for_activation', activated=False,
        scope='Locally qualified physical-only successor; no new GitHub CI or hardware claim',
        candidate=str(candidate), supersedes_receipt=str(ACTIVATION),
        supersedes_receipt_sha256=sha(ACTIVATION), original_active_binding=binding,
        source_comparisons=rows, qualification=verified,
        release_runner_sha256=sha(Path(__file__)))
    out.parent.mkdir(parents=True, exist_ok=True)
    if apply:
        previous = {name: (REPO / name).read_bytes() for name in planned}
        backups = {}
        for name, data in previous.items():
            path = out.parent / ('previous-' + Path(name).name)
            with path.open('xb') as stream:
                stream.write(data)
            backups[name] = dict(path=str(path), sha256=sha(path))
        # Recheck all parent-bound inputs after creating reviewable backups.
        input_comparison(parent)
        if sha(REPO / RECIPE) != binding['active_recipe_sha256']:
            raise ValueError('Active recipe changed during activation preflight')
        try:
            for name, data in planned.items():
                (REPO / name).write_bytes(data)
            rows, _ = source_comparison(candidate, activated=True)
            result.update(status='complete', activated=True, source_comparisons=rows,
                activated_utc=datetime.now(timezone.utc).isoformat(), previous_active_files=backups,
                active_recipe_sha256=sha(REPO / RECIPE), active_flow_sha256=sha(REPO / FLOW))
            with out.open('x') as stream:
                json.dump(result, stream, indent=2); stream.write('\n')
        except Exception:
            for name, data in previous.items():
                (REPO / name).write_bytes(data)
            raise
    else:
        with out.open('x') as stream:
            json.dump(result, stream, indent=2); stream.write('\n')
    print(result['status'], 'activated=' + str(result['activated']))


def verify_active(receipt):
    result = json.loads(receipt.read_text())
    if result.get('status') != 'complete' or result.get('activated') is not True:
        raise ValueError('Incomplete activation receipt')
    if sha(result['supersedes_receipt']) != result['supersedes_receipt_sha256']:
        raise ValueError('Superseded qualification receipt changed')
    candidate = Path(result['candidate'])
    verified = qualification(candidate)
    if verified != result['qualification'] or sha(Path(__file__)) != result['release_runner_sha256']:
        raise ValueError('Qualified activation evidence changed')
    source_comparison(candidate, activated=True)
    if sha(REPO / RECIPE) != result['active_recipe_sha256'] or sha(REPO / FLOW) != result['active_flow_sha256']:
        raise ValueError('Active implementation differs from the qualified successor')
    for backup in result['previous_active_files'].values():
        if sha(backup['path']) != backup['sha256']:
            raise ValueError('Previous active implementation backup changed')
    for path, expected in result['qualification']['timing_replay_input_sha256'].items():
        if sha(path) != expected:
            raise ValueError('Qualified timing model or replay input changed')
    print('PASS: active recipe/flow, frozen inputs, full qualification, parent and timing models')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate', type=Path)
    p.add_argument('--out', type=Path)
    p.add_argument('--apply', action='store_true')
    p.add_argument('--verify-active', type=Path)
    a = p.parse_args()
    if a.verify_active:
        if a.apply:
            p.error('--verify-active cannot activate a different implementation')
        verify_active(a.verify_active.resolve())
    else:
        if not a.candidate or not a.out:
            p.error('--candidate and --out are required')
        activate(a.candidate.resolve(), a.out.resolve(), a.apply)


if __name__ == '__main__':
    main()
