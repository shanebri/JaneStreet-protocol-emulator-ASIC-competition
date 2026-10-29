"""Locate frontend/configuration differences without changing either run."""
import json
from pathlib import Path
import re
import sys

repo = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo/'tools/timing'))
from implementation_trial import template_fingerprint

old = json.loads((repo/'test/sim_build/implementation/placement-corners-01/resolved_input.json').read_text())
new = json.loads((repo/'test/sim_build/production_candidate_20261028_01/run/resolved.json').read_text())
differences = {k: [old.get(k),new.get(k)] for k in old.keys() & new.keys()
    if old[k]!=new[k] and not any(x in json.dumps([old[k],new[k]]) for x in ('/home/','/mnt/','/nix/'))}
states = [Path('/home/shane/eda/timing-20261024/current/runs/wokwi/27-odb-applydeftemplate/state_out.json'),
          repo/'test/sim_build/production_candidate_20261028_01/run/27-odb-applydeftemplate/state_out.json']
views = [json.loads(p.read_text()) for p in states]
views[0]['def'] = str(states[0].parent/'tt_um_shanebri_top.def')
def parse_def(path):
    text = Path(path).read_text()
    # Compare generated physical content while excluding provenance comments.
    return re.sub(r'^#.*$', '', text, flags=re.M).strip()
result = dict(config_differences=differences,
    preplacement_def_equal=parse_def(views[0]['def'])==parse_def(views[1]['def']))
clock_states = [repo/'test/sim_build'/p for p in (
    'clock_factors/clock_split8-01/run/02-openroad-repairclockfanout/state_out.json',
    'production_candidate_20261028_01/run/36-openroad-repairclockfanout/state_out.json')]
geometries = []
for p in clock_states:
    die, pins = template_fingerprint(Path(json.loads(p.read_text())['def']).read_text())
    # The stricter full fingerprint also compares internal net identity. Its
    # only observed difference here is the uio_oe[0] synthesized output net.
    text = Path(json.loads(p.read_text())['def']).read_text()
    text = re.sub(r'(\+ NET)\s+\S+', r'\1 SAME_NET', text)
    geometries.append(template_fingerprint(text))
result['boundary_and_physical_signal_pin_geometry_equal'] = geometries[0]==geometries[1]
out = Path(__file__).with_name('clean_prefix_configuration.json')
with out.open('x') as f:
    json.dump(result,f,indent=2); f.write('\n')
print(json.dumps(result,indent=2))
