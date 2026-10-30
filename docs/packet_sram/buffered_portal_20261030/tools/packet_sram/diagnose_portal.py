"""Map the rejected extracted host paths and electrical loads to source state."""
import hashlib
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import odb

REPO=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--trial',type=Path,default=REPO/'test/sim_build/packet_sram_repair_20261030_04')
p.add_argument('--diagnostic',type=Path)
p.add_argument('--out',type=Path,default=REPO/'test/sim_build/packet_sram_cones_20261030_02')
p.add_argument('--slack-below',type=float,default=0)
args=p.parse_args()
BASE=args.trial.resolve(); OUT=args.out.resolve()
DIAGNOSTIC=args.diagnostic.resolve() if args.diagnostic else BASE/'extracted_diagnostic_01'
OUT.mkdir(exist_ok=False)
syn=BASE/'run/06-yosys-synthesis/tt_um_shanebri_top.nl.v.json'
module=json.loads(syn.read_text())['modules']['tt_um_shanebri_top']
with (OUT/'yosys.log').open('w') as log:
    subprocess.run(['yosys','-Q','-T','-p',f'read_json {syn}; write_verilog -noattr -noexpr {OUT}/renamed.v; write_verilog -noattr -noexpr -norename {OUT}/named.v'],stdout=log,stderr=subprocess.STDOUT,check=True)
def cells(text):
    return [(m,n,re.sub(r'\s+','',body)) for m,n,body in re.findall(r'^  (sg13cmos5l_\w+)\s+(\S+)\s+\((.*?)\);',text,re.M|re.S)]
renamed=cells((OUT/'renamed.v').read_text()); named=cells((OUT/'named.v').read_text())
assert renamed==cells(syn.with_suffix('').read_text())
assert len(renamed)==len(named) and all(a[0]==b[0] for a,b in zip(renamed,named))
identities={a[1]:b for a,b in zip(renamed,named)}
aliases={}
for name,net in module['netnames'].items():
    for index,bit in enumerate(net['bits']):
        aliases.setdefault(bit,[]).append(name+(f'[{index+net.get("offset",0)}]' if len(net['bits'])>1 else ''))
def state_alias(cell):
    if cell not in identities: return []
    q=re.search(r'\.Q\((.*?)\)',identities[cell][2])
    if not q: return []
    name=q[1].lstrip('\\')
    if name in module['netnames']: bits=module['netnames'][name]['bits']
    else:
        match=re.fullmatch(r'(.*)\[(\d+)\]',name)
        if not match or match[1] not in module['netnames']: return [name]
        net=module['netnames'][match[1]]; bits=[net['bits'][int(match[2])-net.get('offset',0)]]
    all_aliases=sorted({n for bit in bits for n in aliases.get(bit,[])})
    return [n for n in all_aliases if not n.startswith('$')] or all_aliases
report=next((DIAGNOSTIC/'run').glob('*-openroad-stapostpnr'))/'nom_slow_1p08V_125C'
paths=[]
for block in (report/'max.rpt').read_text().split('Startpoint: ')[1:]:
    slack=re.search(r'([-+\d.]+)\s+slack \(',block)
    if not slack or float(slack[1])>=args.slack_below: continue
    endpoint=re.search(r'^Endpoint: (\S+)',block,re.M)[1]
    paths.append(dict(start=block.splitlines()[0],endpoint=endpoint,slack_ns=float(slack[1]),source_aliases=state_alias(endpoint)))
db=odb.dbDatabase.create(); odb.read_db(db,str(next((DIAGNOSTIC/'run').glob('*-openroad-fillinsertion/*.odb'))))
block=db.getChip().getBlock()
electrical=(report/'sta.log').read_text().split(' report_check_types -max_slew -max_cap -max_fanout -violators',1)[1].split(' report_parasitic_annotation',1)[0]
loads=[]
pins=re.findall(r'^([^\s]+)\s+[-\d.]+\s+[-\d.]+.*\(VIOLATED\)',electrical,re.M)
for pinname in sorted(set(pins)):
    if '/' in pinname:
        instance,pin=pinname.rsplit('/',1); inst=block.findInst(instance)
        term=inst.findITerm(pin); net=term.getNet(); master=inst.getMaster().getName()
    else:
        net=block.findBTerm(pinname).getNet(); master='port'
    row=dict(pin=pinname,master=master,net=net.getName(),loads=[],drivers=[])
    for term in net.getITerms():
        inst=term.getInst(); item=dict(pin=inst.getName()+'/'+term.getMTerm().getName(),master=inst.getMaster().getName(),location=inst.getLocation(),source_state=state_alias(inst.getName()))
        row['loads' if term.getMTerm().getIoType()=='INPUT' else 'drivers'].append(item)
    loads.append(row)
result=dict(failing_paths=paths,electrical=loads,synthesis_sha256=hashlib.sha256(syn.read_bytes()).hexdigest())
(OUT/'source_diagnosis.json').write_text(json.dumps(result,indent=2)+'\n')
(OUT/'electrical.rpt').write_text(electrical)
for row in paths: print(row['start'],'->',row['source_aliases'],row['slack_ns'])
print('electrical pins',len(loads))
