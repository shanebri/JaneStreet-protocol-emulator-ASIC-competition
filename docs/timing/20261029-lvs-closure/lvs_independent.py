"""Independent exact-GDS LVS while full-layout DRC continues in its original job."""
import json,os,subprocess,sys
from pathlib import Path
repo=Path(__file__).resolve().parents[3]
root=repo/'test/sim_build/lvs_independent_20261029_01'
base=repo/'test/sim_build/lvs_repair_tail_20261029_01/run'
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
    class LVS(Classic):
        Steps=[s for s in Classic.Steps if s.id in ('Magic.SpiceExtraction','Checker.IllegalOverlap','Netgen.LVS','Checker.LVS')]
    variables=LVS.get_all_config_variables(LVS);names={v.name for v in variables}
    raw=json.loads((base/'resolved.json').read_text())
    config,_=Config.load({k:v for k,v in raw.items() if k in names},flow_config_vars=variables,design_dir=raw['DESIGN_DIR'],pdk_root=raw['PDK_ROOT'],_load_pdk_configs=False)
    source=base/'08-odb-checkdesignantennaproperties/state_out.json'
    status=dict(status='running',source=str(source))
    def save(): (root/'job.json').write_text(json.dumps(status,indent=2))
    save()
    try:
        LVS(config).start(with_initial_state=State.loads(source.read_text()),_force_run_dir=str(root/'run'))
        status['status']='complete'
    except Exception as e:
        status.update(status='failed',error=str(e));raise
    finally:save()
