"""Reject contacts between different signal-net wires in the serialized ODB.

This independent rectangle check covers default-width rectilinear signal wires,
via metal enclosures and patch metal. It does not replace pin connectivity,
spacing DRC, or GDS LVS. Unsupported geometry fails closed.
Run with OpenROAD's Python interpreter and the matching DEF.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re


def touches(a, b):
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def find_contacts(shapes, bucket_size=4000):
    """One witness per net pair/layer; include boundary-touching conductors."""
    buckets = defaultdict(list)
    witnesses = {}
    for index, (net, layer, box) in enumerate(shapes):
        seen = set()
        for x in range(box[0] // bucket_size, box[2] // bucket_size + 1):
            for y in range(box[1] // bucket_size, box[3] // bucket_size + 1):
                bucket = buckets[layer, x, y]
                for other in bucket:
                    if other in seen:
                        continue
                    seen.add(other)
                    onet, _, obox = shapes[other]
                    key = (*sorted((net, onet)), layer)
                    if net != onet and key not in witnesses and touches(box, obox):
                        witnesses[key] = dict(nets=list(key[:2]), layer=layer,
                                              rectangles=[list(box), list(obox)])
                bucket.append(index)
    return [witnesses[key] for key in sorted(witnesses)]


def wire_shapes(block, def_path):
    import odb
    text = Path(def_path).read_text()
    section = re.search(r'\bNETS\s+\d+\s*;(.*?)END NETS', text, re.S)[1]
    records = dict(re.findall(r'^\s*-\s+(\S+)\s+(.*?);', section, re.M | re.S))
    shapes = []
    routed = 0
    for net in block.getNets():
        if net.isSpecial() or not net.getWire():
            continue
        name = net.getName()
        routed += 1
        def add(layer, box):
            shapes.append((name, layer, tuple(box)))
        decoder = odb.dbWireDecoder()
        decoder.begin(net.getWire())
        layer, point, extension, rule = None, None, None, None
        patch_count = 0
        while True:
            op = decoder.next()
            if op == decoder.END_DECODE:
                break
            if op == decoder.PATH:
                layer, point, extension, rule = decoder.getLayer(), None, None, None
            elif op == decoder.RULE:
                rule = decoder.getRule()
            elif op in (decoder.JUNCTION, decoder.SHORT, decoder.VWIRE):
                raise ValueError('Unsupported wire opcode on ' + name)
            elif op in (decoder.POINT, decoder.POINT_EXT):
                values = decoder.getPoint_ext() if op == decoder.POINT_EXT else decoder.getPoint()
                current = tuple(values[:2])
                current_ext = values[2] if op == decoder.POINT_EXT else None
                if point is not None:
                    x1, y1 = point; x2, y2 = current
                    if x1 != x2 and y1 != y2:
                        raise ValueError('Non-rectilinear wire: ' + name)
                    wrong_way = ((layer.getDirection() == 'HORIZONTAL' and y1 != y2)
                                 or (layer.getDirection() == 'VERTICAL' and x1 != x2))
                    width = rule.getWidth() if rule else (layer.getWrongWayWidth() if wrong_way else layer.getWidth())
                    if width <= 0 or width % 2:
                        raise ValueError('Unsupported wire width: ' + name)
                    half = width // 2
                    start = half if extension is None else extension
                    end = half if current_ext is None else current_ext
                    if y1 == y2:
                        lo, hi = (start, end) if x1 <= x2 else (end, start)
                        box = (min(x1,x2)-lo, y1-half, max(x1,x2)+hi, y1+half)
                    else:
                        lo, hi = (start, end) if y1 <= y2 else (end, start)
                        box = (x1-half, min(y1,y2)-lo, x1+half, max(y1,y2)+hi)
                    add(layer.getName(), box)
                point, extension = current, current_ext
            elif op in (decoder.TECH_VIA, decoder.VIA):
                via = decoder.getTechVia() if op == decoder.TECH_VIA else decoder.getVia()
                for box in via.getBoxes():
                    metal = box.getTechLayer()
                    if metal.getType() == 'ROUTING':
                        add(metal.getName(), (box.xMin()+point[0], box.yMin()+point[1],
                                             box.xMax()+point[0], box.yMax()+point[1]))
                # Subsequent path segments are on the other side of the via.
                layer = via.getTopLayer() if layer == via.getBottomLayer() else via.getBottomLayer()
            elif op == decoder.RECT:
                patch_count += 1
            elif op not in (decoder.ITERM, decoder.BTERM):
                raise ValueError('Unknown wire opcode on ' + name)
        record = records[name]
        patches = re.findall(r'(?:NEW|ROUTED|FIXED)\s+(\w+)\s+(?:TAPER\s+)?\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+RECT\s+\(\s*(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s*\)', record)
        if len(patches) != patch_count:
            raise ValueError('ODB/DEF patch mismatch: ' + name)
        for metal, x, y, a, b, c, d in patches:
            x,y,a,b,c,d = map(int,(x,y,a,b,c,d))
            add(metal,(x+a,y+b,x+c,y+d))
    return shapes, routed


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ('odb','def','out'):
        p.add_argument('--'+arg, type=Path, required=True)
    a = p.parse_args()
    import odb
    db = odb.dbDatabase.create(); odb.read_db(db,str(a.odb))
    block = db.getChip().getBlock()
    shapes, nets = wire_shapes(block, getattr(a,'def'))
    contacts = find_contacts(shapes)
    result = dict(status='fail' if contacts else 'pass', routed_nets=nets,
                  metal_rectangles=len(shapes), dbu_per_micron=block.getDbUnitsPerMicron(),
                  scope=__doc__, contacts=contacts,
                  sha256={str(path):hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in (a.odb,getattr(a,'def'),Path(__file__))})
    with a.out.open('x') as f: json.dump(result,f,indent=2); f.write('\n')
    print('Cross-net signal wire contact groups:',len(contacts),flush=True)
    if contacts: raise SystemExit(1)


if __name__ == '__main__': main()
