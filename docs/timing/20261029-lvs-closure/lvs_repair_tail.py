"""Finish signoff on the completed repair without repeating physical routing."""
import json,os,subprocess,sys
from pathlib import Path
repo=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo/'tools/timing'))
root=repo/'test/sim_build/lvs_repair_tail_20261029_01'
base=repo/'test/sim_build/production_final_20261028_01/run'
if '--worker' not in sys.argv:
    root.mkdir(exist_ok=False)
    cmd=['/nix/var/nix/profiles/default/bin/nix','develop','--offline','--command','python3',str(Path(__file__).resolve()),'--worker']
    with (root/'launcher.log').open('w') as log:
        proc=subprocess.Popen(cmd,cwd='/home/shane/eda/librelane-3.1.0.dev3',stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    (root/'process.json').write_text(json.dumps(dict(pid=proc.pid,command=cmd),indent=2))
    print('Detached',proc.pid)
else:
    from librelane.flows.classic import Classic
    from librelane.config import Config
    from librelane.state import State
    from production_flow import RouteAcceptance,PIOClosure
    source=repo/'test/sim_build/lvs_repair_20261029_01/run/12-openroad-stapostpnr/state_out.json'
    first=next(i for i,s in enumerate(Classic.Steps) if s.id=='OpenROAD.STAPostPNR')
    class Tail(Classic): Steps=[Classic.Steps[first],RouteAcceptance,*Classic.Steps[first+1:]]
    variables=PIOClosure.get_all_config_variables(PIOClosure); names={v.name for v in variables}
    raw=json.loads((base/'resolved.json').read_text())
    config,_=Config.load({k:v for k,v in raw.items() if k in names},flow_config_vars=variables,design_dir=raw['DESIGN_DIR'],pdk_root=raw['PDK_ROOT'],_load_pdk_configs=False)
    state=dict(status='running',source=str(source))
    def save(): (root/'job.json').write_text(json.dumps(state,indent=2))
    save()
    try:
        Tail(config).start(with_initial_state=State.loads(source.read_text()),_force_run_dir=str(root/'run'))
        state['status']='qualifying';save()
        tooling=repo/'test/sim_build/production_tooling'
        subprocess.run([sys.executable,str(repo/'tools/timing/qualify_gds_artifact.py'),'--run',str(root/'run'),'--out',str(root/'qualification'),'--pdk-root',raw['PDK_ROOT'],'--support-tools',str(tooling/'tt'),'--precheck-python',str(tooling/'precheck-venv/bin/python'),'--test-python','/home/shane/eda/pio-test-venv/bin/python','--test-source',str(repo/'test')],check=True)
        state['status']='complete'
    except Exception as e:
        state.update(status='failed',error=str(e));raise
    finally: save()
