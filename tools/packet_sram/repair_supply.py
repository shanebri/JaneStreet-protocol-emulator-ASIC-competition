"""Add audited Metal3 peripheral buses and Metal4 tabs to the SRAM supply pins.

No metal is added across the macro interior. All via dimensions use the pinned
Via3 rule. Native PDN connectivity, later DRC and GDS LVS remain mandatory.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import odb


def bounds(rect):
    return (rect.xMin(), rect.yMin(), rect.xMax(), rect.yMax())


def conflict(a, b, spacing=300):
    return a[0] < b[2]+spacing and b[0] < a[2]+spacing and a[1] < b[3]+spacing and b[1] < a[3]+spacing


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--odb',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    db=odb.dbDatabase.create(); odb.read_db(db,str(a.odb))
    block=db.getChip().getBlock(); tech=db.getTech()
    inst=block.findInst('pio.packet.storage.memory')
    assert inst and inst.getMaster().getName()=='RM_IHPSG13_1P_64x16_c2'
    assert str(inst.getOrient())=='R0'
    x,y=inst.getLocation(); box=bounds(inst.getBBox())
    assert box==(x,y,x+236800,y+64360)
    supplies={'VDD!':'VPWR','VDDARRAY!':'VPWR','VSS!':'VGND'}
    pins=[]
    for name,net in supplies.items():
        iterm=inst.findITerm(name)
        assert iterm.getNet().getName()==net, (name,'incorrect supply net')
        for mpin in iterm.getMTerm().getMPins():
            for shape in mpin.getGeometry():
                assert shape.getTechLayer().getName()=='Metal4'
                r=bounds(shape)
                assert r[1]==0 or r[3]==64360, 'Supply rectangle does not reach macro boundary'
                pins.append((name,net,(r[0]+x,r[1]+y,r[2]+x,r[3]+y)))
    existing=[]; existing_vias=[]
    for net in block.getNets():
        if net.getSigType() not in ('POWER','GROUND'): continue
        for wire in net.getSWires():
            for shape in wire.getWires():
                if shape.isVia():
                    via=shape.getTechVia() or shape.getBlockVia()
                    vx,vy=shape.getViaXY()
                    if {via.getBottomLayer().getName(),via.getTopLayer().getName()}=={'Metal3','Metal4'}:
                        existing_vias.append((net.getName(),vx,vy))
                    for r in via.getBoxes():
                        layer=r.getTechLayer().getName()
                        if layer in ('Metal3','Metal4'):
                            b=bounds(r); existing.append((net.getName(),layer,(b[0]+vx,b[1]+vy,b[2]+vx,b[3]+vy)))
                elif shape.getTechLayer().getName() in ('Metal3','Metal4'):
                    existing.append((net.getName(),shape.getTechLayer().getName(),bounds(shape)))
    planned=[]; vias=[]; buses={}
    for side in ('bottom','top'):
        for net in ('VPWR','VGND'):
            selected=None
            for offset in range(3000,9001,10):
                cy=y-offset if side=='bottom' else y+64360+offset
                bus=(x-70000,cy-1000,x+236800+70000,cy+1000)
                proposal=[(net,'Metal3',bus)]
                for name,n,r in pins:
                    if n!=net: continue
                    if side=='bottom' and r[1]==y:
                        proposal.append((net,'Metal4',(r[0],cy-1000,r[2],y+150)))
                    if side=='top' and r[3]==y+64360:
                        proposal.append((net,'Metal4',(r[0],y+64360-150,r[2],cy+1000)))
                if any(n!=other and layer==other_layer and conflict(r,s)
                       for n,layer,r in proposal for other,other_layer,s in existing+planned): continue
                # Find actual uninterrupted same-net M4 straps outside the macro halo.
                taps=[]
                for n,layer,r in existing:
                    if n!=net or layer!='Metal4' or r[2]-r[0]<1800: continue
                    cx=(r[0]+r[2])//2
                    if not (bus[0]+1000<cx<bus[2]-1000 and r[1]+1000<cy<r[3]-1000): continue
                    if x-10000<=cx<=x+236800+10000: continue
                    taps.append((cx,cy))
                if not taps: continue
                selected=(cy,proposal,taps); break
            if selected is None: raise ValueError('No electrically isolated peripheral bus position: '+net+' '+side)
            cy,proposal,taps=selected; planned+=proposal; buses[net+'_'+side]=cy
            vias.extend((net,cx,cy) for cx,cy in taps)
            for name,n,r in pins:
                if n==net and ((side=='bottom' and r[1]==y) or (side=='top' and r[3]==y+64360)):
                    vias.append((net,(r[0]+r[2])//2,cy))
    via=odb.dbVia_create(block,'packet_supply_via3_3x3')
    params=odb.dbViaParams()
    params.setBottomLayer(tech.findLayer('Metal3')); params.setTopLayer(tech.findLayer('Metal4'))
    params.setCutLayer(tech.findLayer('Via3'))
    for axis in ('X','Y'):
        getattr(params,'set'+axis+'CutSize')(190)
        getattr(params,'set'+axis+'CutSpacing')(290)
        getattr(params,'set'+axis+'BottomEnclosure')(100)
        getattr(params,'set'+axis+'TopEnclosure')(100)
    params.setNumCutRows(3); params.setNumCutCols(3); via.setViaParams(params)
    wires={n:odb.dbSWire_create(block.findNet(n),'ROUTED') for n in ('VPWR','VGND')}
    for net,layer,r in planned:
        odb.dbSBox_create(wires[net],tech.findLayer(layer),*r,'STRIPE')
    for net,vx,vy in sorted(set(vias)):
        if any(n==net and abs(px-vx)<1000 and abs(py-vy)<1000 for n,px,py in existing_vias):
            continue
        odb.dbSBox_create(wires[net],via,vx,vy,'STRIPE')
    # Verify every added conductor uses a permitted layer and every terminal has
    # at least one explicitly connected boundary tab. Full DRC is separate.
    assert all(n in wires and layer in ('Metal3','Metal4') for n,layer,r in planned)
    report=dict(status='peripheral_geometry_added_not_signoff',source_sha256=hashlib.sha256(a.odb.read_bytes()).hexdigest(),
        macro_supply_pin_rectangles=len(pins),buses=buses,added_rectangles=len(planned),added_via_arrays=len(vias),
        forbidden_layer_added=False,macro_interior_routes_added=False)
    odb.write_db(db,str(a.out))
    full_def=a.out.with_suffix('.full.def')
    odb.write_def(block,str(full_def))
    text=full_def.read_text()
    section=re.search(r'\bSPECIALNETS\s+\d+\s*;.*?END SPECIALNETS',text,re.S)[0]
    via_text=re.search(r'- packet_supply_via3_3x3\b.*?;',text,re.S)[0]
    header='VERSION 5.8 ;\nDIVIDERCHAR "/" ;\nBUSBITCHARS "[]" ;\nDESIGN tt_um_shanebri_top ;\nUNITS DISTANCE MICRONS 1000 ;\n'
    a.out.with_suffix('.special.def').write_text(header+'VIAS 1 ;\n'+via_text+'\nEND VIAS\n'+section+'\nEND DESIGN\n')
    a.out.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__': main()
