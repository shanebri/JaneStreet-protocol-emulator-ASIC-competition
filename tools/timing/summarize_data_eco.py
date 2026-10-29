"""Validate data ECO suites against their matched reroute control."""
import argparse
import json
from pathlib import Path
import subprocess
from closure_trial import sha
from check_signoff import REQUIRED_CORNERS, check_metrics, find_state
from collect_implementation import selected_metrics, validate_replay, path_summary
from data_eco_trial import SUITES, suite_recipes, script


def audit_match(common, config0, manifest, config):
    inputs={k:manifest[k] for k in ('input_state_sha256','input_views_sha256','execution_overrides')}
    if inputs!=common or config!=config0:
        raise ValueError('Unmatched input/configuration: '+manifest['trial'])


def delta(row, reference):
    return {key: row[key]-reference[key] for key in
            ('setup_ws_ns','setup_tns_ns','setup_endpoints','slow_slew')} | {
        'fanout': row['fanout'][REQUIRED_CORNERS[0]]-reference['fanout'][REQUIRED_CORNERS[0]]}


def add_comparisons(rows, reference=None, *, control_name='control', control_operations=None, cumulative=True):
    control=rows[0]
    expected_operations=[] if control_operations is None else control_operations
    if control['trial']!=control_name or control['operations']!=expected_operations:
        raise ValueError('First row must be the exact declared matched control')
    for index,row in enumerate(rows):
        if row['clock_sink_count']!=control['clock_sink_count']:
            raise ValueError('Native flow changed the clock sink count')
        row['annotation_complete']=all(v==0 for v in row['filtered_gaps'].values())
        row['strict_gate_pass']=not row['strict_gate_failures']
        row['screen_valid']=(row['annotation_complete'] and row['positive_hold_all_sessions'] and
            all(v==0 for v in row['cap'].values()) and row['clock_buffer_outputs_above8']==0 and
            row['route_drc']==0 and row['antenna_violations']==0)
        row['delta_vs_matched_control']=delta(row,control)
        if cumulative:
            row['delta_vs_previous_case']=delta(row,rows[max(0,index-1)])
        if 'fast_hold_ws_ns' in row:
            row['delta_fast_hold_ns']=row['fast_hold_ws_ns']-control['fast_hold_ws_ns']
        if reference is not None:
            row['delta_vs_old_routed_reference']=delta(row,reference)


def reference_row(metrics):
    selected_metrics(metrics)
    slow=REQUIRED_CORNERS[0]
    return dict(setup_ws_ns=metrics['timing__setup__ws__corner:'+slow],
        setup_tns_ns=metrics['timing__setup__tns__corner:'+slow],
        setup_endpoints=metrics['timing__setup_vio__count__corner:'+slow],
        slow_slew=metrics['design__max_slew_violation__count__corner:'+slow],
        fanout={c:metrics['design__max_fanout_violation__count__corner:'+c] for c in REQUIRED_CORNERS})


def best_combination(rows, start_index=2):
    return max((r for r in rows[start_index:] if r['screen_valid']),
               key=lambda r:(r['setup_ws_ns'],r['setup_tns_ns'],-r['setup_endpoints']),default=None)


def comparison_markdown(result):
    previous='delta_vs_previous_case' in result['rows'][0]
    headers=['Case','WS ns','Delta control']+(['Delta previous'] if previous else [])+[
        'TNS ns','Endpoints','Slew','Fanout','Fast hold ns','Delta fast hold ns','Annotation','Valid screen']
    lines=['# '+result['suite'].capitalize()+' data ECO comparison', '',
        'All cases start from the same prepared input and use a matched full reroute. '
        'Positive slack deltas mean improvement. Screen validity does not imply strict signoff.', '',
        '| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']
    for index,row in enumerate(result['rows'],1):
        cells=[f"[{index}]({row['attempt']}/sta/metrics.json)",f"{row['setup_ws_ns']:.6f}",
            f"{row['delta_vs_matched_control']['setup_ws_ns']:+.6f}"]
        if previous: cells.append(f"{row['delta_vs_previous_case']['setup_ws_ns']:+.6f}")
        cells += [f"{row['setup_tns_ns']:.6f}",str(row['setup_endpoints']),str(row['slow_slew']),
            str(row['fanout'][REQUIRED_CORNERS[0]]),f"{row['fast_hold_ws_ns']:+.9f}",
            f"{row['delta_fast_hold_ns']:+.9f}",
            'complete' if row['annotation_complete'] else 'REJECT','yes' if row['screen_valid'] else 'NO']
        lines.append('| '+' | '.join(cells)+' |')
    lines.append('')
    for index,row in enumerate(result['rows'],1):
        path=row['critical_path']
        lines.append(f"{index}. `{row['trial']}`: `{path['startpoint']}` to `{path['endpoint']}`. "
                     f"Strict signoff: {'PASS' if row['strict_gate_pass'] else 'FAIL'}.")
    selected=result['best_valid_candidate'] if result['suite'] in ('critical_path','upstream','balanced','electrical','sink_local','fanout_tail','read_acceptance') else result['best_valid_combination']
    lines+=['', 'Best valid '+('candidate' if result['suite'] in ('critical_path','upstream','balanced','electrical','sink_local','fanout_tail','read_acceptance') else 'combination')+
            ' by global setup WS: `'+str(selected)+'`.']
    if result['suite'] in ('critical_path','upstream','balanced','electrical','sink_local','fanout_tail','read_acceptance'):
        lines+=['', 'Each candidate applies its declared independent repair to the control; candidates are not cumulative.',
                'Best valid candidate improves control setup WS: '+str(result['candidate_setup_improves_control'])+'.']
    if result['old_routed_reference']:
        reference=result['old_routed_reference']['metrics']
        lines+=['',f"Old routed reference: WS {reference['setup_ws_ns']:.6f} ns, "
            f"TNS {reference['setup_tns_ns']:.6f} ns, {reference['setup_endpoints']} endpoints, "
            f"{reference['slow_slew']} slew and {reference['fanout'][REQUIRED_CORNERS[0]]} fanout violations. "
            'Per-case deltas against this different routing history are retained in comparison.json.']
    return '\n'.join(lines)+'\n'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--suite',choices=SUITES,default='isolated')
    p.add_argument('--reference-metrics',type=Path,
                   help='Old splitting-only routed metrics (required for integration comparison)')
    a=p.parse_args()
    if a.suite=='integration' and a.reference_metrics is None:
        p.error('Integration comparison requires --reference-metrics for the old routed reference')
    reference=reference_row(json.loads(a.reference_metrics.read_text())) if a.reference_metrics else None
    common=None; config0=None; model0=None; rows=[]
    selected=suite_recipes(a.suite)
    control_name=next(iter(selected))
    for name,operations in selected.items():
        choices=[v for v in sorted(a.root.glob(name+'-[0-9][0-9]'))
                 if (v/'eco_audit.json').exists() and
                 json.loads((v/'experiment.json').read_text())['status'] in ('screen_complete','rejected_signoff')]
        if not choices:
            raise ValueError('No completed physical/audited result: '+name)
        trial=choices[-1]; out=a.evidence/trial.name
        manifest=json.loads((trial/'experiment.json').read_text())
        config=json.loads((trial/'resolved_input.json').read_text())
        if manifest['operations']!=operations or (trial/'eco.tcl').read_text()!=script(operations):
            raise ValueError('Applied ECO differs from the declared recipe')
        if manifest['runner_sha256']!=sha(trial/'runner.py') or manifest['eco_script_sha256']!=sha(trial/'eco.tcl'):
            raise ValueError('Invocation runner/script checksum mismatch')
        inputs={k:manifest[k] for k in ('input_state_sha256','input_views_sha256','execution_overrides')}
        if common is None: common=inputs; config0=config
        audit_match(common,config0,manifest,config)
        if a.suite in ('integration','critical_path','upstream','balanced','electrical','sink_local','fanout_tail','read_acceptance') and inputs['execution_overrides']!={'OPENROAD_THREADS':8}:
            raise ValueError('Matched suites require eight OpenROAD threads')
        audit=json.loads((trial/'eco_audit.json').read_text())
        if audit['status']!='pass' or not audit['clock_topology_unchanged']:
            raise ValueError('Invalid logical/clock audit')
        state_path=find_state(trial/'run'); state=json.loads(state_path.read_text())
        metrics=json.loads((out/'sta/metrics.json').read_text())
        replay=json.loads((out/'sta/replay_manifest.json').read_text())
        provenance=json.loads((out/'sta/provenance.json').read_text())
        if metrics!=selected_metrics(state['metrics']) or provenance['gate_failures']!=check_metrics(state['metrics']):
            raise ValueError('Collected metrics/gate results differ from actual post-route state')
        validate_replay(replay,metrics)
        if provenance['coverage_issues'] or provenance['state_sha256']!=sha(state_path):
            raise ValueError('STA coverage or state provenance mismatch')
        models={k:v for k,v in replay['sha256'].items() if '/libs.ref/' in k}
        if model0 is None: model0=models
        if models!=model0: raise ValueError('PDK model mismatch')
        final_audit=out/'routed_clock_audit.json'
        if not final_audit.exists():
            with (out/'routed_clock_audit.log').open('w') as log:
                subprocess.run(['openroad','-no_init','-exit','-python',
                    str(Path(__file__).with_name('audit_clock_tree.py')),'--odb',state['odb'],
                    '--out',str(final_audit)],stdout=log,stderr=subprocess.STDOUT,check=True)
        clock=json.loads(final_audit.read_text())
        if clock['input_sha256']!={state['odb']:sha(Path(state['odb']))}:
            raise ValueError('Final clock audit state mismatch')
        slow=REQUIRED_CORNERS[0]
        def m(key,corner=slow): return metrics[key+'__corner:'+corner]
        row=dict(trial=name,attempt=trial.name,operations=operations,
            setup_ws_ns=m('timing__setup__ws'),setup_tns_ns=m('timing__setup__tns'),
            setup_endpoints=m('timing__setup_vio__count'),slow_slew=m('design__max_slew_violation__count'),
            fanout={c:m('design__max_fanout_violation__count',c) for c in REQUIRED_CORNERS},
            cap={c:m('design__max_cap_violation__count',c) for c in REQUIRED_CORNERS},
            hold_ws_ns={c:m('timing__hold__ws',c) for c in REQUIRED_CORNERS},
            filtered_gaps={c:m('timing__unannotated_net_filtered__count',c) for c in REQUIRED_CORNERS},
            clock_sink_count=clock['topology']['clock_sink_count'],
            clock_buffer_outputs_above8=clock['topology']['clock_buffer_outputs_above8'],
            added_buffers=audit['added_buffers'],replacements=audit['replacements'],
            route_drc=state['metrics'].get('route__drc_errors'),
            antenna_violations=state['metrics'].get('route__antenna_violation__count'),
            strict_gate_failures=provenance['gate_failures'],replay_sessions=len(replay['sessions']))
        row['positive_hold_all_sessions']=all(s['hold']>0 for s in replay['sessions'])
        row['min_hold_all_sessions_ns']=min(s['hold'] for s in replay['sessions'])
        row['fast_hold_ws_ns']=m('timing__hold__ws',REQUIRED_CORNERS[-1])
        row['critical_path']=path_summary((out/'sta/global_setup.rpt').read_text())
        rows.append(row)
    add_comparisons(rows,reference,control_name=control_name,control_operations=selected[control_name],
                    cumulative=a.suite not in ('critical_path','upstream','balanced','electrical','sink_local','fanout_tail','read_acceptance'))
    best=best_combination(rows,1 if a.suite in ('critical_path','upstream','balanced','electrical','sink_local','fanout_tail','read_acceptance') else 2) if a.suite!='isolated' else None
    result=dict(status='complete',suite=a.suite,rows=rows,matched_inputs=common,pdk_models_sha256=model0,
        control_trial=control_name,
        best_valid_combination=best['trial'] if best and a.suite=='integration' else None,
        best_valid_candidate=best['trial'] if best and a.suite in ('critical_path','upstream','balanced','electrical','sink_local','fanout_tail','read_acceptance') else None,
        candidate_setup_improves_control=bool(best and best['setup_ws_ns']>rows[0]['setup_ws_ns']),
        best_selection='Highest global slow setup WS, then TNS, then fewer endpoints; valid screen is not strict signoff',
        old_routed_reference=dict(metrics=reference,sha256=sha(a.reference_metrics)) if reference else None,
        setup_delta_sign='positive means improved slack',
        qualification='matched full reroute of post-antenna logic; compare with control, not the old routed reference; no accepted fabrication qualification')
    with (a.evidence/'comparison.json').open('x') as f:
        json.dump(result,f,indent=2); f.write('\n')
    with (a.evidence/'comparison.md').open('x') as f:
        f.write(comparison_markdown(result))
    print('PASS:',len(rows),a.suite,'audited screens;',sum(r['replay_sessions'] for r in rows),'STA replay sessions')


if __name__=='__main__':
    main()
