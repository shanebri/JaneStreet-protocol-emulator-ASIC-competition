"""Run an isolated RTL candidate using an archived resolved physical config.

Run in the pinned LibreLane 3.1.0.dev3 environment after functional verification.
The supplied DEF template must be checked against the archived boundary/pins.
This command does not edit production configuration or relax acceptance gates.
"""
import argparse
import hashlib
import json
from pathlib import Path

from physical_trial import final_gate, relocate


def main():
    from librelane.config import Config
    from librelane.flows.classic import Classic

    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-root',type=Path,required=True)
    parser.add_argument('--design-root',type=Path,required=True)
    parser.add_argument('--template',type=Path,required=True)
    parser.add_argument('--pdk-root',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--threads',type=int,default=8)
    args=parser.parse_args()
    if args.threads<1:
        parser.error('--threads must be positive')
    archive,design,pdk,out,template=(p.resolve() for p in
        (args.archive_root,args.design_root,args.pdk_root,args.out,args.template))
    original=json.loads((archive/'runs/wokwi/resolved.json').read_text())
    assert original['CLOCK_PERIOD']==20
    assert original['PDK']=='ihp-sg13cmos5l'
    assert set(original['STA_CORNERS'])=={'nom_slow_1p08V_125C','nom_typ_1p20V_25C','nom_fast_1p32V_m40C'}
    for key in ['SETUP_VIOLATION_CORNERS','HOLD_VIOLATION_CORNERS',
                'MAX_SLEW_VIOLATION_CORNERS','MAX_CAP_VIOLATION_CORNERS']:
        assert original[key]==['*'],(key,original[key])
    raw=relocate(original,[(str(Path(original['DESIGN_DIR']).parent),str(archive)),
                           (original['PDK_ROOT'],str(pdk))])
    source_names=[]
    for line in (design/'info.yaml').read_text().split('  source_files:\n',1)[1].splitlines():
        if not line.startswith('    - '): break
        source_names.append(line.split('"')[1])
    raw['DESIGN_DIR']=str(design/'src')
    raw['VERILOG_FILES']=[str(design/'src'/name) for name in source_names]
    raw['FP_DEF_TEMPLATE']=str(template)
    raw['OPENROAD_THREADS']=args.threads
    variables=Classic.get_all_config_variables(Classic)
    names={v.name for v in variables}
    config,_=Config.load({k:v for k,v in raw.items() if k in names},
                         flow_config_vars=variables,design_dir=str(design/'src'),
                         pdk_root=str(pdk),_load_pdk_configs=False)
    out.mkdir(parents=True,exist_ok=False)
    manifest={'trial':'parallel_instruction_read','status':'running',
              'archive_root':str(archive),'design_root':str(design),
              'template_sha256':hashlib.sha256(template.read_bytes()).hexdigest(),
              'source_sha256':{n:hashlib.sha256((design/'src'/n).read_bytes()).hexdigest() for n in source_names},
              'execution_overrides':{'OPENROAD_THREADS':args.threads}}
    (out/'experiment.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (out/'resolved_input.json').write_text(config.dumps())
    try:
        Classic(config).start(_force_run_dir=str(out/'run'))
    except Exception as exc:
        manifest.update(status='rejected_or_failed',error=str(exc))
        raise
    else:
        manifest['status']='flow_complete'
    finally:
        manifest['signoff_exit']=final_gate(out)
        if manifest['status']=='flow_complete' and manifest['signoff_exit']:
            manifest['status']='rejected_signoff'
        (out/'experiment.json').write_text(json.dumps(manifest,indent=2)+'\n')
    if manifest['signoff_exit']:
        parser.exit(1,'Strict post-route signoff rejected this trial; inspect post_route_signoff.log\n')


if __name__=='__main__':
    main()
