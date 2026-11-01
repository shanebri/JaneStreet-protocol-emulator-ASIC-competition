"""Bind small timing increments to a verified qualified-parent connectivity graph.

Run with OpenROAD Python. Generated cell names are used only to identify the
archived evidence; production resolves unique pin-labelled fingerprints again.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from audit_clock_tree import snapshot
from check_signoff import check_metrics
from resolve_eco_targets import make_contract, resolve


def feedback_operation(block, data, register):
    cells, _, _, loads, _ = data
    matches = [name for name,(master,pins) in cells.items()
               if master == 'sg13cmos5l_dfrbpq_1' and pins['Q'].replace('\\', '') == register]
    if len(matches) != 1:
        raise ValueError('Missing or ambiguous architectural feedback register: '+register)
    ff = matches[0]
    net = block.findInst(ff).findITerm('D').getNet()
    drivers = [pin for pin in net.getITerms() if pin.getMTerm().getIoType() == 'OUTPUT']
    if len(drivers) != 1 or loads[net.getName()] != [(ff, 'D')]:
        raise ValueError('Feedback repair is not an exclusive single-driver D boundary')
    driver = drivers[0]
    return dict(kind='buffer', target=driver.getInst().getName()+'/'+driver.getMTerm().getName(),
                old=driver.getInst().getMaster().getName(), max_loads=1, location='sink_centroid')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--inventory", action="store_true")
    p.add_argument("--add-clone", action="store_true")
    p.add_argument("--add-buffer", action="store_true")
    p.add_argument('--add-combination', action='store_true')
    a = p.parse_args()
    repo = a.repo.resolve()
    parent_path = repo/"docs/timing/20261030-control-refactor/qualified-parent/69-openroad-stapostpnr/state_out.json"
    if check_metrics(json.loads(parent_path.read_text())["metrics"]):
        raise ValueError("Qualified parent fails strict numeric checks")
    source = repo/"test/sim_build/production_final_20261029_01/run/56-openroad-lastfanoutrepair/state_in.json"
    state = json.loads(source.read_text())
    import odb
    db = odb.dbDatabase.create()
    odb.read_db(db, state["odb"])
    data = snapshot(db.getChip().getBlock())
    cells, _, _, loads, _ = data
    if a.inventory:
        rows = []
        block = db.getChip().getBlock()
        for name in ('_17710_', '_28912_', '_30253_'):
            inst = block.findInst(name)
            outputs = [pin for pin in inst.getITerms() if pin.getMTerm().getIoType() == 'OUTPUT']
            rows.append(dict(name=name, master=inst.getMaster().getName(), location=inst.getLocation(),
                loads=[dict(pin='/'.join(sink), location=block.findInst(sink[0]).getLocation(),
                            master=cells[sink[0]][0]) for sink in loads[outputs[0].getNet().getName()]]))
        masters = sorted(master.getName() for lib in db.getLibs() for master in lib.getMasters()
                         if master.getName().startswith(('sg13cmos5l_nand3_', 'sg13cmos5l_or3_', 'sg13cmos5l_inv_', 'sg13cmos5l_a221oi_', 'sg13cmos5l_buf_')))
        print(json.dumps(dict(targets=rows, available_masters=masters), indent=2))
        return
    original = json.loads(subprocess.check_output([
        'git', 'show', 'bb7c5ef3c54a7ae2733bbfae82aa940016375007:tools/timing/production/last-fanout.json'], cwd=repo, text=True))
    base = resolve(data, original)
    if a.add_combination:
        block = db.getChip().getBlock()
        operations = base + [feedback_operation(block, data, 'pio.engines[1].core.isr[6]'),
            dict(kind='buffer', target='_17710_/Y', old='sg13cmos5l_nand3_1', max_loads=4, location='sink_centroid'),
            feedback_operation(block, data, 'pio.engines[1].core.isr[3]')]
        contract = make_contract(data, operations)
        if resolve(data, contract) != operations:
            raise ValueError('Combined contract self-resolution failed')
        contract['reference_odb_sha256'] = hashlib.sha256(Path(state['odb']).read_bytes()).hexdigest()
        with (a.out/'buffer_hold.json').open('x') as stream:
            json.dump(contract, stream, indent=2); stream.write('\n')
        print('PASS: combined control buffers and ISR[6]/ISR[3] hold boundaries uniquely bound')
        return
    if a.add_buffer:
        operations = base + [dict(kind='buffer', target='_17710_/Y', old='sg13cmos5l_nand3_1',
                                  max_loads=4, location='sink_centroid')]
        if db.findMaster('sg13cmos5l_buf_4') is None:
            raise ValueError('Required physical buffer master is unavailable')
        contract = make_contract(data, operations)
        if resolve(data, contract) != operations:
            raise ValueError('Host-buffer contract self-resolution failed')
        contract['reference_odb_sha256'] = hashlib.sha256(Path(state['odb']).read_bytes()).hexdigest()
        with (a.out/'host_buffer.json').open('x') as stream:
            json.dump(contract, stream, indent=2); stream.write('\n')
        print('PASS: bounded local host-control buffer contract uniquely bound')
        return
    if a.add_clone:
        from refactor_eco import selected_loads
        op = dict(kind='clone', target='_17710_/Y', old='sg13cmos5l_nand3_1',
                  x_min_um=550, max_loads=8, name='eco_control_local')
        block = db.getChip().getBlock()
        selected_loads(data, op, {inst.getName():inst.getLocation() for inst in block.getInsts()}, block.getDbUnitsPerMicron())
        operations = base + [op]
        contract = make_contract(data, operations)
        if resolve(data, contract) != operations:
            raise ValueError('Replica contract self-resolution failed')
        contract['reference_odb_sha256'] = hashlib.sha256(Path(state['odb']).read_bytes()).hexdigest()
        with (a.out/'host_clone.json').open('x') as stream:
            json.dump(contract, stream, indent=2); stream.write('\n')
        print('PASS: local host-control replication contract uniquely bound')
        return
    # Read the actual feedback endpoint and source in the reference graph.
    ff = cells["_32071_"]
    if ff[0] != "sg13cmos5l_dfrbpq_1" or ff[1]["Q"].replace("\\", "") != "pio.engines[1].core.isr[6]":
        raise ValueError("ISR[6] reference identity changed: " + repr(ff))
    if cells["_30253_"][0] != "sg13cmos5l_a21oi_1" or cells["_30253_"][1]["Y"] != ff[1]["D"]:
        raise ValueError("Feedback source is not the verified ISR[6] D driver")
    if loads[ff[1]["D"]] != [("_32071_", "D")]:
        raise ValueError("Hold repair would affect undeclared sinks")
    variants = {
        "hold": base + [dict(kind="buffer", target="_30253_/Y", old="sg13cmos5l_a21oi_1",
                             max_loads=1, location="sink_centroid")],
    }
    unavailable = {}
    if db.findMaster('sg13cmos5l_nand3_2') is not None:
        variants['host_drive'] = base + [dict(kind='size', instance='_17710_', old='sg13cmos5l_nand3_1', new='sg13cmos5l_nand3_2')]
    else:
        unavailable['host_drive'] = 'Required sg13cmos5l_nand3_2 master is absent; no contract generated'
    a.out.mkdir(parents=True, exist_ok=False)
    manifest = dict(scope="Reference binding only; no candidate physical qualification",
                    parent_state_sha256=hashlib.sha256(parent_path.read_bytes()).hexdigest(),
                    reference_state_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    reference_odb_sha256=hashlib.sha256(Path(state["odb"]).read_bytes()).hexdigest(),
                    operations=variants, unavailable_hypotheses=unavailable,
                    runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    boundaries=dict(hold="ISR[6] D; same clock and cycles",
                    host_drive="Existing live HOST_RD acceptance/control cone; identical gate function"))
    for name, operations in variants.items():
        contract = make_contract(data, operations)
        if resolve(data, contract) != operations:
            raise ValueError("Contract does not self-resolve")
        contract["reference_odb_sha256"] = manifest["reference_odb_sha256"]
        (a.out/(name+".json")).write_text(json.dumps(contract, indent=2)+"\n")
    (a.out/"reference_binding.json").write_text(json.dumps(manifest, indent=2)+"\n")
    print("PASS: available hypotheses uniquely bound; unavailable cells explicitly recorded")


if __name__ == "__main__":
    main()
