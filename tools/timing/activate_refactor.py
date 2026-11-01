"""Audit active implementation inputs and optionally activate a qualified recipe.

Without --apply this only records an input comparison, not qualification.
Activation requires both complete physical parents and the exact tested inputs.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from refactor_trial import PARENT_SHA256, QUALIFIED, REPO, sha, validated_parent


FLOW_CHECK = """        parent = Path(self.config['DESIGN_DIR']).parent/'parent/69-openroad-stapostpnr/state_out.json'
        comparison = [sys.executable, str(TOOL/'compare_timing.py'), '--parent', str(parent),
                      '--candidate', str(Path(self.step_dir).parent), '--out',
                      str(Path(self.step_dir)/'parent_comparison.json')]
        with (Path(self.step_dir)/'parent_comparison.log').open('w') as log:
            subprocess.run(comparison, stdout=log, stderr=subprocess.STDOUT, check=True)
"""
RECIPE = Path('tools/timing/production/last-fanout.json')


def normalized(path):
    return path.read_bytes().replace(b'\r\n', b'\n')


def input_comparison(candidate):
    frozen = json.loads((candidate/'frozen_inputs.json').read_text())
    if any(sha(candidate/name) != expected for name, expected in frozen.items()):
        raise ValueError('Frozen tested inputs changed')
    names = [name for name in frozen if name.startswith('src/') or name in (
        'info.yaml', 'librelane_plugin_pio.py', '.github/workflows/gds.yaml')
        or name.startswith('tools/timing/')]
    rows = {}
    for name in names:
        if '__pycache__' in Path(name).parts or name.endswith('.pyc'):
            continue
        if name == RECIPE.as_posix():
            continue
        target = REPO/name
        tested = normalized(candidate/name)
        explanation = 'Same bytes after newline normalization'
        if name == 'tools/timing/compare_timing.py':
            target = REPO/'tools/packet_sram/compare_timing.py'
            explanation = 'Additional acceptance gate only; same comparator at its active location'
        elif name == 'tools/timing/production_flow.py':
            text = tested.decode()
            if text.count(FLOW_CHECK) != 1:
                raise ValueError('Unexpected frozen production-flow modification')
            tested = text.replace(FLOW_CHECK, '', 1).encode()
            explanation = 'Only the extra parent-margin rejection gate is omitted in the stock flow'
        if normalized(target) != tested:
            raise ValueError('Active input differs from tested snapshot: '+name)
        rows[name] = dict(active_path=str(target), active_sha256=sha(target),
                          frozen_sha256=sha(candidate/name), comparison=explanation)
    return rows


def replay_inputs(candidate):
    manifests = list((candidate/'run').glob('*-pio-routeacceptance/qualification/replay/manifest.json'))
    if len(manifests) != 1:
        raise ValueError('Missing or ambiguous native timing replay')
    replay = json.loads(manifests[0].read_text())
    if replay['status'] != 'complete':
        raise ValueError('Native timing replay is incomplete')
    for name, expected in replay['sha256'].items():
        if sha(Path(name)) != expected:
            raise ValueError('Qualified timing input or model changed: '+name)
    return replay['sha256']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--apply', action='store_true')
    a = p.parse_args()
    candidate = a.candidate.resolve()
    out = a.out.resolve()
    if not candidate.is_relative_to((REPO/'test/sim_build').resolve()):
        p.error('Candidate must be an isolated repository production run')
    if not out.is_relative_to(REPO) or out.exists():
        p.error('Evidence output must be a new repository file')
    scope = json.loads((candidate/'scope.json').read_text())
    if scope['variant'] != 'buffer_hold' or scope['qualified_source_parent'] != QUALIFIED:
        raise ValueError('Unexpected candidate recipe or qualified source baseline')
    rows = input_comparison(candidate)
    target = REPO/RECIPE
    before = sha(target)
    tested = candidate/RECIPE
    result = dict(status='inputs_match_tested_snapshot', activated=False,
                  scope='Input comparison alone is not physical qualification',
                  candidate=str(candidate), source_comparisons=rows,
                  previous_recipe_sha256=before, tested_recipe_sha256=sha(tested))
    out.parent.mkdir(parents=True, exist_ok=True)
    if a.apply:
        state, qualification = validated_parent(candidate)
        parent = Path(scope['incremental_parent'])
        parent_state, parent_qualification = validated_parent(parent)
        if (scope['parent_state_sha256'] != sha(parent_state)
                or sha(candidate/'parent/69-openroad-stapostpnr/state_out.json') != sha(parent_state)):
            raise ValueError('Candidate is not bound to its fully qualified immediate parent')
        import sys
        sys.path.insert(0, str(REPO/'tools/packet_sram'))
        from compare_timing import compare
        comparison = compare(json.loads(parent_state.read_text())['metrics'],
                             json.loads(state.read_text())['metrics'])
        if comparison['status'] != 'numeric_checks_pass':
            raise ValueError('Candidate consumes required parent timing headroom')
        baseline_state = parent/'parent/69-openroad-stapostpnr/state_out.json'
        if sha(baseline_state) != PARENT_SHA256:
            raise ValueError('First increment is not bound to the qualified CI baseline')
        baseline_comparison = compare(json.loads(baseline_state.read_text())['metrics'],
                                      json.loads(parent_state.read_text())['metrics'])
        if baseline_comparison['status'] != 'numeric_checks_pass':
            raise ValueError('First increment consumes required baseline timing headroom')
        baseline = subprocess.check_output(['git', 'show', QUALIFIED+':'+RECIPE.as_posix()], cwd=REPO)
        if normalized(target) != baseline.replace(b'\r\n', b'\n'):
            raise ValueError('Active recipe changed since the original qualified baseline')
        timing_inputs = {**replay_inputs(parent), **replay_inputs(candidate)}
        result['source_comparisons'] = input_comparison(candidate)
        backup = out.with_suffix('.previous-recipe.json')
        with backup.open('xb') as stream:
            stream.write(target.read_bytes())
        target.write_bytes(tested.read_bytes())
        if sha(target) != sha(tested):
            raise ValueError('Activated recipe differs from tested bytes')
        result.update(status='complete', activated=True,
            scope='Local qualification and exact-recipe activation; no new GitHub CI claim',
            activated_utc=datetime.now(timezone.utc).isoformat(),
            timing_replay_input_sha256=timing_inputs,
            active_recipe=str(target), active_recipe_sha256=sha(target),
            previous_recipe_backup=str(backup),
            parent_state_sha256=sha(parent_state), run_state_sha256=sha(state),
            qualification_manifest=str(qualification), qualification_manifest_sha256=sha(qualification),
            parent_qualification_manifest=str(parent_qualification),
            parent_qualification_manifest_sha256=sha(parent_qualification),
            parent_comparison=comparison, baseline_comparison=baseline_comparison,
            qualified_baseline_state_sha256=PARENT_SHA256,
            activation_runner_sha256=sha(Path(__file__)))
    with out.open('x') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    print(result['status'], 'activated='+str(result['activated']), 'inputs='+str(len(rows)))


if __name__ == '__main__':
    main()
