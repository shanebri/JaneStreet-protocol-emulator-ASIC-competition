"""Audit a one-factor implementation pair and print its extracted comparison."""
import argparse
import json
from pathlib import Path

from check_signoff import REQUIRED_CORNERS, check_metrics
from collect_implementation import VECTOR_KEYS, selected_metrics
from implementation_trial import trial_plan


def audit_pair(control, candidate, before, after):
    pair = (control['trial'], candidate['trial'])
    expected = {
        ('placement_control', 'placement_timing'): {'PL_TIMING_DRIVEN': [False, True]},
        ('placement_timing', 'placement_corners'): {},
        ('mapping_control', 'mapping_delay4'): {'SYNTH_STRATEGY': ['AREA 0', 'DELAY 4']},
        ('mapping_control', 'mapping_delay0'): {'SYNTH_STRATEGY': ['AREA 0', 'DELAY 0']},
    }
    if pair not in expected:
        raise ValueError(f'Unsupported comparison {pair}')
    for key in ('source_sha256', 'input_state_sha256', 'resolved_config_sha256', 'execution_overrides'):
        if control[key] != candidate[key]:
            raise ValueError(f'Mismatched pair provenance: {key}')
    for manifest in (control, candidate):
        plan = trial_plan(manifest['trial'])
        for key in ('changes', 'step_overrides', 'input_stage'):
            if manifest[key] != plan[key]:
                raise ValueError(f'Unexpected trial recipe: {manifest["trial"]} {key}')
    ignored = {'meta'}
    if pair[0] == 'mapping_control':
        if not control['template_sha256'] or control['template_sha256'] != candidate['template_sha256']:
            raise ValueError('Mapping templates differ or are missing')
        # Frozen paths differ by trial directory, but their source/template
        # contents were hashed above. Do not ignore any other design setting.
        ignored.update(('DESIGN_DIR', 'VERILOG_FILES', 'FP_DEF_TEMPLATE'))
    differences = {k: [before.get(k), after.get(k)] for k in before.keys() | after.keys()
                   if k not in ignored and before.get(k) != after.get(k)}
    if differences != expected[pair]:
        raise ValueError(f'Unexpected config differences: {differences}; expected {expected[pair]}')
    return {'global_config_differences': differences,
            'control_step_overrides': control['step_overrides'],
            'candidate_step_overrides': candidate['step_overrides']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    read = lambda folder, name: json.loads((folder/name).read_text())
    control, candidate = (read(p, 'experiment.json') for p in (args.control, args.candidate))
    audit = audit_pair(control, candidate, read(args.control, 'resolved_input.json'),
                       read(args.candidate, 'resolved_input.json'))
    a, b = (selected_metrics(read(p, 'metrics.json')) for p in (args.control, args.candidate))
    labels = ('Setup WS (ns)', 'Hold WS (ns)', 'Setup TNS (ns)', 'Hold TNS (ns)',
              'Setup endpoints', 'Hold endpoints', 'Slew violations', 'Cap violations',
              'Fanout violations', 'Filtered annotation gaps')
    fmt = lambda values: ' / '.join(f'{v:.6f}' if isinstance(v, float) else str(v) for v in values)
    lines = [f'# {candidate["trial"]} versus {control["trial"]}', '',
             'Vectors: slow / typical / fast. Delta = candidate minus control.', '',
             '| Metric | Control | Candidate | Delta | Candidate |', '| --- | --- | --- | --- | --- |']
    for label, key in zip(labels, VECTOR_KEYS):
        av, bv = ([m[f'{key}__corner:{c}'] for c in REQUIRED_CORNERS] for m in (a, b))
        passed = all(v >= 0 for v in bv) if key.endswith('__ws') else all(v == 0 for v in bv)
        lines.append(f'| {label} | {fmt(av)} | {fmt(bv)} | {fmt([y-x for x,y in zip(av,bv)])} | '
                     + ('PASS' if passed else 'FAIL')+' |')
    for label, key in (('Standard-cell area excluding filler (um2)', 'design__instance__area__stdcell'),
                       ('Standard-cell utilization', 'design__instance__utilization__stdcell'),
                       ('Inferred latches', 'design__inferred_latch__count'),
                       ('Unmapped cells', 'design__instance_unmapped__count'),
                       ('Synthesis check errors', 'synthesis__check_error__count')):
        lines.append(f'| {label} | {a[key]} | {b[key]} | {b[key]-a[key]:.6f} | '
                     + ('INFO' if 'area' in key or 'utilization' in key else 'PASS' if b[key] == 0 else 'FAIL')+' |')
    lines += ['', 'Strict gate: control '+('FAIL' if check_metrics(a) else 'PASS')
              +'; candidate '+('FAIL' if check_metrics(b) else 'PASS')+'.', '',
              'This is extracted screening evidence. Full GDS/DRC/LVS/antenna/precheck and final '
              'gate-level verification remain required before acceptance.']
    with args.out.open('x') as stream:
        stream.write('\n'.join(lines)+'\n')
    with args.out.with_suffix('.json').open('x') as stream:
        json.dump(audit, stream, indent=2)
        stream.write('\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
