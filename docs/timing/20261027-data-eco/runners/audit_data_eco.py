"""Fail closed unless a data ECO changes only its declared strengths/buffers."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from audit_clock_tree import snapshot, topology
from audit_nor_trial import audit_models


def audit(before,after,operations):
    old,ports,nets,loads,_=before
    new,new_ports,new_nets,_,_=after
    if not old.keys()<=new.keys() or ports!=new_ports or not nets<=new_nets:
        raise ValueError('Removed logic/nets or changed ports')
    replacements={o['instance']:(o['old'],o['new']) for o in operations if o['kind']=='size'}
    roots=[]; expected=0; target_counts={}
    for op in operations:
        if op['kind']!='buffer':
            continue
        target=op['target']
        if '/' in target:
            cell,pin=target.split('/')
            if old[cell][0]!=op['old']:
                raise ValueError('Unexpected original buffer-target master')
            net=old[cell][1][pin]
        else:
            net=ports[target]
        if any(pin=='CLK' for _,pin in loads[net]):
            raise ValueError('Data buffer targets a clock')
        count=len(loads[net])
        target_counts[target]=count
        roots.append(net); expected+=math.ceil(count/op['max_loads'])
    added=sorted(new.keys()-old.keys())
    if len(added)!=expected:
        raise ValueError(f'Expected {expected} added buffers, got {len(added)}')
    aliases={}
    for name in added:
        master,pins=new[name]
        if not name.startswith('eco_data_') or master!='sg13cmos5l_buf_4' or set(pins)!={'A','X'}:
            raise ValueError('Unexpected new cell/function')
        if pins['X'] in aliases or pins['A'] not in roots:
            raise ValueError('Unexpected buffer driver or source')
        aliases[pins['X']]=pins['A']
    if new_nets-nets!=aliases.keys():
        raise ValueError('Unexpected new nets')
    for name,(master,pins) in old.items():
        new_master,new_pins=new[name]
        expected_master=replacements.get(name,(master,master))
        if expected_master[0]!=master or new_master!=expected_master[1]:
            raise ValueError('Undeclared master change: '+name)
        normalized={pin:aliases.get(net,net) for pin,net in new_pins.items()}
        if normalized!=pins:
            raise ValueError('Changed original signal connectivity: '+name)
    if topology(before)!=topology(after):
        raise ValueError('Data ECO changed clock topology')
    return dict(status='pass',original_instances=len(old),added_buffers=len(added),
        replacements=replacements,target_load_counts=target_counts,
        original_signal_connectivity_preserved=True,clock_topology_unchanged=True,
        scope='ideal buffer transparency/identical strength functions; PG excluded; not physical LVS')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('before','odb','recipe','pdk-model','out'):
        p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args()
    import odb
    db1=odb.dbDatabase.create(); odb.read_db(db1,str(a.before))
    db2=odb.dbDatabase.create(); odb.read_db(db2,str(a.odb))
    operations=json.loads(a.recipe.read_text())
    model=a.pdk_model.read_text()
    for op in operations:
        if op['kind']=='size':
            audit_models(model,(op['old'],op['new']))
    if any(o['kind']=='buffer' for o in operations):
        body=re.search(r'\bmodule sg13cmos5l_buf_4\b(.*?)\bendmodule',model,re.S)[1].split('specify')[0]
        body=re.sub(r'//[^\n]*','',body)
        if 'buf(X,A);' not in re.sub(r'\s+','',body):
            raise ValueError('Pinned buffer model is not transparent')
    result=audit(snapshot(db1.getChip().getBlock()),snapshot(db2.getChip().getBlock()),operations)
    result['sha256']={str(v):hashlib.sha256(v.read_bytes()).hexdigest() for v in (a.before,a.odb,a.recipe,a.pdk_model,Path(__file__))}
    with a.out.open('x') as f:
        json.dump(result,f,indent=2); f.write('\n')
    print('PASS: declared ECO only; all original data/clock signal connections preserved')


if __name__=='__main__':
    main()
