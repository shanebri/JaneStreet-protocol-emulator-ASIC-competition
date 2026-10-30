"""Cycle-check the registered portal against the rejected original integration."""
from pathlib import Path
import subprocess
import sys
import production_trial as trial

root=Path(sys.argv[1]).resolve()
base=trial.REPO/'test/sim_build/packet_sram_repair_20261030_04'
out=root/(sys.argv[2] if len(sys.argv)>2 else 'verification')
out.mkdir(exist_ok=False)
for name,module in (('pio_subsystem.sv','packet_reference'),('pio_host_bank.sv','packet_reference_bank'),('packet/packet_sram_portal.sv','packet_reference_portal')):
    text=(base/'src'/name).read_text()
    text=text.replace('module '+name.split('/')[-1].split('.')[0]+' ', 'module '+module+' ')
    if name=='pio_subsystem.sv':
        text=text.replace('pio_host_bank bank','packet_reference_bank bank').replace('packet_sram_portal packet','packet_reference_portal packet')
    (out/(module+'.sv')).write_text(text)
names=[]
for line in (root/'info.yaml').read_text().split('  source_files:\n')[1].splitlines():
    if not line.startswith('    - '): break
    names.append(root/'src'/line.split('"')[1])
models=trial.PDK/'ihp-sg13cmos5l/libs.ref/sg13cmos5l_sram/verilog'
binary=out/'differential.vvp'
with (out/'differential.log').open('w') as log:
    subprocess.run(['iverilog','-g2012','-DFUNCTIONAL','-s','portal_differential_tb','-o',str(binary),
        *map(str,names),*[str(p) for p in out.glob('*.sv')],
        str(models/'RM_IHPSG13_1P_64x16_c2.v'),str(models/'RM_IHPSG13_1P_core_behavioral.v'),
        str(trial.REPO/'tools/packet_sram/portal_differential_tb.sv')],stdout=log,stderr=subprocess.STDOUT,check=True)
    subprocess.run(['vvp','-N',str(binary)],stdout=log,stderr=subprocess.STDOUT,check=True)
print((out/'differential.log').read_text())
