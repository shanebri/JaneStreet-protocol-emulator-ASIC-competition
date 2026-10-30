"""Tie the clean rejected implementation to its exact already-replayed route."""
import json
import hashlib
from pathlib import Path
import re
import sys

repo=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(repo/'tools/timing'))
from closure_trial import sha
from closure_collect import nominal_view
from check_signoff import check_metrics, find_state
from collect_implementation import validate_replay, selected_metrics

clean=repo/'test/sim_build/production_candidate_20261028_02/run'
reference=repo/'test/sim_build/data_incremental_tail_20261028/incremental_last_fanout-01'
states=[find_state(clean),find_state(reference/'run')]
data=[json.loads(p.read_text()) for p in states]
views={}
for key in ('odb','def','nl','sdc','spef'):
    paths=[nominal_view(s[key]) if key=='spef' else Path(s[key]) for s in data]
    hashes=[sha(p) for p in paths]
    if key=='spef':
        normalized=[re.sub(rb'^\*DATE .*\n',b'',p.read_bytes(),flags=re.M) for p in paths]
        if normalized[0]!=normalized[1]: raise ValueError('Clean SPEF electrical content differs')
        views[key]=dict(paths=list(map(str,paths)),sha256=hashes,
            difference='Only the SPEF *DATE line may differ',
            electrical_content_sha256=hashlib.sha256(normalized[0]).hexdigest())
    else:
        if hashes[0]!=hashes[1]: raise ValueError('Clean view differs: '+key)
        views[key]=dict(paths=list(map(str,paths)),sha256=hashes[0])
if selected_metrics(data[0]['metrics'])!=selected_metrics(data[1]['metrics']):
    raise ValueError('Clean timing/electrical metrics differ')
replay=json.loads((reference/'replay/manifest.json').read_text())
validate_replay(replay,selected_metrics(data[0]['metrics']))
for path,expected in replay['sha256'].items():
    if sha(Path(path))!=expected: raise ValueError('Replay input changed')
for session in replay['sessions']:
    if (reference/f"replay/{session['corner']}-{session['mode']}/coverage.rpt").read_text().strip():
        raise ValueError('Incomplete replay coverage')
result=dict(status='pass',scope='clean reproduction of a strict-rejected route; not production closure',
    views=views,metrics=selected_metrics(data[0]['metrics']),strict_failures=check_metrics(data[0]['metrics']),
    reused_replay=str(reference/'replay/manifest.json'),
    replay_reuse_basis='NL/SDC/ODB/DEF byte-identical; SPEF differs only in DATE; same verified six libraries; nine reference sessions validated. This is a rejected-route reproduction, not final qualification.',
    replay_manifest_sha256=sha(reference/'replay/manifest.json'),
    sha256={str(p):sha(p) for p in [*states,Path(__file__),clean/'resolved.json']})
with Path(__file__).with_name('clean_rejected_route_identity.json').open('x') as f:
    json.dump(result,f,indent=2);f.write('\n')
print('PASS: clean physical views and all selected metrics exactly match the fully replayed rejected screen')
