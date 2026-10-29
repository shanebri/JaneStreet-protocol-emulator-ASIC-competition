"""Audit native route finalization against its exact pre-finalization database.

FIXED wires are restored as ordinary initial routes before the last native DRT
pass. This lets the router serialize all of its final geometry consistently.
Connectivity, cells, locations, orientations and boundary pins must not change.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from routing_delta import compare


def unfixed_nets_def(text):
    section = re.search(r'\bNETS\s+\d+\s*;.*?END NETS',text,re.S)
    design = re.search(r'\bDESIGN\s+(\S+)\s*;',text)
    units = re.search(r'\bUNITS DISTANCE MICRONS\s+(\d+)\s*;',text)
    if not all((section,design,units)):
        raise ValueError('Incomplete routed DEF')
    nets = re.sub(r'\+\s+FIXED\b','+ ROUTED',section[0])
    if re.search(r'\+\s+(?:COVER|SHIELD)\b',nets):
        raise ValueError('Unsupported route type')
    return ('VERSION 5.8 ;\nDIVIDERCHAR "/" ;\nBUSBITCHARS "[]" ;\n'
            f'DESIGN {design[1]} ;\nUNITS DISTANCE MICRONS {units[1]} ;\n'
            +nets+'\nEND DESIGN\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('before','before-def','after','after-def','out'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    import odb
    from audit_clock_tree import snapshot
    from audit_wire_contacts import wire_shapes,find_contacts
    def read(path):
        db=odb.dbDatabase.create();odb.read_db(db,str(path))
        block=db.getChip().getBlock()
        data=snapshot(block)
        locations={i.getName():(i.getLocation(),i.getOrient(),i.getMaster().getName()) for i in block.getInsts()}
        return db,block,data,locations
    bdb,bb,before,bl=read(a.before)
    adb,ab,after,al=read(a.after)
    if before[:3]!=after[:3] or bl!=al:
        raise ValueError('Route finalization changed logical connectivity or placement')
    delta=compare(a.before_def,a.after_def)
    shapes,nets=wire_shapes(ab,a.after_def)
    contacts=find_contacts(shapes)
    result=dict(status='fail' if contacts else 'pass',connectivity_cells_and_placement_unchanged=True,
                routing_delta=delta,wire_contact_groups=contacts,routed_nets=nets,
                after_def=str(a.after_def),sha256={str(path):hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in (a.before,a.before_def,a.after,a.after_def,Path(__file__),Path(__file__).with_name('audit_wire_contacts.py'))})
    with a.out.open('x') as f: json.dump(result,f,indent=2);f.write('\n')
    if contacts: raise ValueError('Final serialized route contains inter-net metal contacts')
    print('PASS: native route finalization, unchanged connectivity/placement, zero inter-net wire contacts')


if __name__=='__main__': main()
