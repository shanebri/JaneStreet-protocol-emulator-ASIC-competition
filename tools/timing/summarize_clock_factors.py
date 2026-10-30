"""Validate and compare the fixed 2x2 clustering/splitting physical experiment."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from check_signoff import REQUIRED_CORNERS, find_state
from collect_implementation import validate_replay

TRIALS = {'clock_control': (None, None), 'clock_cluster8': (8, None),
          'clock_split8': (None, 8), 'clock_cap8': (8, 8)}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def latency(text):
    result = {}
    for edge in ('rise', 'fall'):
        part = text.split(f'{edge} -> {edge}\n', 1)[1].split('\n\n', 1)[0]
        values = [float(v) for v in re.findall(r'^\s*([-+\d.]+)\s+network latency', part, re.M)]
        if len(values) != 2 or values[0] > values[1]:
            raise ValueError('Unexpected native clock-latency report')
        result[edge] = dict(min_ns=values[0], max_ns=values[1], spread_ns=values[1]-values[0])
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trials-root', type=Path, required=True)
    p.add_argument('--evidence', type=Path, required=True)
    a = p.parse_args()
    baseline_config = None
    baseline_manifest = None
    rows = []
    for name, factors in TRIALS.items():
        trial = a.trials_root/f'{name}-01'
        evidence = a.evidence/f'{name}-01'
        manifest = json.loads((trial/'experiment.json').read_text())
        config = json.loads((trial/'resolved_input.json').read_text())
        if manifest['status'] not in ('screen_complete', 'rejected_signoff'):
            raise ValueError(f'Incomplete physical experiment: {name}')
        if manifest['clock_factors'] != dict(sink_clustering_size=factors[0], branch_split_max_loads=factors[1]):
            raise ValueError('Factor manifest mismatch')
        if (config['CTS_SINK_CLUSTERING_SIZE'] != factors[0] or config['GRT_ADJUSTMENT'] != 0.25
                or not config['CTS_SINK_CLUSTERING_ENABLE']):
            raise ValueError('Applied CTS/GRT settings differ from the experiment contract')
        if sha(trial/'runner.py') != manifest['runner_sha256']:
            raise ValueError('Saved invocation runner hash mismatch')
        if baseline_config is None:
            baseline_config, baseline_manifest = config, manifest
        else:
            differing = {k for k in baseline_config.keys() | config.keys()
                         if baseline_config.get(k) != config.get(k)}
            if differing - {'CTS_SINK_CLUSTERING_SIZE'}:
                raise ValueError(f'Unexpected config changes: {differing}')
            for key in ('input_state_sha256', 'input_views_sha256', 'runner_sha256', 'execution_overrides'):
                if manifest[key] != baseline_manifest[key]:
                    raise ValueError(f'Unmatched experiment input: {key}')
        state_path = find_state(trial/'run')
        state = json.loads(state_path.read_text())
        metrics = json.loads((evidence/'sta/metrics.json').read_text())
        replay = json.loads((evidence/'sta/replay_manifest.json').read_text())
        validate_replay(replay, metrics)
        provenance = json.loads((evidence/'sta/provenance.json').read_text())
        if provenance['coverage_issues'] or provenance['state_sha256'] != sha(state_path):
            raise ValueError('STA provenance or constraint-coverage mismatch')
        post_cts = json.loads((evidence/'post_cts_clock_audit.json').read_text())
        if post_cts['insertion_audit']['status'] != 'pass':
            raise ValueError('Clock insertion connectivity audit failed')
        for filename, expected in post_cts['input_sha256'].items():
            if sha(Path(filename)) != expected:
                raise ValueError('Post-CTS audit input changed')
        final_audit = evidence/'postroute_clock_audit.json'
        if not final_audit.exists():
            with (evidence/'postroute_clock_audit.log').open('w') as log:
                subprocess.run(['openroad', '-no_init', '-exit', '-python',
                    str(Path(__file__).with_name('audit_clock_tree.py')), '--odb', state['odb'],
                    '--out', str(final_audit)], stdout=log, stderr=subprocess.STDOUT, check=True)
        final = json.loads(final_audit.read_text())
        if final['input_sha256'] != {state['odb']: sha(Path(state['odb']))}:
            raise ValueError('Post-route audit input mismatch')
        if final['topology']['clock_sink_count'] != post_cts['topology']['clock_sink_count']:
            raise ValueError('Clock sink set size changed during implementation')
        native = evidence/'native_sta'
        clock_latency = {}
        for corner in REQUIRED_CORNERS:
            target = native/corner
            target.mkdir(parents=True, exist_ok=True)
            for file in ('clock.rpt', 'skew.max.rpt', 'skew.min.rpt'):
                shutil.copy2(state_path.parent/corner/file, target/file)
            clock_latency[corner] = latency((target/'clock.rpt').read_text())
        for file in ('experiment.json', 'resolved_input.json', 'runner.py'):
            shutil.copy2(trial/file, evidence/file)
        slow = 'nom_slow_1p08V_125C'

        def metric(key, corner=slow):
            return metrics[f'{key}__corner:{corner}']

        rows.append(dict(trial=name, factors=manifest['clock_factors'],
            setup_ws_ns=metric('timing__setup__ws'), setup_tns_ns=metric('timing__setup__tns'),
            setup_endpoints=metric('timing__setup_vio__count'), slow_slew=metric('design__max_slew_violation__count'),
            fanout_per_corner={c: metric('design__max_fanout_violation__count', c) for c in REQUIRED_CORNERS},
            cap_per_corner={c: metric('design__max_cap_violation__count', c) for c in REQUIRED_CORNERS},
            filtered_gaps_per_corner={c: metric('timing__unannotated_net_filtered__count', c) for c in REQUIRED_CORNERS},
            hold_ws_per_corner={c: metric('timing__hold__ws', c) for c in REQUIRED_CORNERS},
            added_split_buffers=post_cts['insertion_audit']['added_buffers'],
            post_cts_topology={k: v for k, v in post_cts['topology'].items() if k not in ('buffers', 'dummy_loads')},
            postroute_topology={k: v for k, v in final['topology'].items() if k not in ('buffers', 'dummy_loads')},
            clock_latency=clock_latency, replay_sessions=len(replay['sessions']),
            final_route_drc=state['metrics'].get('route__drc_errors'),
            antenna_violations=state['metrics'].get('route__antenna_violation__count'),
            strict_signoff_failures=provenance['gate_failures']))
    ws = {r['trial']: r['setup_ws_ns'] for r in rows}
    result = dict(status='complete', rows=rows, setup_ws_effects_ns={
        'cluster8_vs_control': ws['clock_cluster8']-ws['clock_control'],
        'split8_vs_control': ws['clock_split8']-ws['clock_control'],
        'split8_after_cluster8': ws['clock_cap8']-ws['clock_cluster8'],
        'interaction': ws['clock_cap8']-ws['clock_cluster8']-ws['clock_split8']+ws['clock_control']},
        effect_sign='positive means improved setup slack; attribution requires complete annotation',
        qualification='controlled post-route screens; strict signoff and full qualification still apply')
    with (a.evidence/'comparison.json').open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
    print('Validated matched four-way clock factor comparison')


if __name__ == '__main__':
    main()
