"""Record available alternative SRAM fast models; never substitute corners."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--pdk-root',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
root=a.pdk_root.resolve()
revision=subprocess.run(['git','-C',str(root),'rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
libraries=[]
for path in sorted((root/'ihp-sg13cmos5l/libs.ref/sg13cmos5l_sram/lib').glob('*_fast_*.lib')):
    data=path.read_bytes(); text=data.decode()
    cell=re.search(r'\bcell\s*\(\s*([^\s)]+)',text)
    temperature=re.search(r'\bnom_temperature\s*:\s*([-0-9.]+)',text)
    voltage=re.search(r'\bnom_voltage\s*:\s*([-0-9.]+)',text)
    if not all((cell,temperature,voltage)): raise ValueError('Malformed SRAM model: '+str(path))
    libraries.append(dict(cell=cell[1],path=str(path),sha256=hashlib.sha256(data).hexdigest(),
        temperature_c=float(temperature[1]),voltage_v=float(voltage[1])))
if not libraries: raise ValueError('No alternative fast models found')
result=dict(scope='Local pinned-PDK model inventory only; no alternative implementation qualification',
    pdk_revision=revision,libraries=libraries,fast_library_count=len(libraries),
    exact_1p32V_m40C_count=sum(v['temperature_c']==-40 and v['voltage_v']==1.32 for v in libraries))
with a.out.open('x') as f: json.dump(result,f,indent=2); f.write('\n')
print('Fast SRAM libraries:',len(libraries),'exact required -40 C:',result['exact_1p32V_m40C_count'])
