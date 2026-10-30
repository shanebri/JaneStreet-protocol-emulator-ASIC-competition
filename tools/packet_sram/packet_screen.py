"""Matched audited data-repair screen on a frozen routed SRAM candidate.

Uses normal native routing/extraction/STA steps and the audited candidate data
repair. This screen cannot replace a clean production run or full GDS signoff.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from install_candidate_tools import install


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trial',type=Path,required=True)
    p.add_argument('--recipe-dir',type=Path,required=True)
    p.add_argument('--case',choices=('control','repair'),required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--source-state',type=Path)
    a=p.parse_args(); root=a.trial.resolve(); out=a.out.resolve(); recipe=a.recipe_dir.resolve()
    out.mkdir(exist_ok=False)
    shutil.copytree(root/'tools/timing',out/'tools/timing',ignore=shutil.ignore_patterns('__pycache__'))
    install(out)
    sys.path.insert(0,str(out/'tools/timing'))
    from production_flow import DataRepair
    from librelane.flows.classic import Classic
    from librelane.config import Config
    from librelane.state import State
    from closure_trial import validate_config
    contract=recipe/('contract.json' if a.case=='repair' else 'empty_postroute_contract.json')
    first=next(i for i,s in enumerate(Classic.Steps) if s.id=='OpenROAD.GlobalRouting')
    last=next(i for i,s in enumerate(Classic.Steps) if s.id=='OpenROAD.STAPostPNR')
    class Screen(Classic): Steps=[DataRepair,*Classic.Steps[first:last+1]]
    variables=Screen.get_all_config_variables(Screen); keys={v.name for v in variables}
    raw=json.loads((root/'run/resolved.json').read_text())
    raw['PIO_ECO_CONTRACT']=str(contract)
    validate_config(raw)
    config,_=Config.load({k:v for k,v in raw.items() if k in keys},flow_config_vars=variables,
        design_dir=raw['DESIGN_DIR'],pdk_root=raw['PDK_ROOT'],_load_pdk_configs=False)
    source=a.source_state.resolve() if a.source_state else next((root/'run').glob('*-pio-preparesignalroutes/state_out.json'))
    state=State.loads(source.read_text())
    manifest=dict(status='running',case=a.case,scope='matched physical screen only; clean production and full GDS qualification remain required',
        source=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        input_odb_sha256=hashlib.sha256(Path(state['odb']).read_bytes()).hexdigest(),
        contract_sha256=hashlib.sha256(contract.read_bytes()).hexdigest(),execution_threads=8)
    (out/'resolved_input.json').write_text(config.dumps())
    try:
        Screen(config).start(with_initial_state=state,_force_run_dir=str(out/'run'))
        checker=Path(__file__).resolve().parents[1]/'timing/check_signoff.py'
        with (out/'strict_signoff.log').open('w') as log:
            result=subprocess.run([sys.executable,str(checker),str(out/'run')],stdout=log,stderr=subprocess.STDOUT)
        manifest.update(status='screen_complete' if result.returncode==0 else 'rejected_metrics',strict_gate_exit=result.returncode)
    except Exception as exc:
        manifest.update(status='failed',error=str(exc)); raise
    finally:
        (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


if __name__=='__main__': main()
