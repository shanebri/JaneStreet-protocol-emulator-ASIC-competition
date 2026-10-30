"""Separate reported cell arcs, inter-pin wire increments and input arrival."""
import argparse
import json
from pathlib import Path
import re
from diagnose_cones import paths, sha


def breakdown(row):
    data=row['text'].split('data arrival time')[0]
    active='input port' in row['start']
    sums=dict(cell_arc_ns=0.,buffer_arc_ns=0.,wire_increment_ns=0.,port_increment_ns=0.)
    arcs=[]
    for line in data.splitlines():
        m=re.match(r'^\s*([\d.\s-]+)\s+[\^v]\s+(\S+)\s+\(([^)]+)\)',line)
        if not m: continue
        nums=[float(n) for n in m[1].split()]
        if len(nums)<3: continue
        pin,master=m[2],m[3]
        if not active:
            if pin.endswith('/Q'): active=True
            else: continue
        delay=nums[-2]
        if master=='in': kind='port_increment_ns'
        elif pin.rsplit('/',1)[-1] in ('X','Y','Q','Q_N'):
            kind='buffer_arc_ns' if re.match(r'sg13cmos5l_(buf_|dlygate)',master) else 'cell_arc_ns'
        else: kind='wire_increment_ns'
        sums[kind]+=delay
        arcs.append(dict(pin=pin,master=master,kind=kind,delay_ns=delay,slew_ns=nums[-3],
                         cap_pf=nums[1] if len(nums)==5 else None,fanout=int(nums[0]) if len(nums)==5 else None))
    arrival=float(re.search(r'([-\d.]+)\s+data arrival time',row['text'])[1])
    required=float(re.search(r'([-\d.]+)\s+data required time',row['text'])[1])
    return dict(start=row['start'],endpoint=row['endpoint'],slack_ns=row['slack'],arrival_ns=arrival,
                required_ns=required,**sums,reported_data_path_sum_ns=sum(sums.values()),arcs=arcs,
                scope='Reported derated increments; not counterfactual removable delay. Clock and external input delay are separate.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('report',type=Path)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    result=dict(report=str(a.report),sha256=sha(a.report),paths=[breakdown(row) for row in paths(a.report.read_text())])
    with a.out.open('x') as f: json.dump(result,f,indent=2); f.write('\n')
    print(json.dumps({k:v for k,v in result['paths'][0].items() if k!='arcs'},indent=2))
