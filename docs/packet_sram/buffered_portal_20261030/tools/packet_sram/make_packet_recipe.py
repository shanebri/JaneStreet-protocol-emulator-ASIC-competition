"""Derive a uniquely bound candidate repair from measured paths and loads.

No generated numeric cell name is reused across builds. Every selected driver
gets a >=4-round structural identity and must resolve uniquely before mutation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import odb

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'timing'))
from audit_clock_tree import snapshot,topology
from resolve_eco_targets import make_contract,resolve

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--trial',type=Path,required=True)
p.add_argument('--diagnostic',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--source-state',type=Path)
p.add_argument('--skip-macro',action='store_true')
p.add_argument('--setup-margin',type=float,default=.5)
p.add_argument('--sizes-per-path',type=int,default=4)
p.add_argument('--max-sizes',type=int,default=24)
a=p.parse_args(); root=a.trial.resolve(); out=a.out.resolve(); out.mkdir(exist_ok=False)
state_path=a.source_state or next((root/'run').glob('*-pio-preparesignalroutes/state_out.json'))
state=json.loads(state_path.read_text()); db=odb.dbDatabase.create(); odb.read_db(db,state['odb'])
block=db.getChip().getBlock(); data=snapshot(block)
macro=block.findInst('pio.packet.storage.memory'); assert macro
data[4].add((macro.getName(),'A_CLK'))
clock=topology(data)
clock_cells={item['instance'] for item in clock['buffers']}
mx,my=macro.getLocation(); height=macro.getMaster().getHeight()
ops={}; evidence={}
def driver(net):
    drivers=[t for t in net.getITerms() if t.getMTerm().getIoType()=='OUTPUT']
    ports=[t for t in net.getBTerms() if t.getIoType()=='INPUT']
    assert len(drivers)+len(ports)==1,net.getName()
    if ports: return ports[0].getName(),None
    t=drivers[0]; return t.getInst().getName()+'/'+t.getMTerm().getName(),t.getInst().getMaster().getName()
for term in ([] if a.skip_macro else macro.getITerms()):
    name=term.getMTerm().getName()
    if term.getMTerm().getSigType() in ('POWER','GROUND') or name in ('A_CLK','A_DLY'): continue
    boxes=[s for pin in term.getMTerm().getMPins() for s in pin.getGeometry()]
    box=boxes[0]; cx=mx+(box.xMin()+box.xMax())/2
    cy=my-18000 if box.yMin()<height/2 else my+height+18000
    source,old=driver(term.getNet())
    op=dict(kind='buffer',target=source,old=old,max_loads=4,location_um=[cx/1000,cy/1000])
    if term.getMTerm().getIoType()=='INPUT': op['loads']=['pio.packet.storage.memory/'+name]
    if source in ops:
        ops[source].pop('loads',None); ops[source]['location']='sink_centroid'; ops[source].pop('location_um',None)
    else: ops[source]=op
    evidence.setdefault(source,[]).append('Macro pin '+name+' local electrical isolation')
slow=next((a.diagnostic/'run').glob('*-openroad-stapostpnr'))/'nom_slow_1p08V_125C'
electrical=(slow/'sta.log').read_text().split(' report_check_types -max_slew -max_cap -max_fanout -violators',1)[1].split(' report_parasitic_annotation',1)[0]
pins=re.findall(r'^([^\s]+)\s+[-\d.]+\s+[-\d.]+.*\(VIOLATED\)',electrical,re.M)
for pin in sorted(set(pins)):
    if '/' in pin:
        name,port=pin.rsplit('/',1); net=block.findInst(name).findITerm(port).getNet()
    else: net=block.findBTerm(pin).getNet()
    source,old=driver(net)
    if any((cell,port) in data[4] for cell,port in data[3].get(net.getName(),[])):
        raise ValueError('Electrical data repair would touch a clock: '+source)
    if source not in ops or 'loads' in ops[source]:
        ops[source]=dict(kind='buffer',target=source,old=old,max_loads=4,location='sink_centroid')
    evidence.setdefault(source,[]).append('Measured electrical violation at '+pin)
sizes={}
# A long source-to-buffer segment may remain electrically slow even after its
# sink fanout was split. Strengthen that measured source, not an unrelated cone.
for pin in sorted(set(pins)):
    if '/' not in pin: continue
    name,port=pin.rsplit('/',1); net=block.findInst(name).findITerm(port).getNet()
    source,old=driver(net)
    if old is None or not old.endswith('_1'): continue
    cell=source.rsplit('/',1)[0]
    if cell in clock_cells or 'df' in old or old.startswith('RM_'): continue
    new=old[:-1]+('4' if '_buf_' in old else '2')
    if db.findMaster(new) is not None:
        sizes[cell]=dict(kind='size',instance=cell,old=old,new=new)
        evidence.setdefault(cell,[]).append('Measured residual electrical slew/drive source '+pin)
for path in (slow/'max.rpt').read_text().split('Startpoint: ')[1:]:
    slack=re.search(r'([-+\d.]+)\s+slack \(',path)
    if not slack or float(slack[1])>=a.setup_margin: continue
    section=path.split('data arrival time')[0]
    arcs=[]
    pattern=r'^\s*\d+\s+[-\d.]+\s+[-\d.]+\s+([-\d.]+)\s+[-\d.]+\s+[v^]\s+(\S+)/(\w+)\s+\((sg13cmos5l_\w+)\)'
    for delay,cell,pin,master in re.findall(pattern,section,re.M):
        if float(delay)<.35 or not master.endswith(('_1','_2')) or 'df' in master or cell in clock_cells: continue
        replacement=master[:-1]+('4' if '_buf_' in master or master.endswith('_2') else '2')
        if db.findMaster(replacement) is None: continue
        if any((cell,p) in data[4] for p in data[0][cell][1]): continue
        arcs.append((float(delay),cell,master,replacement))
    for delay,cell,old,new in sorted(arcs,reverse=True)[:a.sizes_per_path]:
        if len(sizes)>=a.max_sizes and cell not in sizes: continue
        sizes[cell]=dict(kind='size',instance=cell,old=old,new=new)
        evidence.setdefault(cell,[]).append(f'Measured data arc {delay} ns on setup path slack {slack[1]} ns')
operations=list(ops.values())+list(sizes.values())
contract=make_contract(data,operations)
assert resolve(data,contract)==operations
contract['reference_odb_sha256']=hashlib.sha256(Path(state['odb']).read_bytes()).hexdigest()
(out/'recipe.json').write_text(json.dumps(operations,indent=2)+'\n')
(out/'contract.json').write_text(json.dumps(contract,indent=2)+'\n')
(out/'selection_evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
(out/'empty_postroute_contract.json').write_text(json.dumps(make_contract(data,[]),indent=2)+'\n')
print('Uniquely bound',len(ops),'buffer sources and',len(sizes),'gate strengths')
