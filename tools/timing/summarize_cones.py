"""Archive and summarize complete diagnostic reports without claiming signoff."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import shutil
import zipfile
from diagnose_cones import paths, sha


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--diagnosis',type=Path,required=True)
    p.add_argument('--trial',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    manifest=json.loads((a.diagnosis/'manifest.json').read_text())
    if manifest['status']!='complete': raise ValueError('Incomplete diagnostic run')
    a.out.mkdir(parents=True,exist_ok=False)
    for name in ('manifest.json','endpoint_mapping.json','queries.tcl'):
        shutil.copy2(a.diagnosis/name,a.out/name)
    mapping=json.loads((a.diagnosis/'endpoint_mapping.json').read_text())
    failures={r['endpoint'] for r in mapping if r['slack']<0}
    inventory={}
    for folder in sorted(a.diagnosis.glob('nom_*')):
        if not folder.is_dir(): continue
        reports={}
        for file in sorted(folder.glob('*.rpt')):
            ps=paths(file.read_text())
            if not ps: continue
            rows=[]
            for row in ps:
                body=row.pop('text')
                data=body.split('data arrival time')[0]
                row['cells']=list(dict.fromkeys(re.findall(r'\s([\w]+)/(?:Y|X|Q) \(sg13cmos5l_',data)))
                row['arrival_ns']=float(re.search(r'([-\d.]+)\s+data arrival time',body)[1])
                row['required_ns']=float(re.search(r'([-\d.]+)\s+data required time',body)[1])
                rows.append(row)
            reports[file.name]=dict(path_count=len(rows), worst_slack_ns=min(r['slack'] for r in rows), paths=rows)
        inventory[folder.name]=reports
    slow=inventory['nom_slow_1p08V_125C']
    sharing={}
    for driver in ('_17226_','_17236_','_17238_','_17250_','_17262_','_28912_','_28923_'):
        all_paths=[r for name,report in slow.items() if name.startswith(('cone_','through_')) for r in report['paths']]
        affected=sorted({r['endpoint'] for r in all_paths if driver in r['cells']} & failures)
        sharing[driver]=dict(failing_endpoints=affected,count=len(affected))
    netlist=next(a.trial.glob('replay-input/*-openroad-fillinsertion/*.nl.v'))
    pins={}; drivers=defaultdict(list); sinks=defaultdict(list)
    for master,cell,body in re.findall(r'\b(sg13cmos5l_\w+)\s+([^\s(]+)\s*\((.*?)\);',netlist.read_text(),re.S):
        for pin,net in re.findall(r'\.(\w+)\s*\(\s*(.*?)\s*\)',body,re.S):
            net=re.sub(r'\s+','',net).lstrip('\\')
            name=cell+'/'+pin
            pins[name]=net
            entry=dict(pin=name,master=master)
            if pin in ('Y','X','Q','Q_N','L_HI','L_LO'):
                drivers[net].append(entry)
            elif pin not in ('VDD','VSS','VNW','VPW'):
                sinks[net].append(entry)
    electrical={}
    for folder in sorted((a.trial/'replay').glob('*-baseline')):
        nets={}; violations=[]; kind=None
        for line in (folder/'electrical.rpt').read_text().splitlines():
            if line.startswith('max '): kind=line.strip()
            if '(VIOLATED)' not in line: continue
            pin=line.split()[0]; net=pins.get(pin,pin)
            violations.append(dict(kind=kind,pin=pin,net=net,report_line=line.strip()))
            ds=drivers.get(net,[]) or [dict(pin=net,master='input_port')]
            loads=sinks.get(net,[])
            nets[net]=dict(drivers=ds,loads=loads,functional_pins=sum(v['master']!='sg13cmos5l_antennanp' for v in loads),
                           antenna_pins=sum(v['master']=='sg13cmos5l_antennanp' for v in loads),total_loads=len(loads))
        electrical[folder.name]=dict(violations=violations,nets=nets)
    result=dict(scope='Diagnostic only; paths bounded as recorded in queries.tcl',
                shared_gates=sharing,path_inventory=inventory,electrical_inventory=electrical,
                netlist_sha256=sha(netlist),runner_sha256=sha(__file__))
    (a.out/'inventory.json').write_text(json.dumps(result,indent=2)+'\n')
    with zipfile.ZipFile(a.out/'reports.zip','x',zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(a.diagnosis.rglob('*')):
            if file.is_file() and file.suffix in ('.rpt','.log','.sdc'):
                archive.write(file,file.relative_to(a.diagnosis))
    (a.out/'SHA256SUMS').write_text(''.join(f'{sha(f)}  {f.name}\n' for f in sorted(a.out.iterdir()) if f.is_file()))
    print(json.dumps(sharing,indent=2))


if __name__=='__main__': main()
