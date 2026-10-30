"""Audit clock-buffer insertion and measure clock-tree topology in saved ODBs.

Run with OpenROAD's Python. Logical equivalence is limited to transparent,
non-inverting clock buffers; this does not replace routed LVS or signoff STA.
"""
import argparse
from collections import Counter, defaultdict, deque
import hashlib
import json
from pathlib import Path


def snapshot(block):
    cells, loads, clock_pins = {}, defaultdict(list), set()
    for inst in block.getInsts():
        pins = {}
        for pin in inst.getITerms():
            term = pin.getMTerm()
            if term.getSigType() in ('POWER', 'GROUND'):
                continue
            name = term.getName()
            net = pin.getNet()
            pins[name] = net.getName() if net is not None else None
            if term.getIoType() == 'INPUT' and net is not None:
                loads[net.getName()].append((inst.getName(), name))
            if name == 'CLK':
                clock_pins.add((inst.getName(), name))
        cells[inst.getName()] = (inst.getMaster().getName(), pins)
    ports = {p.getName(): p.getNet().getName() if p.getNet() is not None else None
             for p in block.getBTerms() if p.getSigType() not in ('POWER', 'GROUND')}
    nets = {n.getName() for n in block.getNets() if n.getSigType() not in ('POWER', 'GROUND')}
    return cells, ports, nets, loads, clock_pins


def topology(data):
    cells, ports, _, loads, clock_pins = data
    root = ports.get('clk')
    if root is None or not clock_pins:
        raise ValueError('Missing clock root or CLK sinks')
    queue = deque([(root, 0)])
    seen, reached, buffers, depth_hist, dummy_loads, antenna_loads = set(), set(), [], Counter(), [], []
    while queue:
        net, depth = queue.popleft()
        if net in seen:
            raise ValueError(f'Clock reconvergence or cycle at {net}')
        seen.add(net)
        for cell, pin in sorted(loads.get(net, [])):
            master, pins = cells[cell]
            if master.startswith('sg13cmos5l_buf_') and pin == 'A':
                output = pins['X']
                count = len(loads.get(output, [])) if output is not None else 0
                buffers.append(dict(instance=cell, master=master, fanout=count, depth=depth+1))
                if output is not None:
                    queue.append((output, depth+1))
            elif (cell, pin) in clock_pins:
                reached.add((cell, pin))
                depth_hist[depth] += 1
            elif (cell.startswith('clkload') and master.startswith('sg13cmos5l_inv_')
                    and pin == 'A' and not loads.get(pins.get('Y'), [])):
                # CTS uses unloaded inverters as explicit capacitance dummies.
                dummy_loads.append(dict(instance=cell, master=master, depth=depth))
            elif master == 'sg13cmos5l_antennanp' and pin == 'A' and set(pins) == {'A'}:
                # Real native antenna loads count toward output fanout above.
                antenna_loads.append(dict(instance=cell, master=master, depth=depth))
            else:
                raise ValueError(f'Unsupported non-clock load on clock tree: {cell}/{pin} ({master})')
    if reached != clock_pins:
        raise ValueError(f'{len(clock_pins-reached)} CLK sinks are not reached from clk')
    return dict(clock_sink_count=len(reached), clock_buffer_count=len(buffers),
                dummy_clock_load_count=len(dummy_loads), dummy_loads=dummy_loads,
                antenna_clock_load_count=len(antenna_loads), antenna_loads=antenna_loads,
                root_fanout=len(loads[root]),
                max_buffer_fanout=max((b['fanout'] for b in buffers), default=0),
                clock_buffer_outputs_above8=sum(b['fanout'] > 8 for b in buffers),
                sink_buffer_depth_histogram=dict(sorted(depth_hist.items())),
                clock_buffer_fanout_histogram=dict(sorted(Counter(b['fanout'] for b in buffers).items())),
                buffers=buffers)


def audit(before, after):
    old, old_ports, old_nets, _, _ = before
    new, new_ports, new_nets, _, _ = after
    if not old.keys() <= new.keys() or old_ports != new_ports or not old_nets <= new_nets:
        raise ValueError('Removed original instances/nets or changed top-level signal connections')
    inserted = sorted(new.keys()-old.keys())
    aliases = {}
    for name in inserted:
        master, pins = new[name]
        if (not name.startswith('clkbuf_fanoutfix_') or master != 'sg13cmos5l_buf_8'
                or set(pins) != {'A', 'X'} or None in pins.values()):
            raise ValueError(f'Unexpected inserted cell or pins: {name} {master} {pins}')
        if pins['X'] in aliases:
            raise ValueError('Multiple inserted buffer drivers')
        aliases[pins['X']] = pins['A']
    if new_nets-old_nets != aliases.keys():
        raise ValueError('Added nets differ from inserted clock-buffer outputs')

    def transparent(net):
        seen = set()
        while net in aliases:
            if net in seen:
                raise ValueError('Inserted clock-buffer cycle')
            seen.add(net)
            net = aliases[net]
        return net

    for name, (master, pins) in old.items():
        after_master, after_pins = new[name]
        if master != after_master or pins != {p: transparent(n) for p, n in after_pins.items()}:
            raise ValueError(f'Changed original master or logical signal connections: {name}')
    return dict(status='pass', original_instances=len(old), added_buffers=len(inserted),
                all_original_signal_connections_preserved=True,
                scope='ideal non-inverting clock-buffer insertion; power/ground excluded; not physical LVS')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--before', type=Path, help='CTS output before the matched repair/legalization step')
    p.add_argument('--odb', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    import odb
    # Keep both databases alive while their snapshots are populated.
    database = odb.dbDatabase.create()
    odb.read_db(database, str(a.odb))
    after = snapshot(database.getChip().getBlock())
    result = dict(topology=topology(after), input_sha256={str(a.odb): hashlib.sha256(a.odb.read_bytes()).hexdigest()})
    if a.before:
        original = odb.dbDatabase.create()
        odb.read_db(original, str(a.before))
        before = snapshot(original.getChip().getBlock())
        result['before_topology'] = topology(before)
        result['insertion_audit'] = audit(before, after)
        result['input_sha256'][str(a.before)] = hashlib.sha256(a.before.read_bytes()).hexdigest()
    result['runner_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with a.out.open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
    print('PASS: clock sinks', result['topology']['clock_sink_count'],
          'buffer outputs above 8', result['topology']['clock_buffer_outputs_above8'])


if __name__ == '__main__':
    main()
