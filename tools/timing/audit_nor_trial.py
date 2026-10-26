"""Fail closed unless exported trial netlists differ only by the intended NOR size.

This checks connectivity and the PDK's two NOR functional model bodies. It is
not a timing proof or a substitute for final routed gate-level verification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re


INSTANCE = re.compile(r'^\s*(sg13cmos5l_\w+)\s+(\S+)\s*\((.*?)\);', re.M | re.S)
PORT = re.compile(r'\.(\w+)\s*\(([^()]*)\)')


def topology(text):
    instances = {}
    for match in INSTANCE.finditer(text):
        master, name, body = match.groups()
        ports = PORT.findall(body)
        if not ports or PORT.sub('', body).replace(',', '').strip():
            raise ValueError(f'Unsupported connection syntax at {name}')
        if name in instances or len(dict(ports)) != len(ports):
            raise ValueError(f'Duplicate instance or port at {name}')
        instances[name] = (master, {pin: re.sub(r'\s+', '', net) for pin, net in ports})
    if not instances:
        raise ValueError('No PDK instances parsed')
    remainder = re.sub(r'\s+', '', INSTANCE.sub('', text))
    return instances, remainder


def audit(control, candidate):
    before, before_other = topology(control)
    after, after_other = topology(candidate)
    if before_other != after_other or before.keys() != after.keys():
        raise ValueError('Non-instance text or instance set changed')
    if '_23246_' not in before:
        raise ValueError('Measured NOR missing')
    changes = [name for name in before if before[name] != after[name]]
    if changes != ['_23246_']:
        raise ValueError(f'Expected exactly the terminal NOR change; found {changes}')
    old, old_pins = before['_23246_']
    new, new_pins = after['_23246_']
    if (old, new) != ('sg13cmos5l_nor4_1', 'sg13cmos5l_nor4_2') or old_pins != new_pins:
        raise ValueError('Unexpected NOR master or changed connections')
    return {'instance_count': len(before), 'changed_instance': '_23246_',
            'before': old, 'after': new, 'connections': old_pins}


def audit_models(text):
    bodies = []
    for master in ('sg13cmos5l_nor4_1', 'sg13cmos5l_nor4_2'):
        match = re.search(r'\bmodule\s+' + master + r'\b(.*?)\bendmodule', text, re.S)
        if not match:
            raise ValueError(f'Missing PDK model {master}')
        body = re.sub(r'//[^\n]*', '', match[1].split('specify', 1)[0])
        bodies.append(re.sub(r'\s+', '', body))
    if bodies[0] != bodies[1]:
        raise ValueError('NOR functional model bodies differ')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--pdk-model', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.control.read_text(), args.candidate.read_text())
    audit_models(args.pdk_model.read_text())
    result.update(status='pass', pdk_functional_bodies_identical=True,
                  sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in (args.control, args.candidate, args.pdk_model)})
    with args.out.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(f'PASS: {result["instance_count"]} instances audited; only _23246_ drive strength differs')


if __name__ == '__main__':
    main()
