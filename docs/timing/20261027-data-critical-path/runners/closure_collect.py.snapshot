"""Collect new closure screens, including screens that reuse a frozen netlist."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from check_signoff import check_metrics, find_state
from collect_implementation import selected_metrics, validate_replay, first_path, path_summary


def nominal_view(spefs):
    if len(spefs) != 1 or next(iter(spefs)) not in ('nom', 'nom_*'):
        raise ValueError(f'Unexpected RC corner set: {spefs}')
    return Path(next(iter(spefs.values())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trial', type=Path, required=True)
    parser.add_argument('--pdk-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    trial, pdk, out = (p.resolve() for p in (args.trial, args.pdk_root, args.out))
    manifest = json.loads((trial/'experiment.json').read_text())
    if manifest['status'] == 'running':
        parser.error('Trial is not finished')
    state_path = find_state(trial/'run')
    state = json.loads(state_path.read_text())
    metrics = selected_metrics(state['metrics'])
    out.mkdir(parents=True, exist_ok=False)
    for name in ('experiment.json', 'resolved_input.json', 'post_route_signoff.log'):
        shutil.copy2(trial/name, out/name)
    shutil.copy2(state_path, out/'postroute_state.json')
    # Preserve the applied step configuration, especially placement-only views.
    for suffix, label in (('openroad-globalplacement', 'placement'), ('yosys-synthesis', 'synthesis')):
        folders = list((trial/'run').glob('*-'+suffix))
        if len(folders) > 1:
            raise ValueError(f'Ambiguous {suffix} provenance')
        if folders:
            shutil.copy2(folders[0]/'config.json', out/f'{label}_config.json')
            if label == 'synthesis':
                for script in folders[0].glob('*.abc'):
                    shutil.copy2(script, out/script.name)
    (out/'metrics.json').write_text(json.dumps(metrics, indent=2)+'\n')
    # A re-extraction screen legitimately shares its frozen netlist/SDC. Expose
    # exactly those state views to replay rather than borrowing a new netlist.
    view = trial/'replay-input'
    (view/'input-openroad-fillinsertion').mkdir(parents=True, exist_ok=False)
    (view/'output-openroad-rcx/nom').mkdir(parents=True)
    (view/'final/sdc').mkdir(parents=True)
    (view/'input-openroad-fillinsertion/tt_um_shanebri_top.nl.v').symlink_to(Path(state['nl']))
    (view/'output-openroad-rcx/nom/tt_um_shanebri_top.nom.spef').symlink_to(nominal_view(state['spef']))
    (view/'final/sdc/tt_um_shanebri_top.sdc').symlink_to(Path(state['sdc']))
    replay = trial/'replay'
    with (out/'replay.log').open('w') as log:
        run = subprocess.run([sys.executable, str(Path(__file__).with_name('replay.py')), '--run', str(view),
                              '--pdk-root', str(pdk), '--out', str(replay), '--reset-active'],
                             stdout=log, stderr=subprocess.STDOUT)
    if run.returncode:
        parser.exit(1, f'Replay failed; inspect {out/"replay.log"}\n')
    replay_manifest = json.loads((replay/'manifest.json').read_text())
    validate_replay(replay_manifest, metrics)
    shutil.copy2(replay/'manifest.json', out/'replay_manifest.json')
    sessions, coverage = [], []
    for session in replay_manifest['sessions']:
        folder = replay/f'{session["corner"]}-{session["mode"]}'
        text = (folder/'coverage.rpt').read_text()
        if text.strip():
            coverage.append(dict(session, report=text))
        paths = {p.name: path_summary(p.read_text()) for p in folder.glob('*.rpt')
                 if p.name.endswith(('_max.rpt', '_min.rpt')) or p.name.startswith('global_')}
        sessions.append(dict(session, coverage_issues=bool(text.strip()), paths=paths))
        if session['corner'] == 'nom_slow_1p08V_125C' and session['mode'] == 'baseline':
            for report in folder.glob('*.rpt'):
                if report.name in ('annotation.rpt', 'electrical.rpt', 'coverage.rpt'):
                    shutil.copy2(report, out/report.name)
                elif report.name.startswith(('global_', 'registers_', 'reset_', 'input_ui_in_', 'input_ena')):
                    (out/report.name).write_text(first_path(report.read_text()))
    (out/'targeted_paths.json').write_text(json.dumps(sessions, indent=2)+'\n')
    (out/'provenance.json').write_text(json.dumps({
        'state': str(state_path), 'state_sha256': hashlib.sha256(state_path.read_bytes()).hexdigest(),
        'gate_failures': check_metrics(state['metrics']), 'coverage_issues': coverage,
        'qualification': 'post-route screen; full qualification remains required'}, indent=2)+'\n')
    print('Collected', manifest['trial'], 'slow setup WS', metrics['timing__setup__ws__corner:nom_slow_1p08V_125C'])


if __name__ == '__main__':
    main()
