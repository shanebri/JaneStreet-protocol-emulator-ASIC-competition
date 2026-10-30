"""Measure post-antenna data fanout and bind only overloaded current drivers."""
import argparse
import hashlib
import json
from pathlib import Path
import odb
from audit_clock_tree import snapshot,topology
from resolve_eco_targets import make_contract,resolve

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--odb',type=Path,required=True); p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
db=odb.dbDatabase.create(); odb.read_db(db,str(a.odb)); block=db.getChip().getBlock()
data=snapshot(block); clock=topology(data)
clock_nets={data[1]['clk']}|{data[0][b['instance']][1]['X'] for b in clock['buffers']}
if clock['clock_buffer_outputs_above8']:
    raise ValueError('Post-route clock branch overload requires a separate audited clock repair')
operations=[]; measured=[]
for net in block.getNets():
    if net.getSigType() in ('POWER','GROUND') or net.getName() in clock_nets: continue
    count=len(data[3].get(net.getName(),[]))
    if count<=8: continue
    drivers=[t for t in net.getITerms() if t.getMTerm().getIoType()=='OUTPUT']
    ports=[t for t in net.getBTerms() if t.getIoType()=='INPUT']
    if len(drivers)+len(ports)!=1: raise ValueError('Ambiguous overloaded-net driver: '+net.getName())
    if ports: target=ports[0].getName(); master=None
    else:
        t=drivers[0]; target=t.getInst().getName()+'/'+t.getMTerm().getName(); master=t.getInst().getMaster().getName()
    operations.append(dict(kind='buffer',target=target,old=master,max_loads=4,location='sink_centroid'))
    measured.append(dict(target=target,actual_input_loads=count,includes_antenna_pins=True))
operations.sort(key=lambda op:op['target'])
contract=make_contract(data,operations)
assert resolve(data,contract)==operations
contract.update(reference_odb_sha256=hashlib.sha256(a.odb.read_bytes()).hexdigest(),
    policy='Only measured non-clock sources above eight actual loads; buffered partitions at most four',measurements=measured)
with a.out.open('x') as f: json.dump(contract,f,indent=2); f.write('\n')
print('PASS: bound',len(operations),'measured overloaded data branches; all clock nets excluded')
