"""Archive compact, hashed evidence without changing any implementation input."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from xml.etree import ElementTree

REPO=Path(__file__).resolve().parents[2]
PREFIX='packet_sram_buffered_'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    out=args.out.resolve()
    out.mkdir(exist_ok=False)
    inventory={}
    tests={}
    def retain(path):
        relative=path.relative_to(REPO)
        key=str(relative)
        if key in inventory: return
        data=path.read_bytes()
        destination=out/relative
        destination.parent.mkdir(parents=True,exist_ok=True)
        item=dict(sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),full_source=str(relative))
        if path.suffix in ('.log','.rpt') and len(data)>24000:
            text=data.decode(errors='replace')
            lines=text.splitlines()
            first=text.find('\nStartpoint:')
            second=text.find('\nStartpoint:',first+1) if first>=0 else -1
            excerpt=text[:second] if 0<second<24000 else '\n'.join(lines[:70])
            excerpt+='\n[Middle omitted; complete source identified by SHA256]\n'+'\n'.join(lines[-70:])+'\n'
            destination=destination.with_suffix(destination.suffix+'.excerpt.txt')
            destination.write_text(excerpt)
            item['excerpt']=True
        else:
            shutil.copy2(path,destination)
        item['archived']=str(destination.relative_to(out))
        inventory[key]=item
        if path.suffix=='.xml':
            tree=ElementTree.fromstring(data)
            tests[key]=dict(tests=len(tree.findall('.//testcase')),
                failures=len(tree.findall('.//failure')),errors=len(tree.findall('.//error')),
                skipped=len(tree.findall('.//skipped')))

    root=REPO/'test/sim_build/packet_sram_buffered_production_20261030_01'
    frozen=json.loads((root/'frozen_inputs.json').read_text())
    changed=[name for name,sha in frozen.items() if digest(root/name)!=sha]
    if changed: raise ValueError('Frozen implementation inputs changed: '+str(changed))
    paths=('src','info.yaml','constraints','tools/timing','librelane_plugin_pio.py',
        '.github/workflows/gds.yaml',':!**/__pycache__/**')
    diff=subprocess.run(['git','-c','core.autocrlf=true','-c','core.safecrlf=false',
        'diff','--exit-code','bb7c5ef','--',*paths],cwd=REPO,capture_output=True,text=True)
    if diff.returncode: raise ValueError('Active production differs from qualified parent: '+diff.stdout[:4000])
    if 'packet/' in (REPO/'info.yaml').read_text(): raise ValueError('Experimental SRAM unexpectedly active')
    cases=sorted((REPO/'test/sim_build').glob(PREFIX+'20261030*'))
    cases += sorted((REPO/'test/sim_build').glob(PREFIX+'*20261030*'))
    cases += [REPO/'test/sim_build/packet_tool_validation_20261030_01',
        REPO/'test/sim_build/packet_sram_cones_20261030_02']
    allowed={'job.json','manifest.json','frozen_inputs.json','supply_audit.json',
        'parent_comparison.json','matched_comparison.json','extracted_comparison.json',
        'contract.json','contract_audit.json','data_audit.json','clock_audit.json','audit.json',
        'resolved_recipe.json','measured_fanout_contract.json','resolved.json',
        'source_clock_audit.json','report.json','summary.json','disposition.json',
        'runtime.json','gate_runtime.json','retry_gate_runtime.json','metrics.json','alternative_fast_libraries.json',
        'native_comparison.json','replay_comparison.json','source_diagnosis.json','electrical.rpt','yosys.log'}
    for case in dict.fromkeys(cases):
        if not case.is_dir(): continue
        for path in sorted(case.rglob('*')):
            if not path.is_file() or any(part in ('tt','.cache','__pycache__') for part in path.relative_to(case).parts): continue
            name=path.name
            selected=(name in allowed or name.endswith('_audit.json') or
                name in ('results.xml','packet_results.xml','differential.log','strict_signoff.log','resolve_eco_targets.log') or
                path.parent==case and path.suffix=='.log')
            if selected and path.stat().st_size<8_000_000: retain(path)
        stages=sorted((case/'run').glob('*-openroad-stapostpnr'))
        if stages:
            stage=stages[-1]
            retain(stage/'state_out.json')
            for corner in sorted(stage.glob('nom_*')):
                for name in ('sta.log','max.rpt','min.rpt','checks.rpt','violations.rpt'):
                    path=corner/name
                    if path.is_file(): retain(path)
    # Preserve the precise portal implementation and the repair/qualification recipe.
    for path in sorted((REPO/'tools/packet_sram').glob('*')):
        if path.is_file(): retain(path)
    for name in ('src/pio_subsystem.sv','src/pio_host_bank.sv','src/packet/packet_sram.sv',
        'src/packet/packet_sram_portal.sv','src/config.json','tools/timing/packet_contracts/main.json',
        'tools/timing/packet_contracts/tail.json','tools/timing/packet_contracts/adaptive.json'):
        if (root/name).is_file(): retain(root/name)
    summary=dict(disposition='Experimental SRAM is not promoted; active production matches qualified parent',
        exact_fast_sram_model_available=False,frozen_inputs_unchanged=len(frozen),tests=tests,
        production_job=json.loads((root/'job.json').read_text()))
    (out/'disposition.json').write_text(json.dumps(summary,indent=2)+'\n')
    (out/'full_source_inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
    hashes={str(p.relative_to(out)):digest(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'evidence_sha256.json').write_text(json.dumps(hashes,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__': main()
