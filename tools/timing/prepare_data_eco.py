"""Freeze post-antenna connectivity for matched full-reroute ECO experiments.

Run with OpenROAD Python. Removes signal wires only; preserves all instances,
placements, terminal connections and power-grid wires. The shared preparation
is part of the control, not an optimization credited to a candidate.
"""
import argparse
import hashlib
import json
from pathlib import Path
from audit_clock_tree import snapshot


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    import odb
    state=json.loads(a.state.read_text())
    db=odb.dbDatabase.create(); odb.read_db(db,state['odb'])
    block=db.getChip().getBlock()
    before=snapshot(block)[:3]
    positions={i.getName():(i.getLocation(),i.getOrient(),i.getPlacementStatus()) for i in block.getInsts()}
    pg={n.getName():(len(n.getSWires()),n.getWire() is not None) for n in block.getNets() if n.getSigType() in ('POWER','GROUND')}
    removed=0
    for net in block.getNets():
        wire=net.getWire()
        if wire is not None and net.getSigType() not in ('POWER','GROUND'):
            odb.dbWire.destroy(wire)
            removed+=1
    if snapshot(block)[:3]!=before or positions!={i.getName():(i.getLocation(),i.getOrient(),i.getPlacementStatus()) for i in block.getInsts()}:
        raise ValueError('Shared route removal changed logic or placement')
    if pg!={n.getName():(len(n.getSWires()),n.getWire() is not None) for n in block.getNets() if n.getSigType() in ('POWER','GROUND')}:
        raise ValueError('Power-grid wires changed')
    if any(n.getWire() is not None for n in block.getNets() if n.getSigType() not in ('POWER','GROUND')):
        raise ValueError('Signal wires remain')
    a.out.mkdir(parents=True,exist_ok=False)
    odb_path=a.out/'unrouted.odb'; def_path=a.out/'unrouted.def'
    odb.write_db(db,str(odb_path)); odb.write_def(block,str(def_path))
    source_odb=Path(state['odb'])
    state['odb'],state['def']=str(odb_path),str(def_path)
    (a.out/'state.json').write_text(json.dumps(state,indent=2)+'\n')
    (a.out/'preparation.json').write_text(json.dumps(dict(status='pass',signal_wires_removed=removed,
        scope='common full-reroute preparation; logic/placement/PG unchanged',
        source_state=str(a.state),source_state_sha256=hashlib.sha256(a.state.read_bytes()).hexdigest(),
        source_odb_sha256=hashlib.sha256(source_odb.read_bytes()).hexdigest(),
        output_odb_sha256=hashlib.sha256(odb_path.read_bytes()).hexdigest(),
        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),indent=2)+'\n')
    print('PASS: removed',removed,'signal wires; logic, placement and power grid unchanged')


if __name__=='__main__':
    main()
