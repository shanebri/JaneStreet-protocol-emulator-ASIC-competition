"""Archive the rejected repair evidence and verify active production identity."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from xml.etree import ElementTree

repo=Path(__file__).resolve().parents[2]
root=repo/'test/sim_build/packet_sram_repair_20261030_04'
tested=repo/'test/sim_build/packet_sram_repair_20261030_01'
out=repo/'docs/packet_sram/supply_repair_20261030'
if '--compact' in sys.argv:
    sources={}
    for path in sorted(out.glob('nom_*')):
        if not path.is_file() or path.suffix not in ('.rpt','.log'): continue
        data=path.read_bytes(); text=data.decode()
        sources[path.name]=dict(sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),
            retained_full_source='test/sim_build/packet_sram_repair_20261030_04/extracted_diagnostic_01/run/3-openroad-stapostpnr')
        if path.suffix=='.rpt':
            first=text.find('\nStartpoint:'); second=text.find('\nStartpoint:',first+1) if first>=0 else -1
            excerpt=text[:second] if second>=0 else '\n'.join(text.splitlines()[:150])
        else:
            lines=text.splitlines(); excerpt='\n'.join(lines[:50])+ '\n[Middle of full log omitted; see source hash]\n'+'\n'.join(lines[-50:])
        path.with_suffix(path.suffix+'.excerpt.txt').write_text(excerpt+'\n')
        path.unlink()
    (out/'full_report_sources.json').write_text(json.dumps(sources,indent=2)+'\n')
    files={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file() and p.name!='evidence_sha256.json'}
    (out/'evidence_sha256.json').write_text(json.dumps(files,indent=2)+'\n')
    print('Compacted report copies; full source reports remain in the trial directory')
    raise SystemExit(0)
out.mkdir(exist_ok=True)
assert not any(out.iterdir()),'Evidence directory must be empty'
names=[]
for line in (root/'info.yaml').read_text().split('  source_files:\n')[1].splitlines():
    if not line.startswith('    - '): break
    names.append(line.split('"')[1])
assert names
assert (root/'info.yaml').read_bytes()==(tested/'info.yaml').read_bytes()
hashes={}
for name in names+['packet/macro_blackbox.v']:
    candidate=root/'src'/name; reference=tested/'src'/name
    assert candidate.read_bytes()==reference.read_bytes(),name
    hashes[name]=hashlib.sha256(candidate.read_bytes()).hexdigest()
xml=tested/'test/results.xml'
tree=ElementTree.parse(xml)
assert len(tree.findall('.//testcase'))==39
assert not any(tree.findall('.//'+tag) for tag in ('failure','error','skipped'))
paths=('src','info.yaml','constraints','tools/timing','librelane_plugin_pio.py','.github/workflows/gds.yaml',':!**/__pycache__/**')
diff=subprocess.run(['git','-c','core.autocrlf=true','-c','core.safecrlf=false','diff','--exit-code','bb7c5ef','--',*paths],cwd=repo,capture_output=True,text=True)
assert diff.returncode==0,diff.stdout[:4000]
assert 'packet/' not in (repo/'info.yaml').read_text()
summary=dict(disposition='rejected; no candidate promotion; active production matches qualified parent',
    production_code_diff=diff.stdout,rtl_regression=dict(passed=39,failed=0,skipped=0,
        tested_snapshot=str(tested),final_snapshot_rtl_identical=True,source_sha256=hashes),
    physical_result='native supply connectivity and initial route pass; production ECO identity fails; extracted diagnostic timing/electrical gate fails',
    exact_fast_sram_characterization_available=False)
(out/'disposition.json').write_text(json.dumps(summary,indent=2)+'\n')
copies={
    root/'job.json':'production_job.json',root/'frozen_inputs.json':'frozen_inputs.json',
    root/'production.log':'production.log',root/'supply_audit.json':'supply_audit.json',
    root/'extracted_comparison.json':'extracted_comparison.json',
    root/'extracted_diagnostic_01/manifest.json':'extracted_diagnostic_manifest.json',
    root/'extracted_diagnostic_01/strict_signoff.log':'strict_signoff.log',
    root/'extracted_diagnostic_01/run/3-openroad-stapostpnr/state_out.json':'extracted_state_out.json',
    root/'run/45-openroad-detailedrouting/state_out.json':'routed_state_out.json',
    root/'run/21-openroad-generatepdn/openroad-generatepdn.log':'power_grid.log',
    root/'run/21-openroad-generatepdn/supplied.json':'supply_geometry.json',
    root/'run/47-openroad-dataeco/resolve_eco_targets.log':'production_rejection.log',
    root/'run/36-openroad-repairclockfanout/clock_audit.json':'clock_audit.json',
    root/'trial_portal_tb.log':'portal_test.log',root/'pio_subsystem_tb.log':'subsystem_test.log',
    root/'src/config.json':'candidate_config.json',xml:'rtl_results.xml',
}
for src,name in copies.items(): shutil.copy2(src,out/name)
for source in ('repair_supply.py','packet_pdn.tcl','packet_pdn_cfg.tcl'):
    shutil.copy2(root/'tools/timing'/source,out/source)
for corner in ('nom_slow_1p08V_125C','nom_typ_1p20V_25C','nom_fast_1p32V_m40C'):
    reports=root/'extracted_diagnostic_01/run/3-openroad-stapostpnr'/corner
    for filename in ('sta.log','max.rpt','min.rpt','checks.rpt','violations.rpt'):
        src=reports/filename
        if src.is_file(): shutil.copy2(src,out/(corner+'_'+filename))
files={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}
(out/'evidence_sha256.json').write_text(json.dumps(files,indent=2)+'\n')
print(summary['disposition'])
