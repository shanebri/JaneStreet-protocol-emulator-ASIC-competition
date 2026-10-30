"""Validate isolated data ECOs and compare them only with their matched reroute control."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from closure_trial import sha, unique
from check_signoff import REQUIRED_CORNERS, find_state
from collect_implementation import validate_replay
from data_eco_trial import recipes, script


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--evidence',type=Path,required=True)
    a=p.parse_args()
    common=None; config0=None; model0=None; rows=[]
    for name,operations in recipes().items():
        choices=[v for v in sorted(a.root.glob(name+'-[0-9][0-9]'))
                 if (v/'eco_audit.json').exists() and
                 json.loads((v/'experiment.json').read_text())['status'] in ('screen_complete','rejected_signoff')]
        if not choices:
            raise ValueError('No completed physical/audited result: '+name)
        trial=choices[-1]; out=a.evidence/trial.name
        manifest=json.loads((trial/'experiment.json').read_text())
        config=json.loads((trial/'resolved_input.json').read_text())
        if manifest['operations']!=operations or (trial/'eco.tcl').read_text()!=script(operations):
            raise ValueError('Applied ECO differs from the declared isolated recipe')
        if manifest['runner_sha256']!=sha(trial/'runner.py') or manifest['eco_script_sha256']!=sha(trial/'eco.tcl'):
            raise ValueError('Invocation runner/script checksum mismatch')
        inputs={k:manifest[k] for k in ('input_state_sha256','input_views_sha256','execution_overrides')}
        if common is None: common=inputs; config0=config
        if inputs!=common or config!=config0:
            raise ValueError('Unmatched input/configuration: '+name)
        audit=json.loads((trial/'eco_audit.json').read_text())
        if audit['status']!='pass' or not audit['clock_topology_unchanged']:
            raise ValueError('Invalid logical/clock audit')
        state_path=find_state(trial/'run'); state=json.loads(state_path.read_text())
        metrics=json.loads((out/'sta/metrics.json').read_text())
        replay=json.loads((out/'sta/replay_manifest.json').read_text())
        provenance=json.loads((out/'sta/provenance.json').read_text())
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
        rows.append(row)
    control=rows[0]
    for row in rows:
        if row['clock_sink_count']!=control['clock_sink_count']:
            raise ValueError('Native flow changed the clock sink count')
        row['annotation_complete']=all(v==0 for v in row['filtered_gaps'].values())
        row['strict_gate_pass']=not row['strict_gate_failures']
        row['delta_vs_matched_control']=dict(setup_ws_ns=row['setup_ws_ns']-control['setup_ws_ns'],
            setup_tns_ns=row['setup_tns_ns']-control['setup_tns_ns'],
            setup_endpoints=row['setup_endpoints']-control['setup_endpoints'],
            slow_slew=row['slow_slew']-control['slow_slew'],
            fanout=row['fanout'][REQUIRED_CORNERS[0]]-control['fanout'][REQUIRED_CORNERS[0]])
    result=dict(status='complete',rows=rows,matched_inputs=common,pdk_models_sha256=model0,
        setup_delta_sign='positive means improved slack',
        qualification='matched full reroute of post-antenna logic; compare with control, not the old routed reference; no accepted fabrication qualification')
    with (a.evidence/'comparison.json').open('x') as f:
        json.dump(result,f,indent=2); f.write('\n')
    print('PASS:',len(rows),'isolated audited screens;',sum(r['replay_sessions'] for r in rows),'STA replay sessions')


if __name__=='__main__':
    main()
