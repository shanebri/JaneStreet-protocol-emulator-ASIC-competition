"""Restore and fix only source wires whose connections and pin locations match.

OpenROAD Python entrypoint. GRT has removed detailed wires in the ECO output.
This copies eligible physical wire records from the source DEF via a NETS-only
incremental import. It never freezes a changed net or a net incident to a
moved/replaced cell. Independent final DRC, antenna, LVS and STA remain required.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
from collections import defaultdict

from audit_clock_tree import snapshot
from closure_trial import sha
from routing_delta import read_def


def eligible_nets(before, after, before_locations, after_locations):
    def endpoints(data):
        cells, ports, nets, _, _ = data
        result = {net: set() for net in nets}
        for cell, (master, pins) in cells.items():
            for pin, net in pins.items():
                if net is not None:
                    result[net].add(('cell',cell,master,pin))
        for port, net in ports.items():
            if net is not None:
                result[net].add(('port',port))
        return result
    a,b = endpoints(before),endpoints(after)
    return {net for net in a.keys() & b.keys() if a[net] == b[net]
        and all(item[0] != 'cell' or before_locations[item[1]] == after_locations[item[1]] for item in a[net])}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('before','before-def','after','after-def','out'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args(); a.out.mkdir(parents=True,exist_ok=False)
    import odb
    def read(path):
        db=odb.dbDatabase.create(); odb.read_db(db,str(path))
        block=db.getChip().getBlock()
        data=snapshot(block)
        loc={i.getName():(i.getLocation(),i.getOrient(),i.getMaster().getName()) for i in block.getInsts()}
        name=block.getName(); units=block.getDbUnitsPerMicron()
        odb.dbDatabase.destroy(db)
        return data,loc,name,units
    before,bl,_,_=read(a.before); after,al,name,units=read(a.after)
    br,bc,bp=read_def(a.before_def); ar,ac,ap=read_def(a.after_def)
    if bp!=ap:
        raise ValueError('Signal port connections or geometry changed')
    eligible=eligible_nets(before,after,bl,al)
    eligible={n for n in eligible if br.get(n) is not None}
    if len(eligible)<.9*sum(v is not None for v in br.values()):
        raise ValueError('Too few untouched routes for this preservation experiment')
    text=a.before_def.read_text()
    section=re.search(r'\bNETS\s+\d+\s*;(.*?)END NETS',text,re.S)[1]
    records=[]; found=set()
    for net,record in re.findall(r'^\s*-\s+(\S+)\s+(.*?);',section,re.M|re.S):
        if net in eligible:
            records.append('- '+net+' '+re.sub(r'\+\s+ROUTED\b','+ FIXED',record)+';')
            found.add(net)
    if found!=eligible: raise ValueError('Missing source wire record')
    fixed_def=a.out/'fixed_nets.def'
    fixed_def.write_text(f'VERSION 5.8 ;\nDIVIDERCHAR "/" ;\nBUSBITCHARS "[]" ;\n'
        f'DESIGN {name} ;\nUNITS DISTANCE MICRONS {units} ;\nNETS {len(records)} ;\n'
        +'\n'.join(records)+'\nEND NETS\nEND DESIGN\n')
    result_odb=a.out/'preserved.odb'; result_def=a.out/'preserved.def'
    script=a.out/'restore.tcl'
    # ODB INCREMENTAL updates only COMPONENTS/PINS and ignores NETS. The
    # FLOORPLAN update mode includes NETS; importing a nets-only file avoids
    # changing the existing floorplan, placements or pin objects.
    script.write_text(f'read_db {{{a.after}}}\nread_def -floorplan_initialize {{{fixed_def}}}\n'
        f'write_db {{{result_odb}}}\nwrite_def {{{result_def}}}\n')
    with (a.out/'restore.log').open('w') as log:
        subprocess.run(['openroad','-no_init','-exit',str(script)],stdout=log,stderr=subprocess.STDOUT,check=True)
    restored,rl,_,_=read(result_odb)
    rr,rc,rp=read_def(result_def)
    if restored[:3]!=after[:3] or rl!=al or rc!=ac or rp!=ap:
        raise ValueError('Wire restoration changed connectivity, cells, placement or pin geometry')
    for net in rr:
        expected=br[net] if net in eligible else ar[net]
        if rr[net]!=expected:
            raise ValueError('Unexpected restored geometry: '+net)
    output_text=result_def.read_text()
    fixed_count=len(re.findall(r'\+\s+FIXED\b',re.search(r'\bNETS\s+\d+\s*;(.*?)END NETS',output_text,re.S)[1]))
    if fixed_count!=len(eligible): raise ValueError('Restored wires are not all FIXED')
    result=dict(status='pass',scope='only unchanged connections and locations restored as fixed wires',
        fixed_nets=sorted(eligible),fixed_net_count=len(eligible),
        excluded_source_nets=sorted(set(br)-eligible),sha256={str(p):sha(p) for p in
            (a.before,a.before_def,a.after,a.after_def,fixed_def,result_odb,result_def,Path(__file__))})
    (a.out/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS: restored',len(eligible),'unchanged wires with identical geometry; all other views unchanged')


if __name__=='__main__': main()
