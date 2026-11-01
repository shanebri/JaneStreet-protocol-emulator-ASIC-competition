"""Summarize immutable trial evidence without promoting experimental artifacts."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from check_signoff import check_metrics, find_state


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text()) if path.is_file() else None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    repo = a.repo.resolve()
    sys.path.insert(0, str(repo/'tools/packet_sram'))
    from compare_timing import compare
    parent = repo/'docs/timing/20261030-control-refactor/qualified-parent/69-openroad-stapostpnr/state_out.json'
    parent_metrics = read(parent)['metrics']
    if check_metrics(parent_metrics):
        raise ValueError('Qualified parent fails strict numeric gate')
    cases = {
        'matched_control': 'control_refactor_screen_control_20261030_02',
        'hold_screen': 'control_refactor_screen_hold_20261030_01',
        'replication_screen': 'control_refactor_screen_clone_20261030_01',
        'buffer_screen': 'control_refactor_screen_buffer_20261030_01',
        'combined_screen': 'control_refactor_screen_combined_20261030_01',
        'unavailable_drive_screen': 'control_refactor_screen_drive_20261030_01',
        'clean_control': 'control_refactor_control_20261030_02',
        'hold_production': 'control_refactor_hold_production_20261030_01',
        'hold_requalification': 'control_refactor_hold_requalification_20261031_01',
        'replication_production': 'control_refactor_clone_production_20261030_01',
        'combined_production': 'control_refactor_combined_production_20261031_01',
    }
    result = dict(updated_utc=datetime.now(timezone.utc).isoformat(),
                  scope='Evidence ledger; screens are never passing production parents',
                  qualified_parent='bb7c5ef3c54a7ae2733bbfae82aa940016375007',
                  parent_state_sha256=sha(parent), candidates_promoted=False, trials={})
    inventory = {}
    prefix_reference_state = repo/'test/sim_build/production_final_20261029_01/run/56-openroad-lastfanoutrepair/state_in.json'
    prefix_reference = Path(read(prefix_reference_state)['odb'])
    prefix_reference_sha = sha(prefix_reference)
    for name, relative in cases.items():
        root = repo/'test/sim_build'/relative
        row = dict(root=str(root), production_qualified=False)
        for filename in ('experiment.json', 'job.json', 'scope.json'):
            path = root/filename
            data = read(path)
            if data is not None:
                row[filename.removesuffix('.json')] = data
                inventory[str(path)] = dict(bytes=path.stat().st_size, sha256=sha(path))
        prefix_state = root/'run/55-openroad-detailedrouting-2/state_out.json'
        if prefix_state.is_file():
            prefix_odb = Path(read(prefix_state)['odb'])
            prefix_sha = sha(prefix_odb)
            row['clean_prefix_identity'] = dict(reference_odb_sha256=prefix_reference_sha,
                actual_odb_sha256=prefix_sha, identical=prefix_sha == prefix_reference_sha,
                scope='Fresh normal production output immediately before the candidate repair; not full qualification')
        try:
            state = find_state(root/'run')
        except ValueError:
            state = None
        if state:
            incremental_parent = root/'parent/69-openroad-stapostpnr/state_out.json'
            comparison_metrics = read(incremental_parent)['metrics'] if incremental_parent.is_file() else parent_metrics
            row['parent_comparison'] = compare(comparison_metrics, read(state)['metrics'])
            row['qualified_baseline_comparison'] = compare(parent_metrics, read(state)['metrics'])
            row['native_route_drc'] = read(state)['metrics'].get('route__drc_errors')
            row['native_antenna_nets'] = read(state)['metrics'].get('route__antenna_violation__count')
            inventory[str(state)] = dict(bytes=state.stat().st_size, sha256=sha(state))
        qualification = root/'qualification/manifest.json'
        resumed = read(root/'qualification_resume.json')
        if resumed:
            row['qualification_resume'] = resumed
            row['original_failed_qualification'] = read(qualification)
            qualification = Path(resumed['qualification_manifest'])
            inventory[str(root/'qualification_resume.json')] = dict(bytes=(root/'qualification_resume.json').stat().st_size,
                                                                    sha256=sha(root/'qualification_resume.json'))
        if qualification.is_file():
            row['gds_qualification'] = read(qualification)
            inventory[str(qualification)] = dict(bytes=qualification.stat().st_size, sha256=sha(qualification))
            row['production_qualified'] = ((row.get('job', {}).get('physical_signoff') is True
                                           or bool(resumed and resumed.get('physical_signoff') is True))
                                          and row['gds_qualification'].get('status') == 'complete'
                                          and row.get('parent_comparison', {}).get('status') == 'numeric_checks_pass')
            if row['production_qualified']:
                from refactor_trial import validated_parent
                try:
                    validated_parent(root)
                except (OSError,ValueError,KeyError) as exc:
                    row['production_qualified'] = False
                    row['parent_validation_error'] = str(exc)
        replay = root/'route_replay/manifest.json'
        if replay.is_file():
            row['diagnostic_route_qualification'] = read(replay)
            inventory[str(replay)] = dict(bytes=replay.stat().st_size, sha256=sha(replay))
        if name == 'clean_control':
            xml = root/'test/results.xml'
            if xml.is_file():
                tree = ET.parse(xml)
                row['rtl_tests'] = dict(tests=len(tree.findall('.//testcase')),
                    failures=len(tree.findall('.//failure')), errors=len(tree.findall('.//error')),
                    skipped=len(tree.findall('.//skipped')))
                inventory[str(xml)] = dict(bytes=xml.stat().st_size, sha256=sha(xml))
        for filename in ('production.log', 'qualification.log', 'functional.log'):
            path = root/filename
            if path.is_file():
                inventory[str(path)] = dict(bytes=path.stat().st_size, sha256=sha(path))
        result['trials'][name] = row
    activation = a.out/'activation.json'
    if activation.is_file():
        receipt = read(activation)
        errors = []
        try:
            from activate_refactor import input_comparison
            from refactor_trial import validated_parent
            active_candidate = Path(receipt['candidate'])
            state, qualification = validated_parent(active_candidate)
            input_comparison(active_candidate)
            active_scope = read(active_candidate/'scope.json')
            parent_state, parent_qualification = validated_parent(Path(active_scope['incremental_parent']))
            if any(sha(Path(name)) != expected for name, expected in receipt['timing_replay_input_sha256'].items()):
                raise ValueError('Activated timing inputs or pinned models changed')
            expected_recipe = repo/'tools/timing/production/last-fanout.json'
            if (receipt.get('status') != 'complete' or receipt.get('activated') is not True
                    or Path(receipt['active_recipe']) != expected_recipe
                    or sha(expected_recipe) != receipt['active_recipe_sha256']
                    or sha(expected_recipe) != sha(active_candidate/'tools/timing/production/last-fanout.json')
                    or sha(state) != receipt['run_state_sha256']
                    or sha(qualification) != receipt['qualification_manifest_sha256']
                    or sha(parent_state) != receipt['parent_state_sha256']
                    or sha(parent_qualification) != receipt['parent_qualification_manifest_sha256']
                    or sha(Path(receipt['previous_recipe_backup'])) != receipt['previous_recipe_sha256']
                    or sha(repo/'tools/timing/activate_refactor.py') != receipt['activation_runner_sha256']):
                raise ValueError('Activation receipt or current tested inputs do not match')
        except (OSError, ValueError, KeyError) as exc:
            errors.append(str(exc))
        result['activation'] = dict(receipt=receipt, current_validation_errors=errors)
        result['candidates_promoted'] = not errors
        inventory[str(activation)] = dict(bytes=activation.stat().st_size, sha256=sha(activation))
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out/'progress.json').write_text(json.dumps(result, indent=2)+'\n')
    (a.out/'source_inventory.json').write_text(json.dumps(inventory, indent=2)+'\n')
    for name, row in result['trials'].items():
        comparison = row.get('parent_comparison', {})
        print(name, row.get('job', row.get('experiment', {})).get('status', 'not_started'),
              comparison.get('status', 'no_extracted_result'), 'production_qualified='+str(row['production_qualified']))


if __name__ == '__main__':
    main()
