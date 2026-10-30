"""Fresh normal-production trial of the permitted-layer SRAM supply repair."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import production_trial as trial

trial.ROOT=trial.REPO/'test/sim_build/packet_sram_repair_20261030_04'
root=trial.ROOT
if '--worker' in sys.argv:
    trial.worker()
else:
    trial.freeze()
    config=json.loads((root/'src/config.json').read_text())
    config['PDN_MACRO_CONNECTIONS']=[r'pio\.packet\.storage\.memory VPWR VGND VDD.* VSS!']
    scripts=Path('/nix/store/6a08ghhhzl5a07nr0ly762yh1ah6m5bj-python3-3.13.13-env/lib/python3.13/site-packages/librelane/scripts/openroad')
    cfg=(scripts/'common/pdn_cfg.tcl').read_text()
    marker='\ndefine_pdn_grid \\\n    -macro'
    assert cfg.count(marker)==1
    # Preserve the original standard-cell grid. The macro is supplied by the
    # audited peripheral geometry instead of an empty/forbidden-layer grid.
    peripheral='''
define_pdn_grid -macro -instances {pio.packet.storage.memory} -name packet_peripheral -starts_with POWER -halo {10 10}
add_pdn_ring -grid packet_peripheral -layers {Metal3 Metal4} -widths {2 2} -spacings {2 2} -core_offsets {3 3}
add_pdn_connect -grid packet_peripheral -layers {Metal3 Metal4}
'''
    (root/'tools/timing/packet_pdn_cfg.tcl').write_text(cfg.split(marker)[0]+peripheral)
    config['PDN_CFG']=str(root/'tools/timing/packet_pdn_cfg.tcl')
    (root/'src/config.json').write_text(json.dumps(config,indent=2)+'\n')
    shutil.copy2(trial.REPO/'tools/packet_sram/repair_supply.py',root/'tools/timing/repair_supply.py')
    native=(scripts/'pdn.tcl').read_text()
    assert native.count('    write_views')==1
    insert='''    write_db $::env(STEP_DIR)/before_supply.odb
    set repair [file join $::env(DESIGN_DIR) .. tools timing repair_supply.py]
    puts [exec [info nameofexecutable] -exit -python $repair --odb $::env(STEP_DIR)/before_supply.odb --out $::env(STEP_DIR)/supplied.odb]
    foreach packet_net [[ord::get_db_block] getNets] {
        foreach packet_wire [$packet_net getSWires] { odb::dbSWire_destroy $packet_wire }
    }
    read_def -floorplan_initialize $::env(STEP_DIR)/supplied.special.def
    write_views'''
    (root/'tools/timing/packet_pdn.tcl').write_text(native.replace('    write_views',insert))
    flow=root/'tools/timing/production_flow.py'
    text=flow.read_text().replace('from librelane.steps.openroad import DetailedPlacement,','from librelane.steps.openroad import GeneratePDN, DetailedPlacement,')
    text=text.replace('steps = []', '''class PacketPDN(GeneratePDN):
    def get_script_path(self):
        return str(TOOL/'packet_pdn.tcl')

steps = []''')
    text=text.replace('steps.append(PlacementViews if original.id', "steps.append(PacketPDN if original.id == 'OpenROAD.GeneratePDN' else PlacementViews if original.id")
    flow.write_text(text)
    files=[p for folder in ('src','tools/timing','test') for p in (root/folder).rglob('*') if p.is_file()]
    files += [root/'info.yaml',root/'librelane_plugin_pio.py']
    (root/'frozen_inputs.json').write_text(json.dumps({str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)},indent=2)+'\n')
    command=['/nix/var/nix/profiles/default/bin/nix','develop','--offline','--command','python3','-B',str(Path(__file__).resolve()),'--worker']
    with (root/'launcher.log').open('w') as log:
        proc=subprocess.Popen(command,cwd='/home/shane/eda/librelane-3.1.0.dev3',stdin=subprocess.DEVNULL,
            stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    (root/'process.json').write_text(json.dumps(dict(pid=proc.pid,command=command),indent=2)+'\n')
    print('Started isolated SRAM supply repair trial',proc.pid)
