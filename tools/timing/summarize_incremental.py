"""Compare the exact native incremental control and four-net repair."""
import argparse
import json
from pathlib import Path
import shutil
from check_signoff import REQUIRED_CORNERS, check_metrics, find_state
from collect_implementation import selected_metrics, validate_replay
from incremental_trial import operations, incremental_script
from closure_trial import sha
from routing_delta import compare, read_def


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--candidate', choices=('fanout','last_fanout'), default='fanout')
    p.add_argument('--preserve-routes', action='store_true')
    a=p.parse_args()
    rows=[]; common=None; models=None; configuration=None
    for case in ('control',a.candidate):
        name='incremental_'+case+'-01'; trial=a.root/name; out=a.evidence/name
        manifest=json.loads((trial/'experiment.json').read_text())
        if manifest['status'] not in ('screen_complete','rejected_signoff'):
            raise ValueError('Incomplete physical screen')
        if bool(manifest.get('preserve_untouched_routes')) != a.preserve_routes:
            raise ValueError('Unexpected route preservation setting')
        if manifest['operations']!=operations(case) or (trial/'eco.tcl').read_text()!=incremental_script(operations(case)):
            raise ValueError('Unexpected repair recipe')
        if sha(trial/'runner.py') != manifest['runner_sha256'] or sha(trial/'eco.tcl') != manifest['eco_script_sha256']:
            raise ValueError('Frozen runner or script changed')
        source_path = Path(manifest['input_state'])
        if sha(source_path) != manifest['input_state_sha256']:
            raise ValueError('Source state changed')
        source = json.loads(source_path.read_text())
        if any(sha(Path(source[key])) != expected for key, expected in manifest['input_views_sha256'].items()):
            raise ValueError('Source physical view changed')
        inputs={k:manifest[k] for k in ('input_state_sha256','input_views_sha256','execution_overrides')}
        config=json.loads((trial/'resolved_input.json').read_text())
        if common is None: common=inputs; configuration=config
        elif inputs!=common or config!=configuration: raise ValueError('Unmatched input/configuration')
        audit=json.loads((trial/'eco_audit.json').read_text())
        if audit['status']!='pass': raise ValueError('Logical audit failed')
        state_path=find_state(trial/'run'); state=json.loads(state_path.read_text()); metrics=state['metrics']
        replay=json.loads((trial/'replay/manifest.json').read_text())
        validate_replay(replay,selected_metrics(metrics))
        for path,expected in replay['sha256'].items():
            if sha(Path(path))!=expected: raise ValueError('Replay input changed')
        libs={path:value for path,value in replay['sha256'].items() if path.endswith('.lib')}
        if models is None: models=libs
        elif models!=libs: raise ValueError('Library mismatch')
        for session in replay['sessions']:
            if (trial/f"replay/{session['corner']}-{session['mode']}/coverage.rpt").read_text().strip():
                raise ValueError('Incomplete constraint coverage')
        clock_audit=json.loads((out/'clock_audit.json').read_text())
        if clock_audit['input_sha256'] != {state['odb']: sha(Path(state['odb']))}:
            raise ValueError('Clock audit does not identify the final ODB')
        topology=clock_audit['topology']
        if topology['clock_sink_count']!=2421 or topology['clock_buffer_outputs_above8']:
            raise ValueError('Final routed clock audit failed')
        delta=compare(Path(source['def']),Path(state['def']))
        if a.preserve_routes:
            if sha(trial/'preserve_routes.py') != manifest['preserve_helper_sha256']:
                raise ValueError('Frozen preservation helper changed')
            preservation_path=next((trial/'run').glob('*-openroad-dataeco/preserved/audit.json'))
            preservation=json.loads(preservation_path.read_text())
            if preservation['status']!='pass' or preservation['fixed_net_count']==0:
                raise ValueError('No audited fixed wires')
            before_routes=read_def(Path(source['def']))[0]
            after_routes=read_def(Path(state['def']))[0]
            changed_fixed=[net for net in preservation['fixed_nets'] if before_routes[net]!=after_routes.get(net)]
            if changed_fixed: raise ValueError('Detailed routing changed fixed wires: '+str(changed_fixed[:10]))
            delta['fixed_routes_preserved']=preservation['fixed_net_count']
            shutil.copy2(preservation_path,out/'route_preservation.json')
            shutil.copy2(trial/'preserve_routes.py',out/'preserve_routes.py')
        (out/'routing_delta.json').write_text(json.dumps(delta,indent=2)+'\n')
        row=dict(case=case,metrics=selected_metrics(metrics),strict_failures=check_metrics(metrics),
                 state_sha256=sha(state_path),routing_delta=delta,clock_topology=topology)
        rows.append(row)
    result=dict(status='complete',scope='incremental route screen; not GDS qualification',
                common_inputs=common,configuration=configuration,models=models,rows=rows)
    (a.evidence/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
    lines=['# Native incremental-routing comparison','','| Case | Corner | Setup ns | Hold ns | Slew | Fanout | Gaps |',
           '| --- | --- | --- | --- | --- | --- | --- |']
    for row in rows:
        m=row['metrics']
        for c in REQUIRED_CORNERS:
            lines.append(f"| {row['case']} | {c} | {m['timing__setup__ws__corner:'+c]:.9f} | "
                         f"{m['timing__hold__ws__corner:'+c]:.9f} | {m['design__max_slew_violation__count__corner:'+c]} | "
                         f"{m['design__max_fanout_violation__count__corner:'+c]} | {m['timing__unannotated_net_filtered__count__corner:'+c]} |")
        d=row['routing_delta']
        lines+=['',f"{row['case']}: unchanged serialized routes {d['unchanged_signal_routes']}/{d['original_signal_nets']}; "
                f"changed clock routes {len(d['changed_clock_routes'])}; strict gate {'FAIL' if row['strict_failures'] else 'PASS'}.",'']
    lines+=['Complete metrics, setup/hold TNS and counts, coverage, model hashes and physical deltas are in comparison.json.',
            'Native DRC/antenna, GDS qualification and functional verification remain distinct gates.']
    (a.evidence/'comparison.md').write_text('\n'.join(lines)+'\n')
    print('PASS: matched incremental inputs, two logical/clock audits, 18 independent STA sessions')


if __name__=='__main__': main()
