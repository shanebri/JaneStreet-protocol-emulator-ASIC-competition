"""Matched native incremental-routing screen on the slew-clean routed design."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from closure_trial import sha, unique, validate_config
from data_eco_trial import script
from physical_trial import final_gate, relocate
from collect_implementation import selected_metrics, validate_replay
from check_signoff import check_metrics


def operations(case):
    if case == 'control':
        return []
    if case == 'last_fanout':
        return [dict(kind='buffer', target='place6629/X', old='sg13cmos5l_buf_1', max_loads=4)]
    if case != 'fanout':
        raise ValueError('Unknown incremental recipe: '+case)
    return [dict(kind='buffer', target=target, old=master, max_loads=4) for target,master in (
        ('_17916_/Y','sg13cmos5l_nor2b_1'),('_19177_/Y','sg13cmos5l_nor3_2'),
        ('place7144/X','sg13cmos5l_buf_1'),('place5579/X','sg13cmos5l_buf_1'))]


def incremental_script(ops):
    text = script(ops)
    header = 'set_propagated_clock [all_clocks]\n'
    text = text.replace(header, header+'''source $::env(SCRIPTS_DIR)/openroad/common/set_routing_layers.tcl
source $::env(SCRIPTS_DIR)/openroad/common/set_layer_adjustments.tcl
set_macro_extension $::env(GRT_MACRO_EXTENSION)
global_route -start_incremental -allow_congestion
''', 1)
    return text.replace('write_views\n', '''global_route -end_incremental -allow_congestion -congestion_iterations $::env(GRT_OVERFLOW_ITERS) -verbose
write_views
''')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('base','pdk-root','archive-root','out'):
        p.add_argument('--'+key, type=Path, required=True)
    p.add_argument('--case', choices=('control','fanout','last_fanout'), required=True)
    a = p.parse_args()
    base,pdk,out = (v.resolve() for v in (a.base,a.pdk_root,a.out))
    if out.exists():
        p.error('Output must be fresh')
    final_state = json.loads(unique(base/'run','*-openroad-stapostpnr/state_out.json').read_text())
    if any('max_fanout_violation' not in failure for failure in check_metrics(final_state['metrics'])):
        raise ValueError('Incremental base must pass every strict metric except fanout')
    replay = json.loads((base/'replay/manifest.json').read_text())
    validate_replay(replay, selected_metrics(final_state['metrics']))
    for path, expected in replay['sha256'].items():
        if sha(Path(path)) != expected:
            raise ValueError('Base replay inputs changed')
    archive = a.archive_root.resolve()
    original = json.loads((archive/'runs/wokwi/resolved.json').read_text())
    raw = relocate(original, [(str(Path(original['DESIGN_DIR']).parent),str(archive)),
                              (original['PDK_ROOT'],str(pdk))])
    raw.update(json.loads((base/'resolved_input.json').read_text()))
    validate_config(raw)
    if raw['OPENROAD_THREADS'] != 8 or raw['GRT_ADJUSTMENT'] != .25 or not raw['GRT_ALLOW_CONGESTION']:
        raise ValueError('Execution/routing settings differ')
    source = unique(base/'run','*-openroad-detailedrouting/state_out.json')
    from librelane.config import Config
    from librelane.flows.classic import Classic
    from librelane.state import State
    from librelane.steps.openroad import DetailedPlacement, GlobalRouting

    class IncrementalECO(DetailedPlacement):
        id = 'OpenROAD.DataECO'
        config_vars = GlobalRouting.config_vars
        def get_script_path(self):
            return str(out/'eco.tcl')

    first = next(i for i,s in enumerate(Classic.Steps) if s.id=='OpenROAD.DetailedRouting')
    last = next(i for i,s in enumerate(Classic.Steps) if s.id=='OpenROAD.STAPostPNR')
    class Screen(Classic):
        Steps = [IncrementalECO,*Classic.Steps[first:last+1]]
    variables = Screen.get_all_config_variables(Screen)
    names = {v.name for v in variables}
    config,_ = Config.load({k:v for k,v in raw.items() if k in names},flow_config_vars=variables,
                           design_dir=raw['DESIGN_DIR'],pdk_root=str(pdk),_load_pdk_configs=False)
    initial = State.loads(source.read_text()); initial.validate()
    out.mkdir(parents=True)
    ops = operations(a.case)
    (out/'recipe.json').write_text(json.dumps(ops,indent=2)+'\n')
    (out/'eco.tcl').write_text(incremental_script(ops))
    (out/'runner.py').write_bytes(Path(__file__).read_bytes())
    (out/'resolved_input.json').write_text(config.dumps())
    manifest = dict(trial='incremental_'+a.case, status='running',
        scope='native incremental routing from completed slew-clean route', base_trial=str(base),
        input_state=str(source), input_state_sha256=sha(source),
        input_views_sha256={k:sha(Path(initial[k])) for k in ('odb','def','nl','sdc')},
        runner_sha256=sha(Path(__file__)), eco_script_sha256=sha(out/'eco.tcl'), operations=ops,
        execution_overrides={'OPENROAD_THREADS':8})
    (out/'experiment.json').write_text(json.dumps(manifest,indent=2)+'\n')
    try:
        Screen(config).start(with_initial_state=initial,_force_run_dir=str(out/'run'))
        with (out/'eco_audit.log').open('w') as log:
            subprocess.run(['openroad','-no_init','-exit','-python',str(Path(__file__).with_name('audit_data_eco.py')),
                '--before',str(initial['odb']),'--odb',str(unique(out/'run','*-openroad-dataeco/*.odb')),
                '--recipe',str(out/'recipe.json'),'--pdk-model',
                str(pdk/'ihp-sg13cmos5l/libs.ref/sg13cmos5l_stdcell/verilog/sg13cmos5l_stdcell.v'),
                '--out',str(out/'eco_audit.json')],stdout=log,stderr=subprocess.STDOUT,check=True)
        manifest['status'] = 'screen_complete'
    except Exception as exc:
        manifest.update(status='failed',error=str(exc))
        raise
    finally:
        manifest['signoff_exit'] = final_gate(out)
        if manifest['status']=='screen_complete' and manifest['signoff_exit']:
            manifest['status']='rejected_signoff'
        (out/'experiment.json').write_text(json.dumps(manifest,indent=2)+'\n')
    if manifest['signoff_exit']:
        p.exit(1,'Strict signoff rejected the screen\n')


if __name__ == '__main__':
    main()
