"""One isolated data ECO per full-reroute screen on frozen post-antenna logic."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from closure_trial import sha, unique, validate_config
from physical_trial import final_gate, relocate


def recipes():
    result={'control': []}
    result['critical_size']=[dict(kind='size', instance='_23190_', old='sg13cmos5l_a21oi_1', new='sg13cmos5l_a21oi_2')]
    result['critical_buffer']=[dict(kind='buffer', target='_23190_/Y', old='sg13cmos5l_a21oi_1', max_loads=1000)]
    for name,target,master in (
        ('uio3','uio_in[3]',None),('uio2','uio_in[2]',None),
        ('17026','_17026_/Y','sg13cmos5l_inv_1'),('16949','_16949_/Y','sg13cmos5l_inv_1'),
        ('32068','_32068_/Q','sg13cmos5l_dfrbpq_1'),('32071','_32071_/Q','sg13cmos5l_dfrbpq_1')):
        result['fanout_'+name]=[dict(kind='buffer',target=target,old=master,max_loads=8)]
    for name,master,strong in (
        ('19177','nor3','nor3_2'),('24358','a221oi',None),('28038','nor4','nor4_2'),
        ('29030','a22oi',None),('18133','a221oi',None),('23931','nor3','nor3_2')):
        old='sg13cmos5l_'+master+'_1'
        result['slew_'+name]=[dict(kind='size',instance='_'+name+'_',old=old,new='sg13cmos5l_'+strong)
                              if strong else dict(kind='buffer',target='_'+name+'_/Y',old=old,max_loads=1000)]
    return result


def script(operations):
    text='''source $::env(SCRIPTS_DIR)/openroad/common/io.tcl
read_current_odb
set_propagated_clock [all_clocks]
'''
    for index,op in enumerate(operations):
        if op['old'] is not None:
            name=op.get('instance',op.get('target','').split('/')[0])
            text+=f'''set inst [$::block findInst {{{name}}}]
if {{$inst eq "NULL"}} {{ error "Measured driver missing" }}
if {{[[$inst getMaster] getName] ne "{op['old']}"}} {{ error "Unexpected driver master" }}
'''
        if op['kind']=='size':
            text+=f'''replace_cell {{{op['instance']}}} {op['new']}
if {{[[$inst getMaster] getName] ne "{op['new']}"}} {{ error "Replacement failed" }}
'''
        else:
            target=op['target']
            if '/' in target:
                text+=f'''set net [get_nets -of_objects [get_pins {{{target}}}]]
lassign [$inst getLocation] x y
'''
            else:
                text+=f'''set net [get_nets -of_objects [get_ports {{{target}}}]]
set term [$::block findBTerm {{{target}}}]
set box [lindex [[lindex [$term getBPins] 0] getBoxes] 0]
set x [expr {{([$box xMin]+[$box xMax])/2}}]
set y [expr {{([$box yMin]+[$box yMax])/2}}]
'''
            text+=f'''if {{[llength $net] != 1}} {{ error "Expected one target net" }}
set loads {{}}
foreach pin [get_pins -of_objects $net -filter {{direction == input}}] {{
    set name [get_property $pin full_name]
    if {{[string match */CLK $name]}} {{ error "Data ECO touches clock pin" }}
    lappend loads $name
}}
set loads [lsort $loads]
set count [llength $loads]
if {{$count < 1}} {{ error "No measured loads" }}
puts "ECO {target}: $count loads, group maximum {op['max_loads']}"
set location [list [ord::dbu_to_microns $x] [ord::dbu_to_microns $y]]
for {{set first 0}} {{$first < $count}} {{incr first {op['max_loads']}}} {{
    set chunk [lrange $loads $first [expr {{$first+{op['max_loads']}-1}}]]
    insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk -location $location \\
        -buffer_name eco_data_{index}_$first -net_name eco_net_{index}_$first
}}
'''
    return text+'source $::env(SCRIPTS_DIR)/openroad/common/dpl.tcl\nwrite_views\n'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('base','prepared','archive-root','pdk-root','out'):
        p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--trial',choices=tuple(recipes()),required=True)
    p.add_argument('--threads',type=int,default=8)
    a=p.parse_args()
    base,prepared,archive,pdk,out=(v.resolve() for v in (a.base,a.prepared,a.archive_root,a.pdk_root,a.out))
    if out.exists() or a.threads<1:
        p.error('Output must be new; threads positive')
    parent=json.loads((base/'experiment.json').read_text())
    if parent.get('clock_factors')!={'sink_clustering_size':None,'branch_split_max_loads':8}:
        raise ValueError('Require the committed splitting-only baseline')
    qualified=json.loads(unique(base/'run','*-openroad-stapostpnr/state_out.json').read_text())
    from check_signoff import REQUIRED_CORNERS
    if any(qualified['metrics'].get('timing__unannotated_net_filtered__count__corner:'+c)!=0 for c in REQUIRED_CORNERS):
        raise ValueError('Incomplete baseline annotation')
    prep=json.loads((prepared/'preparation.json').read_text())
    source=unique(base/'run','*-openroad-detailedrouting/state_out.json')
    if prep['source_state_sha256']!=sha(source) or prep['output_odb_sha256']!=sha(prepared/'unrouted.odb'):
        raise ValueError('Prepared input does not match frozen baseline')
    original=json.loads((archive/'runs/wokwi/resolved.json').read_text())
    raw=relocate(original,[(str(Path(original['DESIGN_DIR']).parent),str(archive)),(original['PDK_ROOT'],str(pdk))])
    raw.update(json.loads((base/'resolved_input.json').read_text()))
    validate_config(raw)
    if raw['GRT_ADJUSTMENT']!=0.25 or raw['CTS_SINK_CLUSTERING_SIZE'] is not None:
        raise ValueError('Baseline routing/clock settings changed')
    raw['OPENROAD_THREADS']=a.threads
    from librelane.config import Config
    from librelane.flows.classic import Classic
    from librelane.state import State
    from librelane.steps.openroad import DetailedPlacement

    class DataECO(DetailedPlacement):
        id='OpenROAD.DataECO'
        def get_script_path(self):
            return str(out/'eco.tcl')

    first=next(i for i,s in enumerate(Classic.Steps) if s.id=='OpenROAD.GlobalRouting')
    last=next(i for i,s in enumerate(Classic.Steps) if s.id=='OpenROAD.STAPostPNR')
    class Screen(Classic):
        Steps=[DataECO,*Classic.Steps[first:last+1]]
    variables=Screen.get_all_config_variables(Screen)
    keys={v.name for v in variables}
    config,_=Config.load({k:v for k,v in raw.items() if k in keys},flow_config_vars=variables,
                         design_dir=raw['DESIGN_DIR'],pdk_root=str(pdk),_load_pdk_configs=False)
    initial=State.loads((prepared/'state.json').read_text()); initial.validate()
    operations=recipes()[a.trial]
    out.mkdir(parents=True)
    (out/'runner.py').write_bytes(Path(__file__).read_bytes())
    (out/'eco.tcl').write_text(script(operations))
    (out/'recipe.json').write_text(json.dumps(operations,indent=2)+'\n')
    (out/'resolved_input.json').write_text(config.dumps())
    manifest=dict(trial=a.trial,status='running',scope='post_antenna_full_reroute_screen',
        base_trial=str(base),operations=operations,input_state_sha256=sha(prepared/'state.json'),
        input_views_sha256={k:sha(Path(initial[k])) for k in ('odb','def','nl','sdc')},
        runner_sha256=sha(Path(__file__)),eco_script_sha256=sha(out/'eco.tcl'),
        execution_overrides={'OPENROAD_THREADS':a.threads})
    (out/'experiment.json').write_text(json.dumps(manifest,indent=2)+'\n')
    try:
        Screen(config).start(with_initial_state=initial,_force_run_dir=str(out/'run'))
        manifest['status']='screen_complete'
        with (out/'eco_audit.log').open('w') as log:
            subprocess.run(['openroad','-no_init','-exit','-python',str(Path(__file__).with_name('audit_data_eco.py')),
                '--before',str(initial['odb']),'--odb',str(unique(out/'run','*-openroad-dataeco/*.odb')),
                '--recipe',str(out/'recipe.json'),'--pdk-model',str(pdk/'ihp-sg13cmos5l/libs.ref/sg13cmos5l_stdcell/verilog/sg13cmos5l_stdcell.v'),
                '--out',str(out/'eco_audit.json')],stdout=log,stderr=subprocess.STDOUT,check=True)
    except Exception as exc:
        manifest.update(status='failed',error=str(exc))
        raise
    finally:
        manifest['signoff_exit']=final_gate(out)
        if manifest['status']=='screen_complete' and manifest['signoff_exit']:
            manifest['status']='rejected_signoff'
        (out/'experiment.json').write_text(json.dumps(manifest,indent=2)+'\n')
    if manifest['signoff_exit']:
        p.exit(1,'Strict signoff rejected the screen\n')


if __name__=='__main__':
    main()
