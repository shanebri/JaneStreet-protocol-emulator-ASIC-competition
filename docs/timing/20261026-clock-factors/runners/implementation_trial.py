"""Isolated placement/mapping screens in the pinned LibreLane environment.

Never edits production configuration. Every screen ends at extracted STA and
the unchanged strict gate; passing a screen is not fabrication qualification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

from check_signoff import REQUIRED_CORNERS
from physical_trial import final_gate, relocate


def trial_plan(name):
    plans = {
        'placement_control': ({}, {}),
        'placement_timing': ({'PL_TIMING_DRIVEN': True}, {}),
        'placement_corners': ({'PL_TIMING_DRIVEN': True},
                              {'OpenROAD.GlobalPlacement': {'PNR_CORNERS': list(REQUIRED_CORNERS)}}),
        'mapping_control': ({}, {}),
        'mapping_delay4': ({'SYNTH_STRATEGY': 'DELAY 4'}, {}),
        'mapping_delay0': ({'SYNTH_STRATEGY': 'DELAY 0'}, {}),
    }
    if name not in plans:
        raise ValueError(f'Unknown trial: {name}')
    changes, overrides = plans[name]
    return {'changes': changes, 'step_overrides': overrides,
            'input_stage': '27-odb-applydeftemplate' if name.startswith('placement_') else None}


def validate_baseline(raw):
    expected = {'CLOCK_PERIOD': 20, 'PDK': 'ihp-sg13cmos5l',
                'SYNTH_STRATEGY': 'AREA 0', 'SYNTH_CORNER': None,
                'PL_TIMING_DRIVEN': False, 'PNR_CORNERS': None}
    for key, value in expected.items():
        if raw.get(key) != value:
            raise ValueError(f'Unexpected baseline {key}: {raw.get(key)!r}; expected {value!r}')
    if set(raw['STA_CORNERS']) != set(REQUIRED_CORNERS):
        raise ValueError('Required signoff corners changed')
    for key in ('SETUP_VIOLATION_CORNERS', 'HOLD_VIOLATION_CORNERS',
                'MAX_SLEW_VIOLATION_CORNERS', 'MAX_CAP_VIOLATION_CORNERS'):
        if raw[key] != ['*']:
            raise ValueError(f'Acceptance setting changed: {key}')


def template_fingerprint(text):
    die = re.search(r'\bDIEAREA\s+(.*?)\s*;', text, re.S)
    pins = re.search(r'\bPINS\s+\d+\s*;(.*?)END PINS', text, re.S)
    if not die or not pins:
        raise ValueError('DEF die/pin section missing')
    signals = {}
    for name, body in re.findall(r'-\s+(\S+)\s+(.*?);', pins[1], re.S):
        if re.search(r'\+\s+USE\s+(POWER|GROUND)\b', body):
            continue
        # Compare net, direction, layer rectangles, location and orientation.
        body = re.sub(r'\bFIXED\b', 'PLACED', body)
        signals[name] = re.sub(r'\s+', '', body)
    if len(signals) != 43:
        raise ValueError(f'Expected 43 signal pins, found {len(signals)}')
    return re.sub(r'\s+', '', die[1]), signals


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-root', type=Path, required=True)
    parser.add_argument('--pdk-root', type=Path, required=True)
    parser.add_argument('--design-root', type=Path, required=True)
    parser.add_argument('--template', type=Path, help='Required only for fresh mapping trials')
    parser.add_argument('--trial', choices=('placement_control', 'placement_timing', 'placement_corners',
                                          'mapping_control', 'mapping_delay4', 'mapping_delay0'), required=True)
    parser.add_argument('--threads', type=int, default=8)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.threads < 1:
        parser.error('--threads must be positive')
    root, pdk, design, out = (p.resolve() for p in
                              (args.archive_root, args.pdk_root, args.design_root, args.out))
    plan = trial_plan(args.trial)
    run = root/'runs/wokwi'
    original = json.loads((run/'resolved.json').read_text())
    validate_baseline(original)
    if out.exists():
        parser.error('Output directory already exists; never reuse experiment evidence')
    template = args.template.resolve() if args.template else None
    if plan['input_stage'] is None:
        if template is None:
            parser.error('--template is required for mapping trials')
        applied = run/'27-odb-applydeftemplate/tt_um_shanebri_top.def'
        if template_fingerprint(template.read_text()) != template_fingerprint(applied.read_text()):
            parser.error('Template boundary/signal pins differ from archived applied 8x4 template')

    # Defer SDK imports so the plan, constraint guards and template audit can be
    # tested without pretending a fake SDK is a physical timing environment.
    from librelane.config import Config
    from librelane.flows.classic import Classic
    from librelane.state import State
    from librelane.steps.openroad import GlobalPlacement

    replacements = [(str(Path(original['DESIGN_DIR']).parent), str(root)),
                    (original['PDK_ROOT'], str(pdk))]
    raw = relocate(original, replacements)
    raw.update(plan['changes'])
    raw['OPENROAD_THREADS'] = args.threads
    first = (next(i for i, step in enumerate(Classic.Steps)
                  if step.id == 'OpenROAD.GlobalPlacement') if plan['input_stage'] else 0)
    last = next(i for i, step in enumerate(Classic.Steps) if step.id == 'OpenROAD.STAPostPNR')
    steps = list(Classic.Steps[first:last+1])
    if plan['step_overrides']:
        views = plan['step_overrides']['OpenROAD.GlobalPlacement']['PNR_CORNERS']

        class PlacementViews(GlobalPlacement):
            def __init__(self, config, *args, **kwargs):
                # Override only this step's copy, including its saved config.json.
                super().__init__(config.copy(PNR_CORNERS=list(views)), *args, **kwargs)

        steps = [PlacementViews if step.id == 'OpenROAD.GlobalPlacement' else step for step in steps]

    class Screen(Classic):
        Steps = steps

    out.mkdir(parents=True, exist_ok=False)
    source_names = []
    for line in (design/'info.yaml').read_text().split('  source_files:\n', 1)[1].splitlines():
        if not line.startswith('    - '):
            break
        source_names.append(line.split('"')[1])
    source_hashes = {name: sha(design/'src'/name) for name in source_names}
    source_state = None
    initial = None
    if plan['input_stage']:
        source_state = run/plan['input_stage']/'state_out.json'
        state_text = json.dumps(relocate(json.loads(source_state.read_text()), replacements))
        initial = State.loads(state_text)
        initial.validate()
        (out/'relocated_state.json').write_text(state_text+'\n')
    else:
        # Freeze the unchanged design before synthesis; do not run from mutable RTL.
        frozen = out/'frozen'
        shutil.copytree(design/'src', frozen/'src')
        shutil.copy2(design/'info.yaml', frozen/'info.yaml')
        shutil.copy2(template, frozen/'template.def')
        raw['DESIGN_DIR'] = str(frozen/'src')
        raw['VERILOG_FILES'] = [str(frozen/'src'/name) for name in source_names]
        raw['FP_DEF_TEMPLATE'] = str(frozen/'template.def')
    variables = Screen.get_all_config_variables(Screen)
    names = {v.name for v in variables}
    config, _ = Config.load({k: v for k, v in raw.items() if k in names},
                            flow_config_vars=variables, design_dir=raw['DESIGN_DIR'],
                            pdk_root=str(pdk), _load_pdk_configs=False)
    (out/'resolved_input.json').write_text(config.dumps())
    manifest = dict(plan, trial=args.trial, status='running', scope='post_route_screen',
                    archive_root=str(root), source_sha256=source_hashes,
                    resolved_config_sha256=sha(run/'resolved.json'),
                    input_state_sha256=sha(source_state) if source_state else None,
                    runner_sha256=sha(Path(__file__)),
                    template_sha256=sha(template) if template else None,
                    execution_overrides={'OPENROAD_THREADS': args.threads})
    (out/'experiment.json').write_text(json.dumps(manifest, indent=2)+'\n')
    try:
        Screen(config).start(with_initial_state=initial, _force_run_dir=str(out/'run'))
    except Exception as exc:
        manifest.update(status='rejected_or_failed', error=str(exc))
        raise
    else:
        manifest['status'] = 'screen_complete'
    finally:
        manifest['signoff_exit'] = final_gate(out)
        if manifest['status'] == 'screen_complete' and manifest['signoff_exit']:
            manifest['status'] = 'rejected_signoff'
        (out/'experiment.json').write_text(json.dumps(manifest, indent=2)+'\n')
    if manifest['signoff_exit']:
        parser.exit(1, 'Strict extracted signoff rejected this screen; inspect post_route_signoff.log\n')


if __name__ == '__main__':
    main()
