"""Compare serialized signal routing and placement; diagnostic, not LVS."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from implementation_trial import template_fingerprint


def read_def(path):
    text = path.read_text()
    section = re.search(r'\bNETS\s+\d+\s*;(.*?)END NETS', text, re.S)[1]
    routes = {}
    for name, record in re.findall(r'^\s*-\s+(\S+)\s+(.*?);', section, re.M|re.S):
        match = re.search(r'\+\s+(?:ROUTED|FIXED)\b(.*)', record, re.S)
        routes[name] = re.sub(r'\s+', ' ', match[1]).strip() if match else None
    section = re.search(r'\bCOMPONENTS\s+\d+\s*;(.*?)END COMPONENTS', text, re.S)[1]
    cells = {}
    for name, record in re.findall(r'^\s*-\s+(\S+)\s+(.*?);', section, re.M|re.S):
        match = re.search(r'\+\s+(PLACED|FIXED)\s*\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+(\S+)', record)
        cells[name] = (record.split()[0], match.groups() if match else None)
    return routes, cells, template_fingerprint(text)


def compare(before, after):
    a, ac, ap = read_def(before)
    b, bc, bp = read_def(after)
    if ap != bp:
        raise ValueError('Die boundary or signal pins changed')
    changed = sorted(n for n in a.keys() & b.keys() if a[n] != b[n])
    return dict(scope='DEF serialization comparison, not physical equivalence/LVS',
        original_signal_nets=len(a), unchanged_signal_routes=sum(a[n] == b.get(n) for n in a),
        changed_signal_routes=changed, new_signal_nets=sorted(b.keys()-a.keys()),
        missing_signal_nets=sorted(a.keys()-b.keys()),
        changed_clock_routes=[n for n in changed if n=='clk' or n.startswith('clknet')],
        moved_or_changed_original_cells=sorted(n for n in ac.keys() & bc.keys() if ac[n]!=bc[n]),
        removed_original_cells=sorted(ac.keys()-bc.keys()), boundary_and_signal_pins_unchanged=True,
        sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (before, after)})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('before','after','out'):
        p.add_argument('--'+key, type=Path, required=True)
    a=p.parse_args()
    result=compare(a.before,a.after)
    with a.out.open('x') as f:
        json.dump(result,f,indent=2); f.write('\n')
    print('Unchanged signal routes:',result['unchanged_signal_routes'],'of',result['original_signal_nets'])
    print('Changed clock routes:',len(result['changed_clock_routes']))


if __name__=='__main__': main()
