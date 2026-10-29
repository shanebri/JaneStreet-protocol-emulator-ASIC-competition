"""Bounded reroute of an already routed, LVS-failing artifact; fresh outputs."""
import json, os, re, subprocess, sys
from pathlib import Path
repo=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo/'tools/timing'))
root=repo/'test/sim_build/lvs_repair_20261029_01'
base=repo/'test/sim_build/production_final_20261028_01/run'
if '--worker' not in sys.argv:
    root.mkdir(exist_ok=False)
    cmd=['/nix/var/nix/profiles/default/bin/nix','develop','--offline','--command','python3',str(Path(__file__).resolve()),'--worker']
    with (root/'launcher.log').open('w') as log:
        p=subprocess.Popen(cmd,cwd='/home/shane/eda/librelane-3.1.0.dev3',stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    (root/'process.json').write_text(json.dumps(dict(pid=p.pid,command=cmd),indent=2))
    print('Detached',p.pid)
else:
    from librelane.flows.classic import Classic
    from librelane.config import Config
    from librelane.state import State,DesignFormat
    from librelane.steps.openroad import DetailedRouting
    from production_flow import RouteAcceptance
    source=base/'57-openroad-detailedrouting-3/state_out.json'
    state=State.loads(source.read_text())
    text=Path(state['def']).read_text()
    section=re.search(r'\bNETS\s+\d+\s*;.*?END NETS',text,re.S)[0]
    section=re.sub(r'\+\s+FIXED\b','+ ROUTED',section)
    thaw=root/'unfixed.def'
    thaw.write_text('VERSION 5.8 ;\nDIVIDERCHAR "/" ;\nBUSBITCHARS "[]" ;\nDESIGN tt_um_shanebri_top ;\nUNITS DISTANCE MICRONS 1000 ;\n'+section+'\nEND DESIGN\n')
    class Repair(DetailedRouting):
        def get_script_path(self):
            return str(root/'reroute.tcl')
    native=Path(DetailedRouting.get_script_path(Repair.__new__(Repair)))
    script=native.read_text().replace('read_current_odb','read_current_odb\nread_def -floorplan_initialize {'+str(thaw)+'}',1)
    (root/'reroute.tcl').write_text(script)
    first=next(i for i,s in enumerate(Classic.Steps) if s.id=='OpenROAD.DetailedRouting')
    steps=[Repair]
    for s in Classic.Steps[first+1:]:
        steps.append(s)
        if s.id=='OpenROAD.STAPostPNR': steps.append(RouteAcceptance)
    class Trial(Classic): Steps=steps
    variables=Trial.get_all_config_variables(Trial); names={v.name for v in variables}
    raw=json.loads((base/'resolved.json').read_text())
    config,_=Config.load({k:v for k,v in raw.items() if k in names},flow_config_vars=variables,design_dir=raw['DESIGN_DIR'],pdk_root=raw['PDK_ROOT'],_load_pdk_configs=False)
    job=dict(status='running',source=str(source),hypothesis='Retain existing detailed routes as initial routes, allow native DRT to repair actual inter-net shorts, and serialize every resulting route consistently')
    (root/'job.json').write_text(json.dumps(job,indent=2))
    try:
        Trial(config).start(with_initial_state=state,_force_run_dir=str(root/'run'))
        job['status']='complete'
    except Exception as e:
        job.update(status='failed',error=str(e)); raise
    finally: (root/'job.json').write_text(json.dumps(job,indent=2))
