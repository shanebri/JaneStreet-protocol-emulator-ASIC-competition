"""Expose local setup/hold budgets at the repaired architectural ISR registers.

Uses the unmodified native path reports, including the qualified CI
archive. This diagnostic supplements, and never changes, production acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

from check_signoff import REQUIRED_CORNERS, find_state
from diagnose_cones import paths
from refactor_trial import PARENT_SHA256, REPO


def sha(data):
    return hashlib.sha256(data).hexdigest()


def register_map(netlist):
    result = {}
    for cell, body in re.findall(r'\bsg13cmos5l_dfrbpq_1\s+(\S+)\s*\((.*?)\);', netlist, re.S):
        q = re.search(r'\.Q\(([^)]+)\)', body)
        if not q:
            continue
        name = q[1].strip().lstrip('\\')
        if name in result:
            raise ValueError('Ambiguous architectural register: '+name)
        result[name] = cell
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    (a.out/'runner.py').write_bytes(Path(__file__).read_bytes())
    roots = dict(hold=REPO/'test/sim_build/control_refactor_hold_production_20261030_01/run',
                 combined=REPO/'test/sim_build/control_refactor_combined_production_20261031_01/run')
    archive = REPO/'test/sim_build/github_analysis_40938542430/logs.zip'
    result = dict(status='running', scope='Local endpoint diagnostics; required worst-corner gates remain unchanged',
                  sources={}, comparisons={})
    with zipfile.ZipFile(archive) as z:
        for label in ('qualified_baseline', 'hold', 'combined'):
            if label == 'qualified_baseline':
                prefix = 'runs/wokwi/69-openroad-stapostpnr/'
                state_bytes = z.read(prefix+'state_out.json')
                if sha(state_bytes) != PARENT_SHA256:
                    raise ValueError('CI archive does not match the qualified baseline state')
                state = json.loads(state_bytes)
                key = 'runs/wokwi/'+state['nl'].split('/runs/wokwi/', 1)[1]
                netlist = z.read(key)
                reader = lambda corner, delay: z.read(prefix+corner+'/'+delay+'.rpt')
            else:
                state_path = find_state(roots[label])
                state_bytes = state_path.read_bytes()
                state = json.loads(state_bytes)
                netlist = Path(state['nl']).read_bytes()
                reader = lambda corner, delay: (state_path.parent/corner/(delay+'.rpt')).read_bytes()
            mapping = register_map(netlist.decode())
            source = dict(state_sha256=sha(state_bytes), netlist_sha256=sha(netlist),
                          report_sha256={}, registers={})
            for bit in (3, 6, 7):
                name = f'pio.engines[1].core.isr[{bit}]'
                source['registers'][name] = dict(cell=mapping[name], corners={})
            for corner in REQUIRED_CORNERS:
                for delay, analysis in (('max', 'setup'), ('min', 'hold')):
                    data = reader(corner, delay)
                    source['report_sha256'][corner+'/'+delay+'.rpt'] = sha(data)
                    records = paths(data.decode())
                    for name, reg in source['registers'].items():
                        cell = reg['cell']
                        selected = [row for row in records if row['endpoint'] == cell
                                    and cell+'/D (' in row['text'].split('data arrival time')[0]]
                        if not selected:
                            raise ValueError(f'Missing native data-pin path: {label} {corner} {name} {analysis}')
                        worst = min(selected, key=lambda row: row['slack'])
                        reg['corners'].setdefault(corner, {})[analysis] = worst['slack']
                        index = name.rsplit('[', 1)[1][:-1]
                        (a.out/f'{label}-{corner}-isr{index}-{delay}.rpt').write_text(worst['text'])
            result['sources'][label] = source
    for parent, candidate in (('qualified_baseline', 'hold'), ('hold', 'combined')):
        rows = {}
        for name, reg in result['sources'][candidate]['registers'].items():
            rows[name] = {corner: {analysis: dict(
                parent_ns=result['sources'][parent]['registers'][name]['corners'][corner][analysis],
                candidate_ns=reg['corners'][corner][analysis],
                consumed_ns=result['sources'][parent]['registers'][name]['corners'][corner][analysis]-reg['corners'][corner][analysis])
                for analysis in ('setup', 'hold')} for corner in REQUIRED_CORNERS}
        result['comparisons'][candidate+'_vs_'+parent] = rows
    result['status'] = 'complete'
    with (a.out/'manifest.json').open('x') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    print('Local endpoint report extraction complete:', a.out)
    for comparison, rows in result['comparisons'].items():
        for name, corners in rows.items():
            print(comparison, name, {c: {k: v['consumed_ns'] for k,v in x.items()} for c,x in corners.items()})


if __name__ == '__main__':
    main()
