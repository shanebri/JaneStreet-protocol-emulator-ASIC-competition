"""Bounded, cycle-preserving timing campaign on an immutable qualified parent.

Inventory uses the parent's actual extracted reports and architectural Q nets.
Physical experiments use fresh directories and retain the active repair recipe.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from check_signoff import REQUIRED_CORNERS, check_metrics, find_state
from diagnose_cones import paths
from refactor_trial import REPO, sha, validated_parent, replace_once
from summarize_refactor_endpoints import register_map


ACTIVATION = REPO / 'docs/timing/20261030-control-refactor/activation.json'


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def reference():
    from activate_refactor import input_comparison, replay_inputs
    receipt = json.loads(ACTIVATION.read_text())
    parent = Path(receipt['candidate'])
    state, qualification = validated_parent(parent)
    if (receipt.get('status') != 'complete' or receipt.get('activated') is not True
            or sha(state) != receipt['run_state_sha256']
            or sha(qualification) != receipt['qualification_manifest_sha256']
            or sha(REPO / 'tools/timing/production/last-fanout.json') != receipt['active_recipe_sha256']):
        raise ValueError('Active qualification receipt or recipe differs')
    inputs = input_comparison(parent)
    replay_inputs(parent)
    return parent, state, dict(
        activation_sha256=sha(ACTIVATION), parent=str(parent), state=str(state),
        state_sha256=sha(state), qualification=str(qualification),
        qualification_sha256=sha(qualification), active_inputs_checked=len(inputs),
        active_recipe_sha256=receipt['active_recipe_sha256'])


def arcs(report):
    """Read output-cell arcs from the data portion, excluding clock paths."""
    data = report.split('data arrival time', 1)[0]
    if 'input external delay' in data:
        data = data.split('input external delay', 1)[1]
    else:
        q = re.search(r'^.*[\^v] \S+/Q \(sg13\w+\).*$', data, re.M)
        if q:
            data = data[q.end():]
    result = []
    for match in re.finditer(r'^\s*([\d. +\-]+)\s+[\^v]\s+(\S+/[XY])\s+\((sg13\w+)\)', data, re.M):
        values = match[1].split()
        if len(values) < 3:
            raise ValueError('Malformed timing arc: ' + match[0])
        result.append(dict(pin=match[2], master=match[3], delay_ns=float(values[-2]),
                           fanout=int(values[0]) if len(values) >= 5 else None,
                           cap_pf=float(values[1]) if len(values) >= 5 else None))
    return result


def inventory(out):
    parent, state_path, binding = reference()
    state = json.loads(state_path.read_text())
    out.mkdir(parents=True, exist_ok=False)
    (out / 'paths').mkdir()
    reverse = {cell: name for name, cell in register_map(Path(state['nl']).read_text()).items()}
    result = dict(status='complete', scope='Immutable qualified-parent endpoint inventory',
                  reference=binding, reports={}, corners={})
    for corner in REQUIRED_CORNERS:
        corner_rows = {}
        for delay, analysis in (('max', 'setup'), ('min', 'hold')):
            source = state_path.parent / corner / (delay + '.rpt')
            records = paths(source.read_text())
            records.sort(key=lambda row: row['slack'])
            result['reports'][str(source)] = sha(source)
            worst_by_endpoint = {}
            for row in records:
                # Recovery/removal checks are retained, but never confused with D paths.
                endpoint = row['endpoint']
                key = endpoint
                if key in worst_by_endpoint:
                    continue
                name = reverse.get(endpoint, endpoint)
                row_arcs = arcs(row['text'])
                item = dict(endpoint=endpoint, architectural_q=name, start=row['start'],
                            slack_ns=row['slack'], largest_data_arcs=sorted(
                                row_arcs, key=lambda arc: arc['delay_ns'], reverse=True)[:6])
                worst_by_endpoint[key] = item
                if len(worst_by_endpoint) <= 20:
                    report = out / 'paths' / f'{corner}-{analysis}-{len(worst_by_endpoint):02}.rpt'
                    report.write_text(row['text'])
                    item['report'] = str(report)
            selected = list(worst_by_endpoint.values())
            if not selected:
                raise ValueError('Missing native endpoint reports')
            metric = state['metrics'][f'timing__{analysis}__ws__corner:{corner}']
            if abs(selected[0]['slack_ns'] - metric) > 0.000001:
                raise ValueError('Native report minimum differs from qualified state')
            family_counts = Counter(re.sub(r'\[\d+\]', '[]', item['architectural_q']) for item in selected[:50])
            corner_rows[analysis] = dict(worst_slack_ns=metric, reported_paths=len(records),
                distinct_endpoints=len(selected), top50_families=dict(family_counts), endpoints=selected[:100])
        result['corners'][corner] = corner_rows
    write_json(out / 'inventory.json', result)
    (out / 'inventory_runner.py').write_bytes(Path(__file__).read_bytes())
    for corner, checks in result['corners'].items():
        for analysis, details in checks.items():
            print(corner, analysis, 'worst_ns=', details['worst_slack_ns'])
            for row in details['endpoints'][:10]:
                print(' ', row['architectural_q'], row['start'].split(' (')[0], row['slack_ns'],
                      [(arc['pin'], arc['delay_ns']) for arc in row['largest_data_arcs'][:2]])


def prepare(out):
    import odb
    from audit_clock_tree import snapshot
    from prepare_refactor import feedback_operation
    from resolve_eco_targets import make_contract, resolve
    parent = Path(json.loads((out / 'inventory.json').read_text())['reference']['parent'])
    source = parent / 'run/56-openroad-lastfanoutrepair/state_in.json'
    state = json.loads(source.read_text())
    db = odb.dbDatabase.create(); odb.read_db(db, state['odb'])
    block = db.getChip().getBlock()
    data = snapshot(block)
    baseline = json.loads((REPO / 'tools/timing/production/last-fanout.json').read_text())
    base_ops = resolve(data, baseline)
    hold_ops = json.loads(json.dumps(base_ops))
    changes = []
    # The two already repaired D boundaries get a characterized transparent
    # delay cell in place of their existing buffer; no duplicate source repair.
    for bit in (3, 6):
        op = feedback_operation(block, data, f'pio.engines[1].core.isr[{bit}]')
        existing = [entry for entry in hold_ops if entry.get('target') == op['target']]
        if len(existing) != 1:
            raise ValueError('Qualified D-boundary repair missing or ambiguous')
        existing[0]['buffer_cell'] = 'sg13cmos5l_dlygate4sd1_1'
        changes.append(dict(register=f'engine1 ISR[{bit}]', kind='transparent-buffer-to-delay', target=op['target']))
    for register in ('pio.engines[1].core.isr[7]',
                     'pio.engines[0].core.fetch.words[20][11]',
                     'pio.engines[0].core.fetch.words[20][12]'):
        op = feedback_operation(block, data, register)
        op['buffer_cell'] = 'sg13cmos5l_dlygate4sd1_1'
        hold_ops.append(op)
        changes.append(dict(register=register, kind='transparent-D-delay', target=op['target']))
    # The measured slow path's largest cell arc drives two loads and a long
    # net. A local strong buffer tests isolation of that wire from the weak AOI.
    setup = dict(kind='buffer', target='_28912_/Y', old='sg13cmos5l_a221oi_1', max_loads=1000)
    variants = dict(control=base_ops, hold_cluster=hold_ops,
                    setup_local=base_ops + [setup], combined=hold_ops + [setup])
    required = {op.get('buffer_cell', 'sg13cmos5l_buf_4') for ops in variants.values()
                for op in ops if op['kind'] == 'buffer'}
    for suffix in ('slow_1p08V_125C', 'typ_1p20V_25C', 'fast_1p32V_m40C'):
        library = Path('/home/shane/eda/pdk-2bbec755/ihp-sg13cmos5l/libs.ref/sg13cmos5l_stdcell/lib') / ('sg13cmos5l_stdcell_' + suffix + '.lib')
        available = set(re.findall(r'cell\s*\(\s*([A-Za-z0-9_]+)\s*\)', library.read_text()))
        if not required <= available:
            raise ValueError('Missing required repair cell corner: ' + str(library))
    targets = []
    for name in ('_28912_', '_17920_', '_17925_', '_17215_'):
        inst = block.findInst(name)
        output = inst.findITerm('Y')
        targets.append(dict(instance=name, master=inst.getMaster().getName(),
            location_dbu=inst.getLocation(),
            loads=[dict(pin=sink[0] + '/' + sink[1], location_dbu=block.findInst(sink[0]).getLocation())
                   for sink in data[3][output.getNet().getName()]]))
    contracts = out / 'contracts'; contracts.mkdir(exist_ok=False)
    for name, ops in variants.items():
        contract = make_contract(data, ops)
        if resolve(data, contract) != ops:
            raise ValueError('Candidate contract does not self-resolve')
        contract['reference_odb_sha256'] = sha(state['odb'])
        write_json(contracts / (name + '.json'), contract)
        print('Prepared', name, 'operations=', len(ops), flush=True)
    write_json(out / 'preparation.json', dict(status='complete', input_state=str(source),
        input_state_sha256=sha(source), input_odb_sha256=sha(state['odb']),
        parent_recipe_sha256=sha(REPO / 'tools/timing/production/last-fanout.json'),
        hold_changes=changes, setup_targets=targets,
        required_transparent_models=sorted(required),
        scope='Fresh structural contracts; no registers, clocks or architectural cycles changed'))


def verify_baseline(campaign):
    inventory_data = json.loads((campaign / 'inventory.json').read_text())
    parent = Path(inventory_data['reference']['parent'])
    parent_replay = next((parent / 'run').glob('*-pio-routeacceptance/qualification/replay/manifest.json'))
    expected = json.loads(parent_replay.read_text())
    actual_path = campaign / 'baseline_replay/manifest.json'
    actual = json.loads(actual_path.read_text())
    if actual.get('status') != 'complete' or actual['sessions'] != expected['sessions']:
        raise ValueError('Fresh nine-session baseline differs from the qualified parent')
    if len(actual['sessions']) != 9:
        raise ValueError('Incomplete baseline matrix')
    for name, digest in actual['sha256'].items():
        if sha(name) != digest:
            raise ValueError('Fresh baseline input changed: ' + name)
    for session in actual['sessions']:
        report = actual_path.parent / (session['corner'] + '-' + session['mode']) / 'coverage.rpt'
        if report.read_text().strip():
            raise ValueError('Baseline timing coverage is incomplete')
    return dict(status='pass', manifest_sha256=sha(actual_path),
                all_nine_sessions_equal_qualified_parent=True, coverage_complete=True)


def screen(out, case):
    from closure_trial import validate_config
    from librelane.config import Config
    from librelane.flows.classic import Classic
    from librelane.state import State
    from production_flow import PIOClosure, LastFanoutRepair
    from headroom_eco import render_script
    campaign = out.parent
    baseline_validation = verify_baseline(campaign)
    inventory_data = json.loads((campaign / 'inventory.json').read_text())
    parent = Path(inventory_data['reference']['parent'])
    parent_state = Path(inventory_data['reference']['state'])
    if sha(parent_state) != inventory_data['reference']['state_sha256']:
        raise ValueError('Qualified parent state changed')
    preparation = json.loads((campaign / 'preparation.json').read_text())
    source = Path(preparation['input_state'])
    if sha(source) != preparation['input_state_sha256']:
        raise ValueError('Prepared source state changed')
    contract = campaign / 'contracts' / (case + '.json')
    raw = json.loads((parent / 'run/resolved.json').read_text())
    raw['PIO_INCREMENTAL_ECO_CONTRACTS'][1] = str(contract)
    validate_config(raw)
    class Repair(LastFanoutRepair):
        def render_script(self, operations):
            return render_script(operations)

        def run(self, state_in, **kwargs):
            import production_flow
            previous = production_flow.run_tool
            def checked(step, name, arguments):
                return previous(step, 'headroom_eco.py' if name == 'audit_data_eco.py' else name, arguments)
            production_flow.run_tool = checked
            try:
                return super().run(state_in, **kwargs)
            finally:
                production_flow.run_tool = previous
    first = PIOClosure.Steps.index(LastFanoutRepair)
    last = next(i for i, step in enumerate(PIOClosure.Steps) if step.id == 'OpenROAD.STAPostPNR')
    class Screen(Classic):
        Steps = [Repair, *PIOClosure.Steps[first + 1:last + 1]]
        gating_config_vars = PIOClosure.gating_config_vars
    variables = PIOClosure.get_all_config_variables(PIOClosure)
    names = {v.name for v in variables}
    config, _ = Config.load({k: v for k, v in raw.items() if k in names}, flow_config_vars=variables,
        design_dir=raw['DESIGN_DIR'], pdk_root=raw['PDK_ROOT'], _load_pdk_configs=False)
    initial = State.loads(source.read_text()); initial.validate()
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / 'resolved_input.json', json.loads(config.dumps()))
    manifest = dict(status='running', scope='Diagnostic physical tail; not production qualification',
        case=case, parent_state=str(parent_state), parent_state_sha256=sha(parent_state),
        contract=str(contract), contract_sha256=sha(contract), source_state_sha256=sha(source),
        source_odb_sha256=sha(initial['odb']), runner_sha256=sha(Path(__file__)))
    manifest['baseline_validation'] = baseline_validation
    write_json(out / 'experiment.json', manifest)
    try:
        Screen(config).start(with_initial_state=initial, _force_run_dir=str(out / 'run'))
        state_path = find_state(out / 'run')
        metrics = json.loads(state_path.read_text())['metrics']
        errors = check_metrics(metrics)
        parent_metrics = json.loads(parent_state.read_text())['metrics']
        margins = {corner: {analysis: dict(parent_ns=parent_metrics[f'timing__{analysis}__ws__corner:{corner}'],
            candidate_ns=metrics[f'timing__{analysis}__ws__corner:{corner}'],
            consumed_ns=parent_metrics[f'timing__{analysis}__ws__corner:{corner}'] - metrics[f'timing__{analysis}__ws__corner:{corner}'])
            for analysis in ('setup', 'hold')} for corner in REQUIRED_CORNERS}
        manifest.update(status='rejected_signoff' if errors else 'screen_complete',
            strict_errors=errors, margins=margins, state=str(state_path), state_sha256=sha(state_path),
            route_drc=metrics.get('route__drc_errors'), antenna=metrics.get('route__antenna_violation__count'))
        print(json.dumps(dict(case=case, status=manifest['status'], margins=margins), indent=2), flush=True)
    except Exception as exc:
        manifest.update(status='failed', error=str(exc))
        raise
    finally:
        write_json(out / 'experiment.json', manifest)


def production(out, case):
    campaign = out.parent
    inventory_data = json.loads((campaign / 'inventory.json').read_text())
    parent = Path(inventory_data['reference']['parent'])
    state, qualification = validated_parent(parent)
    if sha(state) != inventory_data['reference']['state_sha256']:
        raise ValueError('Qualified parent changed')
    screen_record = json.loads((campaign / case / 'experiment.json').read_text())
    control = json.loads((campaign / 'control/experiment.json').read_text())
    if (control.get('status') != 'screen_complete'
            or any(abs(row['consumed_ns']) > 0.000001 for checks in control['margins'].values() for row in checks.values())
            or screen_record['source_state_sha256'] != control['source_state_sha256']
            or screen_record['source_odb_sha256'] != control['source_odb_sha256']):
        raise ValueError('Candidate lacks an exactly reproduced, matched-source control')
    if (screen_record.get('status') != 'screen_complete' or screen_record['strict_errors']
            or screen_record['route_drc'] != 0 or screen_record['antenna'] != 0):
        raise ValueError('Selected hypothesis lacks a clean routed screen')
    contract = campaign / 'contracts' / (case + '.json')
    if sha(contract) != screen_record['contract_sha256']:
        raise ValueError('Screened contract changed')
    out.mkdir(parents=True, exist_ok=False)
    (out / 'run').mkdir()
    frozen = json.loads((parent / 'frozen_inputs.json').read_text())
    for name, expected in frozen.items():
        source = parent / name
        if sha(source) != expected:
            raise ValueError('Qualified parent frozen input changed: ' + name)
        if name in ('scope.json', 'parent_comparison_selfcheck.json'):
            continue
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    shutil.copy2(state, out / 'parent/69-openroad-stapostpnr/state_out.json')
    shutil.copy2(contract, out / 'tools/timing/production/last-fanout.json')
    shutil.copy2(REPO / 'tools/timing/headroom_eco.py', out / 'tools/timing/headroom_eco.py')
    shutil.copy2(Path(__file__), out / 'campaign_runner.py')
    tooling = REPO / 'test/sim_build/production_tooling'
    (out / 'tt').symlink_to(tooling / 'tt', target_is_directory=True)
    flow = out / 'tools/timing/production_flow.py'
    text = flow.read_text()
    text = replace_once(text, 'from incremental_trial import incremental_script',
                        'from incremental_trial import incremental_script\nfrom headroom_eco import render_script as headroom_script')
    text = replace_once(text, '    contract_index = 1\n',
                        '    contract_index = 1\n\n    def render_script(self, operations):\n        return headroom_script(operations)\n')
    text = replace_once(text, "run_tool(self, 'audit_data_eco.py',",
                        "run_tool(self, 'headroom_eco.py' if isinstance(self, LastFanoutRepair) else 'audit_data_eco.py',")
    flow.write_text(text)
    comparator = out / 'tools/timing/compare_timing.py'
    comparator.write_text(replace_once(comparator.read_text(), '            if consumed > 0:',
                                      '            if consumed > 0.000001:'))
    subprocess.run([sys.executable, str(comparator), '--parent', str(out / 'parent/69-openroad-stapostpnr/state_out.json'),
                    '--candidate', str(out / 'parent/69-openroad-stapostpnr/state_out.json'),
                    '--out', str(out / 'parent_comparison_selfcheck.json')], check=True)
    # This timing-only campaign retains all six parent minima as its release
    # reserves. The tolerance classifies numeric ties; strict signoff is intact.
    write_json(out / 'scope.json', dict(qualified_source_parent='bb7c5ef3c54a7ae2733bbfae82aa940016375007',
        variant='headroom_' + case, production_flow='PIOClosure', tooling_path=str(tooling),
        parent_state_sha256=sha(state), incremental_parent=str(parent),
        screen=str(campaign / case), screen_state_sha256=screen_record['state_sha256'],
        acceptance='Strict signoff and all six fixed active-parent reserves; numerical comparison tolerance 0.000001 ns',
        qualification='Full normal production, nine-session replay, actual-GDS LVS/DRC, precheck and 39 gate tests',
        active_production_modified=False))
    files = [p for p in out.rglob('*') if p.is_file() and not p.is_symlink() and 'tt' not in p.relative_to(out).parts]
    write_json(out / 'frozen_inputs.json', {str(p.relative_to(out)): sha(p) for p in sorted(files)})
    command = ['/nix/var/nix/profiles/default/bin/nix', 'develop', '--offline', '--command',
               'python3', '-B', str(out / 'trial_runner.py'), '--out', str(out), '--worker']
    with (out / 'launcher.log').open('x') as log:
        proc = subprocess.Popen(command, cwd='/home/shane/eda/librelane-3.1.0.dev3', stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
    write_json(out / 'process.json', dict(pid=proc.pid, command=command))
    print('Launched fresh normal production candidate', proc.pid, out, flush=True)


def summarize(campaign):
    source = json.loads((campaign / 'inventory.json').read_text())
    result = dict(scope='Bounded diagnostic comparison; production qualification is separate',
                  reference=source['reference'], baseline_validation=verify_baseline(campaign),
                  candidates={})
    control_path = campaign / 'control/experiment.json'
    control = json.loads(control_path.read_text()) if control_path.is_file() else None
    control_exact = bool(control and control.get('status') == 'screen_complete' and
        all(abs(row['consumed_ns']) <= 0.000001 for checks in control['margins'].values() for row in checks.values()))
    result['matched_control_reproduces_parent'] = control_exact
    for case in ('control', 'hold_cluster', 'setup_local', 'combined'):
        record_path = campaign / case / 'experiment.json'
        if not record_path.is_file():
            continue
        record = json.loads(record_path.read_text())
        row = dict(experiment=record)
        if 'state' in record:
            state_path = Path(record['state'])
            if sha(state_path) != record['state_sha256']:
                raise ValueError('Candidate extracted state changed')
            state = json.loads(state_path.read_text())
            metric = state['metrics']
            row['area_um2'] = metric.get('design__instance__area__stdcell')
            row['all_six_parent_reserves_preserved'] = all(
                item['consumed_ns'] <= 0.000001 for checks in record['margins'].values() for item in checks.values())
            mapping = {cell: name for name, cell in register_map(Path(state['nl']).read_text()).items()}
            row['limiting_paths'] = {}
            row['local_endpoint_margins'] = {}
            for corner in REQUIRED_CORNERS:
                for delay, analysis in (('max', 'setup'), ('min', 'hold')):
                    records = paths((state_path.parent / corner / (delay + '.rpt')).read_text())
                    records.sort(key=lambda p: p['slack'])
                    worst = records[0]
                    row['limiting_paths'][corner + '-' + analysis] = dict(
                        start=worst['start'], endpoint=worst['endpoint'],
                        architectural_q=mapping.get(worst['endpoint'], worst['endpoint']), slack_ns=worst['slack'])
                    for name in ('pio.engines[1].core.isr[3]', 'pio.engines[1].core.isr[6]',
                                 'pio.engines[1].core.isr[7]', 'pio.engines[0].core.fetch.words[20][11]',
                                 'pio.engines[0].core.fetch.words[20][12]'):
                        selected = [p for p in records if mapping.get(p['endpoint']) == name
                                    and p['endpoint'] + '/D (' in p['text'].split('data arrival time')[0]]
                        if selected:
                            row['local_endpoint_margins'].setdefault(name, {}).setdefault(corner, {})[analysis] = selected[0]['slack']
            if control and 'margins' in control:
                row['gain_vs_matched_control_ns'] = {corner: {analysis:
                    record['margins'][corner][analysis]['candidate_ns'] - control['margins'][corner][analysis]['candidate_ns']
                    for analysis in ('setup', 'hold')} for corner in REQUIRED_CORNERS}
        result['candidates'][case] = row
        print(case, record['status'], {c: {a: round(v['candidate_ns'], 9) for a, v in checks.items()}
                                      for c, checks in record.get('margins', {}).items()})
    write_json(campaign / 'comparison.json', result)
    print('matched_control_reproduces_parent=', control_exact)


def endpoints(run, out):
    state_path = find_state(run)
    state = json.loads(state_path.read_text())
    registers = register_map(Path(state['nl']).read_text())
    names = ('pio.engines[1].core.isr[3]', 'pio.engines[1].core.isr[6]',
             'pio.engines[1].core.isr[7]', 'pio.engines[0].core.fetch.words[20][11]',
             'pio.engines[0].core.fetch.words[20][12]')
    selected = {name: registers[name] for name in names}
    out.mkdir(parents=True, exist_ok=False)
    original = REPO / 'tools/timing/report_io_paths.tcl'
    script = out / 'local_endpoints.tcl'
    text = 'source {' + str(original) + '}\n'
    for index, (name, cell) in enumerate(selected.items()):
        text += 'set local_target [get_pins -quiet {' + cell + '/D}]\n'
        text += 'if {[llength $local_target] != 1} { error "Missing unique D endpoint" }\n'
        for delay in ('max', 'min'):
            text += ('report_checks -to $local_target -path_delay ' + delay +
                     ' -sort_by_slack -group_path_count 5 -endpoint_path_count 5 '
                     '-fields {slew cap input net fanout} -format full_clock_expanded '
                     '> [file join $out_dir local_' + str(index) + '_' + delay + '.rpt]\n')
    script.write_text(text)
    manifest = dict(status='running', state=str(state_path), state_sha256=sha(state_path),
                    original_script_sha256=sha(original), script_sha256=sha(script),
                    registers=selected, corners={})
    for corner in REQUIRED_CORNERS:
        folder = out / corner
        env = dict(os.environ, PIO_TIMING_RUN=str(run), PDK_ROOT='/home/shane/eda/pdk-2bbec755',
                   PIO_TIMING_CORNER=corner, PIO_TIMING_MODE='baseline',
                   PIO_TIMING_OUT=str(folder), PIO_TIMING_TARGET='none')
        with (out / (corner + '.log')).open('x') as log:
            subprocess.run(['sta', '-exit', str(script)], env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        log_text = (out / (corner + '.log')).read_text()
        if re.search(r'(?im)^\s*(?:error\b|\[ERROR\])', log_text) or (folder / 'coverage.rpt').read_text().strip():
            raise ValueError('Local endpoint STA execution or constraint coverage failed')
        rows = {}
        for index, name in enumerate(selected):
            rows[name] = {}
            for delay, analysis in (('max', 'setup'), ('min', 'hold')):
                report = folder / ('local_' + str(index) + '_' + delay + '.rpt')
                records = paths(report.read_text())
                if not records:
                    raise ValueError('No finite path to selected D boundary')
                rows[name][analysis] = min(row['slack'] for row in records)
        manifest['corners'][corner] = rows
        print(corner, rows, flush=True)
    manifest['status'] = 'complete'
    write_json(out / 'manifest.json', manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('inventory', 'prepare', 'screen', 'production', 'summarize', 'endpoints'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--case', choices=('control', 'hold_cluster', 'setup_local', 'combined'))
    parser.add_argument('--run', type=Path)
    args = parser.parse_args()
    if not args.out.resolve().is_relative_to((REPO / 'test/sim_build').resolve()):
        parser.error('Campaign artifacts must remain in test/sim_build')
    if args.action == 'inventory':
        inventory(args.out.resolve())
    elif args.action == 'prepare':
        prepare(args.out.resolve())
    elif args.action == 'screen':
        if not args.case:
            parser.error('--case is required for screen')
        screen(args.out.resolve(), args.case)
    elif args.action == 'production':
        if not args.case or args.case == 'control':
            parser.error('A screened candidate --case is required for production')
        production(args.out.resolve(), args.case)
    elif args.action == 'summarize':
        summarize(args.out.resolve())
    else:
        if not args.run:
            parser.error('--run is required for endpoints')
        endpoints(args.run.resolve(), args.out.resolve())


if __name__ == '__main__':
    main()
