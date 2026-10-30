"""Extract an already routed rejected candidate without bypassing production.

Use only if the normal production flow has stopped after a completed detailed
route. This native extraction/STA diagnostic cannot approve the candidate or
replace any failed normal-production gate. No routing or constraints are changed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    from librelane.config import Config
    from librelane.flows.classic import Classic
    from librelane.state import State
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trial',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    a=parser.parse_args(); root=a.trial.resolve(); out=a.out.resolve()
    job=json.loads((root/'job.json').read_text())
    if job['status'] not in ('failed','rejected'): raise ValueError('Normal production must have stopped; no parallel route modification')
    candidates=sorted((root/'run').glob('*-openroad-detailedrouting*/state_out.json'))
    if not candidates: raise ValueError('No completed native detailed-route artifact to extract')
    source=candidates[-1]
    names=('OpenROAD.FillInsertion','OpenROAD.RCX','OpenROAD.STAPostPNR')
    selected=[s for s in Classic.Steps if s.id in names]
    assert {s.id for s in selected}==set(names)
    class Diagnostic(Classic): Steps=selected
    variables=Diagnostic.get_all_config_variables(Diagnostic); keys={v.name for v in variables}
    raw=json.loads((root/'run/resolved.json').read_text())
    config,_=Config.load({k:v for k,v in raw.items() if k in keys},flow_config_vars=variables,
        design_dir=raw['DESIGN_DIR'],pdk_root=raw['PDK_ROOT'],_load_pdk_configs=False)
    out.mkdir(parents=True,exist_ok=False)
    manifest=dict(status='running',scope='native extraction/STA diagnostic of rejected routed artifact; not production signoff',
        source_state=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        missing_exact_fast_macro_corner=True,production_failure=job)
    try:
        Diagnostic(config).start(with_initial_state=State.loads(source.read_text()),_force_run_dir=str(out/'run'))
        manifest['status']='extracted_diagnostic_complete'
        checker=Path(__file__).resolve().parents[1]/'timing/check_signoff.py'
        with (out/'strict_signoff.log').open('w') as f:
            result=subprocess.run([sys.executable,str(checker),str(out/'run')],stdout=f,stderr=subprocess.STDOUT)
        manifest['strict_numeric_gate_exit']=result.returncode
    except Exception as exc:
        manifest.update(status='failed',error=str(exc)); raise
    finally:
        (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


if __name__=='__main__': main()
