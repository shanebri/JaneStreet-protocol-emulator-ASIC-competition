"""Resolve an ECO by local connectivity, never by generated instance numbers.

OpenROAD Python entrypoint. Fingerprints include cell functions/strengths, pin
names, connectivity, and boundary port names. Internal instance/net names and
placement are deliberately excluded. A changed or ambiguous cone fails closed.
This identity check does not replace the transformation audit or final LVS.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

from audit_clock_tree import snapshot


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def fingerprints(data, rounds=8):
    cells, ports, nets, _, _ = data
    port_names = defaultdict(list)
    for name, net in ports.items():
        if net is not None:
            port_names[net].append(name)
    adjacency = defaultdict(list)
    labels = {('net', net): digest(['net', sorted(port_names[net])]) for net in nets}
    for name, (master, pins) in cells.items():
        node = ('cell', name)
        labels[node] = digest(['cell', master, sorted(pins)])
        for pin, net in pins.items():
            if net is not None:
                other = ('net', net)
                adjacency[node].append((pin, other))
                adjacency[other].append((pin, node))
    history = [labels]
    for _ in range(rounds):
        labels = {node: digest([value, sorted((pin, labels[other]) for pin, other in adjacency[node])])
                  for node, value in labels.items()}
        history.append(labels)
    return history


def make_contract(data, operations):
    history = fingerprints(data)
    counts = []
    for labels in history:
        by_hash = defaultdict(list)
        for (kind, name), value in labels.items():
            if kind == 'cell':
                by_hash[value].append(name)
        counts.append(by_hash)
    entries = []
    for op in operations:
        entry = dict(operation=op)
        target = op.get('instance', op.get('target'))
        if op.get('old') is None:
            if target not in data[1]:
                raise ValueError('Missing boundary target: '+target)
            entry['port'] = target
        else:
            name = target.split('/')[0]
            if data[0][name][0] != op['old']:
                raise ValueError('Unexpected reference master: '+name)
            # Require four rounds even if a shallow neighborhood is unique.
            radius = next((r for r in range(4, len(history))
                           if len(counts[r][history[r][('cell', name)]]) == 1), None)
            if radius is None:
                raise ValueError('Structurally ambiguous target: '+name)
            entry.update(rounds=radius, fingerprint=history[radius][('cell', name)], reference_name=name)
        entries.append(entry)
    return dict(schema=1, identity='bidirectional pin-labelled graph; internal names excluded', entries=entries)


def resolve(data, contract):
    if contract.get('schema') != 1:
        raise ValueError('Unknown target contract schema')
    history = fingerprints(data, max((v.get('rounds', 0) for v in contract['entries']), default=0))
    resolved = []
    for entry in contract['entries']:
        op = dict(entry['operation'])
        if 'port' in entry:
            if entry['port'] not in data[1]:
                raise ValueError('Missing boundary port')
        else:
            matches = [name for (kind, name), value in history[entry['rounds']].items()
                       if kind == 'cell' and value == entry['fingerprint']]
            if len(matches) != 1:
                raise ValueError(f"Target {entry['reference_name']} has {len(matches)} structural matches")
            name = matches[0]
            if data[0][name][0] != op['old']:
                raise ValueError('Resolved master mismatch')
            if 'instance' in op:
                op['instance'] = name
            else:
                op['target'] = name+'/'+op['target'].split('/')[1]
        resolved.append(op)
    return resolved


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--odb', type=Path, required=True)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--recipe', type=Path, help='Create a reference contract')
    group.add_argument('--contract', type=Path, help='Resolve against this build')
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    import odb
    db = odb.dbDatabase.create(); odb.read_db(db, str(a.odb))
    data = snapshot(db.getChip().getBlock())
    if a.recipe:
        operations = json.loads(a.recipe.read_text())
        result = make_contract(data, operations)
        if resolve(data, result) != operations:
            raise ValueError('Reference self-resolution failed')
        result['reference_odb_sha256'] = hashlib.sha256(a.odb.read_bytes()).hexdigest()
        result['recipe_sha256'] = hashlib.sha256(a.recipe.read_bytes()).hexdigest()
    else:
        result = resolve(data, json.loads(a.contract.read_text()))
    with a.out.open('x') as f:
        json.dump(result, f, indent=2); f.write('\n')
    print('PASS: structural target identity verified')


if __name__ == '__main__':
    main()
