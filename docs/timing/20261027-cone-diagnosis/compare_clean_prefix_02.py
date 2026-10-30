"""Compare the clean clock-repair output with the measured saved-state prefix."""
import hashlib
import json
from pathlib import Path
import sys
import odb

repo = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo/'tools/timing'))
from audit_clock_tree import snapshot
from implementation_trial import template_fingerprint

paths = [repo/'test/sim_build'/p for p in (
    'clock_factors/clock_split8-01/run/02-openroad-repairclockfanout/state_out.json',
    'production_candidate_20261028_02/run/36-openroad-repairclockfanout/state_out.json')]
records = []
for path in paths:
    state = json.loads(path.read_text())
    db = odb.dbDatabase.create(); odb.read_db(db, state['odb'])
    block = db.getChip().getBlock()
    cells, ports, nets, _, _ = snapshot(block)
    records.append(dict(cells=cells, ports=ports, nets=sorted(nets),
        locations={i.getName(): [i.getLocation(), i.getOrient(), i.getPlacementStatus()] for i in block.getInsts()},
        geometry=template_fingerprint(Path(state['def']).read_text())))
    odb.dbDatabase.destroy(db)
a, b = records
result = dict(scope='clean prefix identity; not final qualification',
    equal_fields={k: a[k] == b[k] for k in a},
    original_instances=len(a['cells']), clean_instances=len(b['cells']),
    changed_cells=sorted(k for k in a['cells'].keys() & b['cells'].keys() if a['cells'][k] != b['cells'][k]),
    changed_locations=sorted(k for k in a['locations'].keys() & b['locations'].keys() if a['locations'][k] != b['locations'][k]),
    sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
out = Path(__file__).with_name('clean_clock_prefix_identity_02.json')
with out.open('x') as stream:
    json.dump(result, stream, indent=2); stream.write('\n')
print(json.dumps({k: v for k, v in result.items() if k not in ('changed_cells','changed_locations','sha256')}, indent=2))

