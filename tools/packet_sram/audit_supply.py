"""Check the serialized supply repair's identity, geometry and local shorts."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import odb

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'timing'))
from audit_wire_contacts import find_contacts


def read(path):
    db=odb.dbDatabase.create(); odb.read_db(db,str(path))
    return db,db.getChip().getBlock()


def identity(block):
    return {i.getName():(i.getMaster().getName(),i.getLocation(),str(i.getOrient()),
            tuple(sorted((t.getMTerm().getName(),t.getNet().getName() if t.getNet() else None) for t in i.getITerms()))) for i in block.getInsts()}


def shapes(block):
    result=[]
    for net in block.getNets():
        for wire in net.getSWires():
            for shape in wire.getWires():
                if shape.isVia():
                    via=shape.getTechVia() or shape.getBlockVia(); x,y=shape.getViaXY()
                    for box in via.getBoxes():
                        layer=box.getTechLayer()
                        if layer.getType()!='ROUTING': continue
                        result.append((net.getName(),layer.getName(),(box.xMin()+x,box.yMin()+y,box.xMax()+x,box.yMax()+y)))
                else:
                    result.append((net.getName(),shape.getTechLayer().getName(),(shape.xMin(),shape.yMin(),shape.xMax(),shape.yMax())))
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--step',type=Path,required=True); p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(); step=a.step
    paths=[step/'before_supply.odb',step/'supplied.odb',step/'tt_um_shanebri_top.odb']
    original,before=read(paths[0]); expected_db,expected=read(paths[1]); actual_db,actual=read(paths[2])
    assert identity(before)==identity(expected)==identity(actual),'Logical/placement identity changed'
    expected_shapes,actual_shapes=shapes(expected),shapes(actual)
    assert Counter(expected_shapes)==Counter(actual_shapes),'Serialized power geometry differs from supplied ODB'
    assert not any(layer=='TopMetal1' for net,layer,r in actual_shapes),'Forbidden power layer'
    # Independent contact check includes native macro-ring vias and added tabs.
    local=[s for s in actual_shapes if s[1] in ('Metal3','Metal4') and s[2][0]<1056800 and s[2][2]>660000 and s[2][1]<394360 and s[2][3]>290000]
    contacts=find_contacts(local)
    report=dict(status='failed' if contacts else 'pass',scope='supply identity/serialization/permitted layers/local contact check; full DRC/LVS still required',
        instances=len(identity(actual)),all_signal_and_supply_connections_and_placements_preserved=True,
        exact_serialized_power_shapes=True,local_shapes=len(local),contacts=contacts,
        sha256={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths})
    with a.out.open('x') as f: json.dump(report,f,indent=2); f.write('\n')
    print(report['status'], 'local power contact groups',len(contacts))
    if contacts: raise SystemExit(1)


if __name__=='__main__': main()
