"""Candidate-only local gate replication with exact connectivity audits.

The replicated gate uses the identical combinational library master and input
nets. Only a declared physical subset of its existing loads may move. Clock
topology and every original logical connection must remain equivalent.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from audit_clock_tree import snapshot
from audit_data_eco import audit
from audit_nor_trial import audit_models
from incremental_trial import incremental_script


ALLOWED = {"sg13cmos5l_nand3_1": ("Y", {"A", "B", "C"})}


def selected_loads(before, op, locations, dbu):
    cells, _, _, loads, clocks = before
    cell, output = op["target"].rsplit("/", 1)
    master, pins = cells[cell]
    if master != op["old"] or master not in ALLOWED or output != ALLOWED[master][0]:
        raise ValueError("Unsupported replica source/master/output")
    if set(pins) != ALLOWED[master][1] | {output}:
        raise ValueError("Replica source pin set differs from combinational contract")
    sinks = loads[pins[output]]
    chosen = sorted(sink for sink in sinks if locations[sink[0]][0] > op["x_min_um"]*dbu)
    if not chosen or len(chosen) == len(sinks) or len(chosen) > op["max_loads"]:
        raise ValueError("Replica must isolate a nonempty bounded proper subset")
    if any(sink in clocks for sink in sinks):
        raise ValueError("Replica cannot touch a clock sink")
    return cell, output, pins[output], chosen


def normalize_replicas(before, after, operations, locations, dbu):
    old, ports, nets, _, _ = before
    new, new_ports, new_nets, new_loads, new_clocks = after
    copies, aliases, details = set(), {}, []
    for op in operations:
        if op["kind"] != "clone":
            continue
        source, output, source_net, chosen = selected_loads(before, op, locations, dbu)
        name = op["name"]
        if name in old or name in copies or name not in new:
            raise ValueError("Replica identity missing, duplicated or preexisting")
        master, pins = new[name]
        if master != old[source][0] or set(pins) != set(old[source][1]):
            raise ValueError("Replica changed its gate function or pins")
        if any(pins[pin] != old[source][1][pin] for pin in ALLOWED[master][1]):
            raise ValueError("Replica input signal differs from original source")
        output_net = pins[output]
        if output_net in nets or output_net in aliases or output_net is None:
            raise ValueError("Replica output must be a new uniquely driven net")
        if sorted(new_loads[output_net]) != chosen:
            raise ValueError("Replica sink partition differs from declared physical subset")
        copies.add(name)
        aliases[output_net] = source_net
        details.append(dict(source=source, replica=name, master=master, loads=['/'.join(v) for v in chosen]))
    normalized_cells = {name:(master, {pin:aliases.get(net, net) for pin,net in pins.items()})
                        for name,(master,pins) in new.items() if name not in copies}
    normalized_loads = {}
    for net, sinks in new_loads.items():
        normalized_loads.setdefault(aliases.get(net, net), []).extend(sink for sink in sinks if sink[0] not in copies)
    normalized = (normalized_cells, new_ports, new_nets-set(aliases), normalized_loads, new_clocks)
    result = audit(before, normalized, [op for op in operations if op['kind'] != 'clone'])
    result.update(replicas=details, replica_input_functions_identical=True,
                  scope="Identical combinational masters/inputs and declared partitions; full physical signoff still required")
    return result


def render_script(operations):
    ordinary = [op for op in operations if op['kind'] != 'clone']
    text = incremental_script(ordinary)
    insertion = ''
    for op in operations:
        if op['kind'] != 'clone':
            continue
        master = op['old']
        if master not in ALLOWED:
            raise ValueError('Unsupported replica master')
        source, output = op['target'].rsplit('/', 1)
        insertion += f'''set source [$::block findInst {{{source}}}]
if {{$source eq "NULL" || [[$source getMaster] getName] ne "{master}"}} {{error "Replica source changed"}}
set output [[$source findITerm {{{output}}}] getNet]
set chosen {{}}
set sx 0; set sy 0
foreach pin [$output getITerms] {{
    if {{[[$pin getMTerm] getIoType] ne "INPUT"}} {{continue}}
    if {{[[$pin getMTerm] getName] eq "CLK"}} {{error "Replica targets clock"}}
    lassign [[$pin getInst] getLocation] px py
    if {{$px > {op['x_min_um']} * [$::block getDbUnitsPerMicron]}} {{
        lappend chosen $pin
        incr sx $px; incr sy $py
    }}
}}
if {{[llength $chosen]<1 || [llength $chosen]>{op['max_loads']}}} {{error "Replica partition changed"}}
set replica [odb::dbInst_create $::block [$source getMaster] {{{op['name']}}}]
set replica_net [odb::dbNet_create $::block {{{op['name']}_net}}]
$replica setOrient [$source getOrient]
$replica setLocation [expr {{$sx/[llength $chosen]}}] [expr {{$sy/[llength $chosen]}}]
$replica setPlacementStatus PLACED
foreach pin [$source getITerms] {{
    set pin_name [[$pin getMTerm] getName]
    if {{$pin_name eq "{output}"}} {{
        [$replica findITerm $pin_name] connect $replica_net
    }} else {{
        [$replica findITerm $pin_name] connect [$pin getNet]
    }}
}}
foreach pin $chosen {{$pin disconnect; $pin connect $replica_net}}
'''
    boundary = 'source $::env(SCRIPTS_DIR)/openroad/common/dpl.tcl\n'
    if text.count(boundary) != 1:
        raise ValueError('Native legalization boundary changed')
    return text.replace(boundary, insertion+boundary, 1)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('before', 'odb', 'recipe', 'pdk-model', 'out'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    import odb
    db1=odb.dbDatabase.create(); odb.read_db(db1,str(a.before))
    db2=odb.dbDatabase.create(); odb.read_db(db2,str(a.odb))
    block = db1.getChip().getBlock()
    operations = json.loads(a.recipe.read_text())
    model = a.pdk_model.read_text()
    for op in operations:
        if op['kind'] == 'size':
            audit_models(model, (op['old'], op['new']))
    if any(op['kind'] == 'buffer' for op in operations):
        body=re.search(r'\bmodule sg13cmos5l_buf_4\b(.*?)\bendmodule', model, re.S)[1].split('specify')[0]
        body=re.sub(r'//[^\n]*','',body)
        if 'buf(X,A);' not in re.sub(r'\s+','',body):
            raise ValueError('Pinned buffer model is not transparent')
    result = normalize_replicas(snapshot(block), snapshot(db2.getChip().getBlock()), operations,
                                {inst.getName():inst.getLocation() for inst in block.getInsts()}, block.getDbUnitsPerMicron())
    result['sha256'] = {str(v):hashlib.sha256(v.read_bytes()).hexdigest()
                        for v in (a.before, a.odb, a.recipe, a.pdk_model, Path(__file__))}
    with a.out.open('x') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    print('PASS: identical replica functions/inputs, exact declared load partition, unchanged data/clock behavior')


if __name__ == '__main__':
    main()
