"""Candidate-local transparent-delay repair with exact connectivity auditing.

The existing audit remains authoritative for signal/clock identity and sink
partitions. This extension additionally verifies each declared buffer master and
its pinned functional model before normalizing transparent cells for that audit.
"""
import argparse
import json
from pathlib import Path
import re

from audit_clock_tree import snapshot
from audit_data_eco import audit
from audit_nor_trial import audit_models
from incremental_trial import incremental_script
from refactor_trial import sha


ALLOWED_BUFFERS = {'sg13cmos5l_buf_4', 'sg13cmos5l_dlygate4sd1_1'}


def buffer_cell(op):
    master = op.get('buffer_cell', 'sg13cmos5l_buf_4')
    if master not in ALLOWED_BUFFERS:
        raise ValueError('Unsupported transparent repair cell: ' + master)
    return master


def render_script(operations):
    text = incremental_script(operations)
    for index, op in enumerate(operations):
        if op['kind'] != 'buffer':
            continue
        master = buffer_cell(op)
        original = ('insert_buffer -buffer_cell sg13cmos5l_buf_4 -load_pins $chunk '
                    '-location $location \\\n        -buffer_name eco_data_' + str(index) + '_$first')
        if text.count(original) != 1:
            raise ValueError('Unexpected buffer insertion template')
        text = text.replace(original, original.replace('sg13cmos5l_buf_4', master), 1)
    return text


def audit_transparent(before, after, operations):
    old, ports, _, _, _ = before
    roots = {}
    for op in operations:
        if op['kind'] != 'buffer':
            continue
        target = op['target']
        if '/' in target:
            cell, pin = target.split('/')
            net = old[cell][1][pin]
        else:
            net = ports[target]
        if net in roots:
            raise ValueError('Duplicate buffer source')
        roots[net] = buffer_cell(op)
    new, new_ports, new_nets, new_loads, new_clocks = after
    normalized = dict(new)
    masters = {}
    for name in new.keys() - old.keys():
        master, pins = new[name]
        if set(pins) != {'A', 'X'} or master != roots.get(pins.get('A')):
            raise ValueError('Inserted buffer master/function differs from declared source: ' + name)
        masters[name] = master
        normalized[name] = ('sg13cmos5l_buf_4', pins)
    result = audit(before, (normalized, new_ports, new_nets, new_loads, new_clocks), operations)
    result['declared_transparent_masters'] = masters
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('before', 'odb', 'recipe', 'pdk-model', 'out'):
        p.add_argument('--' + key, type=Path, required=True)
    a = p.parse_args()
    import odb
    db1 = odb.dbDatabase.create(); odb.read_db(db1, str(a.before))
    db2 = odb.dbDatabase.create(); odb.read_db(db2, str(a.odb))
    ops = json.loads(a.recipe.read_text())
    model = a.pdk_model.read_text()
    for master in {buffer_cell(op) for op in ops if op['kind'] == 'buffer'}:
        body = re.search(r'\bmodule ' + re.escape(master) + r'\b(.*?)\bendmodule', model, re.S)
        if not body:
            raise ValueError('Missing pinned transparent cell model')
        function = re.sub(r'//[^\n]*', '', body[1].split('specify')[0])
        if 'buf(X,A);' not in re.sub(r'\s+', '', function):
            raise ValueError('Delay/buffer model is not transparent: ' + master)
    for op in ops:
        if op['kind'] == 'size':
            audit_models(model, (op['old'], op['new']))
    result = audit_transparent(snapshot(db1.getChip().getBlock()), snapshot(db2.getChip().getBlock()), ops)
    result['sha256'] = {str(path): sha(path) for path in (a.before, a.odb, a.recipe, a.pdk_model, Path(__file__))}
    with a.out.open('x') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    print('PASS: exact transparent masters, sink partitions, original connectivity and clock topology')


if __name__ == '__main__':
    main()
