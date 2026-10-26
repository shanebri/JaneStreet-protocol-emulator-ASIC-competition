"""Resume an archived LibreLane 3.1.0.dev3 physical state for one isolated trial.

Run inside the pinned Linux/Nix environment. Production configuration is never
edited. The output directory must be new. Final checks remain enabled and may
reject the experiment after its reports have been saved.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def relocate(value, replacements):
    if isinstance(value, str):
        for old, new in replacements:
            value = value.replace(old, new)
        return value
    if isinstance(value, list):
        return [relocate(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: relocate(item, replacements) for key, item in value.items()}
    return value


def final_gate(output):
    """Always preserve the repository's strict gate, including fanout checks."""
    states = list((output / 'run').glob('*-openroad-stapostpnr/state_out.json'))
    log = output / 'post_route_signoff.log'
    if len(states) != 1:
        log.write_text(f'Signoff evidence unavailable: found {len(states)} completed post-route states\n')
        return 1
    result = subprocess.run([sys.executable, str(Path(__file__).with_name('check_signoff.py')), str(states[0])],
                            capture_output=True, text=True)
    log.write_text(result.stdout + result.stderr)
    return result.returncode


def main():
    from librelane.config import Config
    from librelane.flows.classic import Classic
    from librelane.steps.openroad import DetailedPlacement
    from librelane.state import State

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-root', type=Path, required=True,
                        help='Extracted archive containing runs/wokwi and src')
    parser.add_argument('--pdk-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--trial', choices=('control', 'electrical', 'timing', 'cts', 'cts_branches'), required=True)
    parser.add_argument('--cluster-size', type=int, default=8)
    parser.add_argument('--threads', type=int, default=8,
                        help='Shared execution setting for control and candidate')
    args = parser.parse_args()
    if args.threads < 1:
        parser.error('--threads must be positive')
    root, pdk, output = (p.resolve() for p in (args.archive_root, args.pdk_root, args.out))
    run = root / 'runs/wokwi'
    original = json.loads((run / 'resolved.json').read_text())
    assert original['CLOCK_PERIOD'] == 20
    assert original['PDK'] == 'ihp-sg13cmos5l'
    assert set(original['STA_CORNERS']) == {
        'nom_slow_1p08V_125C', 'nom_typ_1p20V_25C', 'nom_fast_1p32V_m40C'}
    assert original['SETUP_VIOLATION_CORNERS'] == ['*']
    assert original['HOLD_VIOLATION_CORNERS'] == ['*']
    assert original['MAX_SLEW_VIOLATION_CORNERS'] == ['*']
    assert original['MAX_CAP_VIOLATION_CORNERS'] == ['*']
    replacements = [(str(Path(original['DESIGN_DIR']).parent), str(root)),
                    (original['PDK_ROOT'], str(pdk))]
    raw = relocate(original, replacements)
    # In this pinned release str(None) produces '-threads None', rather than
    # falling back to the machine thread count. Use the same explicit value in
    # control and candidate, and record it separately from the hypothesis.
    raw['OPENROAD_THREADS'] = args.threads
    changes = {}
    if args.trial == 'electrical':
        changes['RUN_POST_GRT_DESIGN_REPAIR'] = True
    elif args.trial == 'timing':
        changes['RUN_POST_GRT_RESIZER_TIMING'] = True
    elif args.trial in ('cts', 'cts_branches'):
        changes['CTS_SINK_CLUSTERING_SIZE'] = args.cluster_size
    raw.update(changes)
    cts_trial = args.trial in ('cts', 'cts_branches')
    first_id = 'OpenROAD.CTS' if cts_trial else 'OpenROAD.RepairDesignPostGRT'
    first = next(i for i, step in enumerate(Classic.Steps) if step.id == first_id)
    steps = Classic.Steps[first:]
    extra_steps = {}
    if args.trial == 'cts_branches':
        script = Path(__file__).with_name('repair_clock_fanout.tcl').resolve()

        class RepairClockFanout(DetailedPlacement):
            id = 'OpenROAD.RepairClockFanout'
            name = 'Split overloaded CTS branches'

            def get_script_path(self):
                return str(script)

        steps.insert(1, RepairClockFanout)
        extra_steps[RepairClockFanout.id] = hashlib.sha256(script.read_bytes()).hexdigest()

    class TrialFlow(Classic):
        Steps = steps

    variables = TrialFlow.get_all_config_variables(TrialFlow)
    names = {v.name for v in variables}
    filtered = {k: v for k, v in raw.items() if k in names}
    config, _ = Config.load(filtered, flow_config_vars=variables,
                            design_dir=raw['DESIGN_DIR'], pdk_root=str(pdk),
                            _load_pdk_configs=False)
    input_stage = '34-openroad-detailedplacement' if cts_trial else '39-openroad-globalrouting'
    source_state = run / input_stage / 'state_out.json'
    state_text = json.dumps(relocate(json.loads(source_state.read_text()), replacements))
    initial = State.loads(state_text)
    initial.validate()
    output.mkdir(parents=True, exist_ok=False)
    manifest = {'trial': args.trial, 'changes': changes,
                'execution_overrides': {'OPENROAD_THREADS': args.threads},
                'extra_steps_sha256': extra_steps,
                'archive_root': str(root), 'input_stage': input_stage,
                'input_state_sha256': hashlib.sha256(source_state.read_bytes()).hexdigest(),
                'resolved_config_sha256': hashlib.sha256((run/'resolved.json').read_bytes()).hexdigest(),
                'status': 'running'}
    (output / 'experiment.json').write_text(json.dumps(manifest, indent=2)+'\n')
    (output / 'relocated_config.json').write_text(config.dumps())
    (output / 'relocated_state.json').write_text(state_text+'\n')
    try:
        TrialFlow(config).start(with_initial_state=initial, _force_run_dir=str(output / 'run'))
    except Exception as exc:
        manifest.update(status='rejected_or_failed', error=str(exc))
        raise
    else:
        manifest['status'] = 'flow_complete'
    finally:
        manifest['signoff_exit'] = final_gate(output)
        if manifest['status'] == 'flow_complete' and manifest['signoff_exit']:
            manifest['status'] = 'rejected_signoff'
        (output / 'experiment.json').write_text(json.dumps(manifest, indent=2)+'\n')
    if manifest['signoff_exit']:
        parser.exit(1, 'Strict post-route signoff rejected this trial; inspect post_route_signoff.log\n')


if __name__ == '__main__':
    main()
