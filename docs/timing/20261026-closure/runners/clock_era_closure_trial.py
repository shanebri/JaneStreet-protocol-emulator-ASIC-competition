"""Resume the best placement screen for isolated connectivity/electrical trials.

GDS LVS is diagnostic only. Extraction/repair screens retain the unchanged
strict post-route gate; no production source or acceptance rule is modified.
"""
import argparse
import hashlib
import json
from pathlib import Path

from check_signoff import REQUIRED_CORNERS
from physical_trial import final_gate, relocate


def plan(name):
    recipes = {
        'gds_lvs': {'changes': {'MAGIC_EXT_USE_GDS': True}, 'scope': 'diagnostic_gds_lvs',
                    'first': None, 'input': 'postroute'},
        'extract_control': {'changes': {}, 'scope': 'post_route_screen',
                            'first': 'OpenROAD.RCX', 'input': 'pre_rcx'},
        'extract_no_merge': {'changes': {'RCX_MERGE_VIA_WIRE_RES': False}, 'scope': 'post_route_screen',
                             'first': 'OpenROAD.RCX', 'input': 'pre_rcx'},
        'extract_odb': {'changes': {}, 'scope': 'post_route_screen',
                        'first': 'OpenROAD.RCX', 'input': 'pre_rcx',
                        'mechanism': 'read unchanged routed ODB instead of reparsing DEF'},
        'extract_ordered': {'changes': {}, 'scope': 'post_route_screen',
                            'first': 'OpenROAD.RCX', 'input': 'pre_rcx',
                            'mechanism': 'native orderWires graph normalization; same physical geometry required'},
        'extract_fine': {'changes': {}, 'scope': 'post_route_screen',
                         'first': 'OpenROAD.RCX', 'input': 'pre_rcx',
                         'mechanism': 'same physical inputs and RC rules; -max_res 0 disables wire resistance segment merging'},
        'route_control': {'changes': {}, 'scope': 'post_route_screen',
                          'first': 'OpenROAD.DetailedRouting', 'input': 'pre_drt', 'router_seed': 42},
        'route_seed43': {'changes': {}, 'scope': 'post_route_screen',
                         'first': 'OpenROAD.DetailedRouting', 'input': 'pre_drt', 'router_seed': 43},
        'grt_control': {'changes': {}, 'scope': 'post_route_screen',
                        'first': 'OpenROAD.GlobalRouting', 'input': 'pre_grt'},
        'grt_capacity25': {'changes': {'GRT_ADJUSTMENT': 0.25}, 'scope': 'post_route_screen',
                           'first': 'OpenROAD.GlobalRouting', 'input': 'pre_grt',
                           'mechanism': 'reroute with 25% coarse capacity reduction; unchanged physical DRC/layers/RC rules'},
        'clock_control': {'changes': {}, 'scope': 'post_route_screen',
                          'first': 'OpenROAD.CTS', 'input': 'pre_cts',
                          'mechanism': 'matched post-CTS legalization without clock repair'},
        'clock_cap8': {'changes': {'CTS_SINK_CLUSTERING_SIZE': 8}, 'scope': 'post_route_screen',
                       'first': 'OpenROAD.CTS', 'input': 'pre_cts',
                       'mechanism': 'retest existing clock recipe: cluster size 8 and split remaining branches to at most 8 loads'},
    }
    if name not in recipes:
        raise ValueError(f'Unsupported trial {name}')
    return recipes[name]


def validate_config(raw):
    if raw['CLOCK_PERIOD'] != 20 or raw['PDK'] != 'ihp-sg13cmos5l':
        raise ValueError('Clock/PDK differs from the approved baseline')
    if set(raw['STA_CORNERS']) != set(REQUIRED_CORNERS):
        raise ValueError('Required signoff corners differ')
    for key in ('SETUP_VIOLATION_CORNERS', 'HOLD_VIOLATION_CORNERS',
                'MAX_SLEW_VIOLATION_CORNERS', 'MAX_CAP_VIOLATION_CORNERS'):
        if raw[key] != ['*']:
            raise ValueError(f'Acceptance setting changed: {key}')


def unique(root, pattern):
    paths = list(root.glob(pattern))
    if len(paths) != 1:
        raise ValueError(f'Expected one {pattern}, got {len(paths)}')
    return paths[0]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--archive-root', type=Path, required=True)
    parser.add_argument('--pdk-root', type=Path, required=True)
    parser.add_argument('--trial', choices=('gds_lvs', 'extract_control', 'extract_no_merge', 'extract_odb', 'extract_ordered', 'extract_fine', 'route_control', 'route_seed43', 'grt_control', 'grt_capacity25', 'clock_control', 'clock_cap8'), required=True)
    parser.add_argument('--normalized-input', type=Path)
    parser.add_argument('--placement-base', type=Path)
    parser.add_argument('--lvs-proof', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--threads', type=int, default=8)
    args = parser.parse_args()
    base, archive, pdk, out = (p.resolve() for p in (args.base, args.archive_root, args.pdk_root, args.out))
    if out.exists() or args.threads < 1:
        parser.error('Output must be new and threads positive')
    recipe = plan(args.trial)
    original = json.loads((archive/'runs/wokwi/resolved.json').read_text())
    replacements = [(str(Path(original['DESIGN_DIR']).parent), str(archive)),
                    (original['PDK_ROOT'], str(pdk))]
    raw = relocate(original, replacements)
    if args.placement_base:
        raw.update(json.loads((args.placement_base.resolve()/'resolved_input.json').read_text()))
    raw.update(json.loads((base/'resolved_input.json').read_text()))
    validate_config(raw)
    raw.update(recipe['changes'])
    raw['OPENROAD_THREADS'] = args.threads
    from librelane.config import Config
    from librelane.flows.classic import Classic
    from librelane.state import State

    if recipe['scope'] == 'diagnostic_gds_lvs':
        ids = ('Magic.StreamOut', 'KLayout.StreamOut', 'Magic.SpiceExtraction',
               'Checker.IllegalOverlap', 'Netgen.LVS', 'Checker.LVS')
        steps = [step for step in Classic.Steps if step.id in ids]
        if {s.id for s in steps} != set(ids):
            raise ValueError('Pinned LVS steps do not match the diagnostic recipe')
        state_path = unique(base/'run', '*-openroad-stapostpnr/state_out.json')
    else:
        first = next(i for i, step in enumerate(Classic.Steps) if step.id == recipe['first'])
        last = next(i for i, step in enumerate(Classic.Steps) if step.id == 'OpenROAD.STAPostPNR')
        steps = list(Classic.Steps[first:last+1])
        if recipe['input'] == 'pre_cts':
            if args.placement_base is None or args.lvs_proof is None:
                parser.error('Clock trials require --placement-base and --lvs-proof')
            qualified = unique(base/'run', '*-openroad-stapostpnr/state_out.json')
            qmetrics = json.loads(qualified.read_text())['metrics']
            if any(qmetrics.get(f'timing__unannotated_net_filtered__count__corner:{c}') != 0 for c in REQUIRED_CORNERS):
                raise ValueError('Clock experiment base has incomplete parasitic coverage')
            proof_root = args.lvs_proof.resolve()
            proof = json.loads((proof_root/'experiment.json').read_text())
            proof_state = json.loads(unique(proof_root/'run', '*-checker-lvs/state_out.json').read_text())
            if (proof['status'] != 'diagnostic_complete' or proof['input_state_sha256'] != sha(qualified)
                    or proof_state['metrics'].get('design__lvs_error__count') != 0):
                raise ValueError('Missing or mismatched passing GDS LVS proof')
            state_path = unique(args.placement_base.resolve()/'run', '*-openroad-cts/state_in.json')
            from librelane.steps.openroad import DetailedPlacement
            clock_script = Path(__file__).with_name('repair_clock_fanout.tcl' if args.trial == 'clock_cap8'
                                                    else 'clock_legalize_control.tcl').resolve()

            class ClockRepair(DetailedPlacement):
                id = 'OpenROAD.RepairClockFanout'
                name = 'Controlled clock branch repair/legalization'

                def get_script_path(self):
                    return str(clock_script)

            steps.insert(1, ClockRepair)
        else:
            state_path = unique(base/'run', '*-openroad-detailedrouting/state_in.json' if recipe['input'] == 'pre_drt'
                                else '*-openroad-globalrouting/state_in.json' if recipe['input'] == 'pre_grt'
                                else '*-openroad-rcx/state_in.json')
        if args.trial in ('extract_odb', 'extract_ordered', 'extract_fine'):
            from librelane.steps.openroad import RCX
            from librelane.state import DesignFormat
            script = Path(__file__).with_name('rcx_fine.tcl' if args.trial == 'extract_fine' else 'rcx_from_odb.tcl').resolve()

            class ExtractODB(RCX):
                inputs = [DesignFormat.ODB, DesignFormat.DEF]

                def get_script_path(self):
                    return str(script)

            steps = [ExtractODB if step.id == 'OpenROAD.RCX' else step for step in steps]
        if recipe['input'] == 'pre_drt':
            from librelane.steps.openroad import DetailedRouting
            from librelane.common import get_script_dir
            source_script = Path(get_script_dir())/'openroad/drt.tcl'
            routing_text = source_script.read_text()
            if routing_text.count('lappend drt_args -or_seed 42') != 1:
                raise ValueError('Pinned routing seed recipe changed')
            routing_text = routing_text.replace('lappend drt_args -or_seed 42',
                                                f'lappend drt_args -or_seed {recipe["router_seed"]}')
            routing_script = out/'router.tcl'

            class SeedRoute(DetailedRouting):
                def get_script_path(self):
                    return str(routing_script)

            steps = [SeedRoute if step.id == 'OpenROAD.DetailedRouting' else step for step in steps]

    class Trial(Classic):
        Steps = steps

    variables = Trial.get_all_config_variables(Trial)
    names = {v.name for v in variables}
    config, _ = Config.load({k: v for k, v in raw.items() if k in names}, flow_config_vars=variables,
                            design_dir=raw['DESIGN_DIR'], pdk_root=str(pdk), _load_pdk_configs=False)
    state_text = state_path.read_text()
    if args.trial == 'extract_ordered':
        if args.normalized_input is None:
            parser.error('--normalized-input is required for extract_ordered')
        normalized = args.normalized_input.resolve()
        data = json.loads(state_text)
        data['odb'], data['def'] = str(normalized/'ordered.odb'), str(normalized/'ordered.def')
        state_text = json.dumps(data)
    initial = State.loads(state_text)
    initial.validate()
    out.mkdir(parents=True, exist_ok=False)
    if recipe['input'] == 'pre_drt':
        routing_script.write_text(routing_text)
    manifest = dict(recipe, trial=args.trial, base_trial=str(base), status='running',
                    input_state=str(state_path), input_state_sha256=sha(state_path),
                    input_views_sha256={key: sha(Path(initial[key])) for key in ('odb', 'def', 'nl', 'sdc')
                                        if initial.get(key) is not None},
                    runner_sha256=sha(Path(__file__)),
                    extra_script_sha256=(sha(script) if args.trial in ('extract_odb', 'extract_ordered', 'extract_fine')
                                         else sha(routing_script) if recipe['input'] == 'pre_drt'
                                         else sha(clock_script) if recipe['input'] == 'pre_cts' else None),
                    execution_overrides={'OPENROAD_THREADS': args.threads})
    (out/'experiment.json').write_text(json.dumps(manifest, indent=2)+'\n')
    (out/'resolved_input.json').write_text(config.dumps())
    try:
        Trial(config).start(with_initial_state=initial, _force_run_dir=str(out/'run'))
    except Exception as exc:
        manifest.update(status='rejected_or_failed', error=str(exc))
        raise
    else:
        manifest['status'] = 'diagnostic_complete' if args.trial == 'gds_lvs' else 'screen_complete'
    finally:
        if args.trial != 'gds_lvs':
            manifest['signoff_exit'] = final_gate(out)
            if manifest['status'] == 'screen_complete' and manifest['signoff_exit']:
                manifest['status'] = 'rejected_signoff'
        (out/'experiment.json').write_text(json.dumps(manifest, indent=2)+'\n')
    if manifest.get('signoff_exit'):
        parser.exit(1, 'Strict extracted signoff rejected the screen; inspect post_route_signoff.log\n')


if __name__ == '__main__':
    main()
