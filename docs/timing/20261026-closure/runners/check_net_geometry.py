"""Diagnostic conductor-contact graph for one routed OpenDB signal net.

Run with openroad -python. This is independent of RCX resistance connectivity,
but does not replace full DRC/LVS. Assumes rectilinear default-width signal wire.
"""
import argparse
import json
import re
from pathlib import Path


def touches(a, b):
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--odb', type=Path, required=True)
    parser.add_argument('--net', default='uio_in[2]')
    parser.add_argument('--def', dest='def_path', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    import odb
    database = odb.dbDatabase.create()
    odb.read_db(database, str(args.odb))
    block = database.getChip().getBlock()
    net = block.findNet(args.net)
    if not net or not net.getWire():
        raise ValueError('Routed net missing')
    if net.getNonDefaultRule():
        raise ValueError('Diagnostic requires explicit extension for NDR widths')
    shapes = []
    def add(layer, rect, owner, group=None):
        shapes.append({'layer': layer, 'rect': list(rect), 'owner': owner, 'group': group})
    def box_rect(box):
        return box.xMin(), box.yMin(), box.xMax(), box.yMax()
    decoder = odb.dbWireDecoder()
    decoder.begin(net.getWire())
    layer, previous, point, extension = None, None, None, None
    via_count = 0
    patch_count = 0
    while True:
        op = decoder.next()
        if op == decoder.END_DECODE:
            break
        if op == decoder.PATH:
            layer, previous, point = decoder.getLayer(), None, None
        elif op in (decoder.JUNCTION, decoder.SHORT, decoder.VWIRE, decoder.RULE):
            raise ValueError('Unsupported wire opcode; extend diagnostic rather than assume continuity')
        elif op in (decoder.POINT, decoder.POINT_EXT):
            values = decoder.getPoint_ext() if op == decoder.POINT_EXT else decoder.getPoint()
            current = tuple(values[:2])
            half = layer.getWidth()//2
            current_ext = values[2] if op == decoder.POINT_EXT else half
            if previous is not None:
                x1, y1 = previous; x2, y2 = current
                if x1 != x2 and y1 != y2:
                    raise ValueError('Non-rectilinear wire')
                if y1 == y2:
                    lo, hi = (extension, current_ext) if x1 <= x2 else (current_ext, extension)
                    rect = (min(x1,x2)-lo, y1-half, max(x1,x2)+hi, y1+half)
                else:
                    lo, hi = (extension, current_ext) if y1 <= y2 else (current_ext, extension)
                    rect = (x1-half, min(y1,y2)-lo, x1+half, max(y1,y2)+hi)
                add(layer.getName(), rect, 'wire')
            previous, point, extension = current, current, current_ext
        elif op in (decoder.TECH_VIA, decoder.VIA):
            via = decoder.getTechVia() if op == decoder.TECH_VIA else decoder.getVia()
            group = f'via_{via_count}'; via_count += 1
            for box in via.getBoxes():
                metal = box.getTechLayer()
                if metal.getType() != 'ROUTING':
                    continue
                x1,y1,x2,y2 = box_rect(box)
                add(metal.getName(), (x1+point[0], y1+point[1], x2+point[0], y2+point[1]), group, group)
        elif op == decoder.RECT:
            # The pinned SWIG decoder lacks output typemaps for getRect.
            # Read its exact offsets from the corresponding DEF instead.
            patch_count += 1
    def_text = args.def_path.read_text()
    nets = re.search(r'\bNETS\s+\d+\s*;(.*?)END NETS', def_text, re.S)[1]
    record = re.search(r'^\s*-\s+'+re.escape(args.net)+r'\s+(.*?);', nets, re.M|re.S)[1]
    patches = re.findall(r'(?:NEW|ROUTED)\s+(\w+)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+RECT\s+\(\s*(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s*\)', record)
    if len(patches) != patch_count:
        raise ValueError('DEF patch rectangles do not match the OpenDB wire')
    for layer_name, x, y, a, b, c, d in patches:
        x,y,a,b,c,d = map(int, (x,y,a,b,c,d))
        add(layer_name, (x+a,y+b,x+c,y+d), 'patch')
    for term in net.getITerms():
        owner = term.getInst().getName()+'/'+term.getMTerm().getName()
        instance = term.getInst()
        ox, oy = instance.getOrigin()
        orient = instance.getOrient()
        rotations = {'R0': lambda x,y: (x,y), 'R90': lambda x,y: (-y,x),
                     'R180': lambda x,y: (-x,-y), 'R270': lambda x,y: (y,-x),
                     'MX': lambda x,y: (x,-y), 'MY': lambda x,y: (-x,y),
                     'MXR90': lambda x,y: (y,x), 'MYR90': lambda x,y: (-y,-x)}
        if orient not in rotations:
            raise ValueError(f'Unsupported instance orientation {orient}')
        for pin in term.getMTerm().getMPins():
            for box in pin.getGeometry():
                layer = box.getTechLayer()
                if not layer or layer.getType() != 'ROUTING':
                    continue
                x1,y1,x2,y2 = box_rect(box)
                points = [rotations[orient](x,y) for x,y in ((x1,y1),(x1,y2),(x2,y1),(x2,y2))]
                rect = (min(p[0] for p in points)+ox, min(p[1] for p in points)+oy,
                        max(p[0] for p in points)+ox, max(p[1] for p in points)+oy)
                add(layer.getName(), rect, owner, owner)
    for term in net.getBTerms():
        for pin in term.getBPins():
            for box in pin.getBoxes():
                add(box.getTechLayer().getName(), box_rect(box), 'port:'+term.getName(), 'port:'+term.getName())
    parent = list(range(len(shapes)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    def union(i,j):
        parent[find(i)] = find(j)
    for i,a in enumerate(shapes):
        for j,b in enumerate(shapes[:i]):
            if ((a['group'] is not None and a['group'] == b['group'])
                or (a['layer'] == b['layer'] and touches(a['rect'], b['rect']))):
                union(i,j)
    components = {}
    for i, shape in enumerate(shapes):
        components.setdefault(str(find(i)), []).append(shape)
    pins = {s['owner']: find(i) for i,s in enumerate(shapes) if s['group']
            and not s['group'].startswith('via_')}
    root = pins['port:'+args.net]
    result = {'net': args.net, 'odb': str(args.odb), 'dbu_per_micron': block.getDbUnitsPerMicron(),
              'components': components, 'pin_components': pins,
              'pins_disconnected_from_port': [p for p,c in pins.items() if c != root],
              'scope': 'default-width rectangle contact diagnostic; full LVS remains required'}
    with args.out.open('x') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    print('Components:', len(components), 'Disconnected pins:', result['pins_disconnected_from_port'])


if __name__ == '__main__':
    main()
