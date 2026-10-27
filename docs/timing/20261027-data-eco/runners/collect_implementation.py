"""Preserve a completed implementation screen and independent diagnostic STA.

Run in the pinned Linux/Nix environment. Existing evidence is never overwritten.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys

from check_signoff import REQUIRED_CORNERS, check_metrics, find_state

VECTOR_KEYS = ('timing__setup__ws', 'timing__hold__ws', 'timing__setup__tns', 'timing__hold__tns',
               'timing__setup_vio__count', 'timing__hold_vio__count',
               'design__max_slew_violation__count', 'design__max_cap_violation__count',
               'design__max_fanout_violation__count', 'timing__unannotated_net_filtered__count')
SCALAR_KEYS = ('design__instance__area__stdcell', 'design__instance__utilization__stdcell',
               'design__inferred_latch__count', 'design__instance_unmapped__count',
               'synthesis__check_error__count')


def selected_metrics(metrics):
    keys = [f'{key}__corner:{corner}' for corner in REQUIRED_CORNERS for key in VECTOR_KEYS]
    keys += list(SCALAR_KEYS)
    for key in keys:
        value = metrics.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f'Missing or invalid measured metric: {key}')
    return {key: metrics[key] for key in keys}


def first_path(text):
    return text.partition('\nStartpoint:')[0].rstrip()+'\n' if text.strip() else ''


def path_summary(text):
    text = first_path(text)
    result = {}
    for key, pattern in (('startpoint', r'^Startpoint:\s*(.*)'), ('endpoint', r'^Endpoint:\s*(.*)'),
                         ('slack_ns', r'([-+\d.]+)\s+slack\s+\(')):
        found = re.search(pattern, text, re.M)
        result[key] = (float(found[1]) if key == 'slack_ns' else found[1]) if found else None
    return result


def validate_replay(manifest, metrics):
    expected = {(c, m) for c in REQUIRED_CORNERS for m in ('baseline', 'operational', 'reset_active')}
    sessions = manifest.get('sessions', [])
    if (manifest.get('status') != 'complete' or len(sessions) != 9
            or {(s['corner'], s['mode']) for s in sessions} != expected):
        raise ValueError('Incomplete or duplicate replay matrix')
    for session in sessions:
        if session['mode'] != 'baseline':
            continue
        for analysis in ('setup', 'hold'):
            actual = session[analysis]
            archived = metrics[f'timing__{analysis}__ws__corner:{session["corner"]}']
            if not math.isfinite(actual) or abs(actual-archived) > 0.001:
                raise ValueError(f'Replay differs from fresh extracted state: {session["corner"]} {analysis}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trial', type=Path, required=True)
    parser.add_argument('--pdk-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    trial, pdk, out = (p.resolve() for p in (args.trial, args.pdk_root, args.out))
    manifest = json.loads((trial/'experiment.json').read_text())
    if manifest['status'] == 'running':
        parser.error('Trial still running; do not collect incomplete evidence')
    state_path = find_state(trial/'run')
    state = json.loads(state_path.read_text())
    metrics = selected_metrics(state['metrics'])
    if manifest['trial'].startswith('mapping_'):
        for name, expected_hash in manifest['source_sha256'].items():
            actual = hashlib.sha256((trial/'frozen/src'/name).read_bytes()).hexdigest()
            if actual != expected_hash:
                raise ValueError(f'Frozen mapping source changed: {name}')
    out.mkdir(parents=True, exist_ok=False)
    for name in ('experiment.json', 'post_route_signoff.log', 'resolved_input.json'):
        shutil.copy2(trial/name, out/name)
    (out/'metrics.json').write_text(json.dumps(metrics, indent=2)+'\n')
    synthesis = next((p for p in (trial/'run').iterdir()
                       if p.name.endswith('-yosys-synthesis')), None)
    if synthesis:
        shutil.copy2(synthesis/'config.json', out/'synthesis_config.json')
        for abc in synthesis.glob('*.abc'):
            shutil.copy2(abc, out/abc.name)
        logs = list(synthesis.glob('*synthesis.log'))
        if len(logs) != 1:
            raise ValueError('Expected one synthesis execution log')
        shutil.copy2(logs[0], out/'synthesis.log')
    # Keep the actual post-route state and report paths, not only derived metrics.
    shutil.copy2(state_path, out/'postroute_state.json')
    replay = trial/'replay'
    with (out/'replay.log').open('w') as log:
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('replay.py')),
                                 '--run', str(trial/'run'), '--pdk-root', str(pdk),
                                 '--out', str(replay), '--reset-active'], stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        parser.exit(1, f'Replay failed; inspect {out/"replay.log"}\n')
    replay_manifest = json.loads((replay/'manifest.json').read_text())
    validate_replay(replay_manifest, metrics)
    shutil.copy2(replay/'manifest.json', out/'replay_manifest.json')
    sessions = []
    coverage_issues = []
    for session in replay_manifest['sessions']:
        folder = replay/f'{session["corner"]}-{session["mode"]}'
        coverage = (folder/'coverage.rpt').read_text()
        if coverage.strip():
            coverage_issues.append(dict(corner=session['corner'], mode=session['mode'], report=coverage))
        paths = {p.name: path_summary(p.read_text()) for p in folder.glob('*.rpt')
                 if p.name.endswith(('_max.rpt', '_min.rpt')) or p.name in ('global_setup.rpt', 'global_hold.rpt')}
        sessions.append(dict(session, coverage_issues=bool(coverage.strip()), paths=paths))
        if session['corner'] == REQUIRED_CORNERS[0] and session['mode'] == 'baseline':
            for report in folder.glob('*.rpt'):
                if report.name in ('annotation.rpt', 'coverage.rpt', 'electrical.rpt'):
                    shutil.copy2(report, out/report.name)
                elif report.name.startswith(('global_', 'registers_', 'reset_', 'input_ui_in_')):
                    (out/report.name).write_text(first_path(report.read_text()))
    (out/'targeted_paths.json').write_text(json.dumps(sessions, indent=2)+'\n')
    placement = next((p for p in (trial/'run').iterdir()
                      if p.name.endswith('-openroad-globalplacement')), None)
    observed = []
    if placement:
        log = placement/'openroad-globalplacement.log'
        observed = re.findall(r'Reading timing models for corner ([A-Za-z0-9_]+)', log.read_text())
        shutil.copy2(placement/'config.json', out/'placement_config.json')
        shutil.copy2(log, out/'placement.log')
    expected = (manifest['step_overrides'].get('OpenROAD.GlobalPlacement', {}).get('PNR_CORNERS')
                or [json.loads((trial/'resolved_input.json').read_text())['DEFAULT_CORNER']])
    if set(observed) != set(expected):
        raise ValueError(f'Observed placement views {observed} differ from expected {expected}')
    provenance = {'state': str(state_path), 'state_sha256': hashlib.sha256(state_path.read_bytes()).hexdigest(),
                  'gate_failures': check_metrics(state['metrics']), 'coverage_issues': coverage_issues,
                  'placement_views_observed': observed, 'placement_views_expected': expected,
                  'qualification': 'screen_only; final GDS/DRC/LVS/precheck/gate-level verification incomplete'}
    (out/'provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    print(f'Collected {manifest["trial"]}: setup WS '
          + ' / '.join(f'{metrics[f"timing__setup__ws__corner:{c}"]:.6f}' for c in REQUIRED_CORNERS))


if __name__ == '__main__':
    main()
