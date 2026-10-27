from pathlib import Path
import os
import subprocess
import sys
repo=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(repo/'tools/timing'))
from replay import slack
out=repo/'test/sim_build/closure/host-path-clean-classes'
out.mkdir(parents=True,exist_ok=False)
script=(repo/'tools/timing/report_io_paths.tcl').read_text()
assert script.count('read_spef $spef\n')==1
for name,wr,rd in (('cmd0',1,0),('wordA',1,0)):
    path=out/f'{name}.tcl'
    cases=f'\nset_case_analysis {wr} [get_ports {{ui_in[4]}}]\nset_case_analysis {rd} [get_ports {{ui_in[5]}}]\n'
    cases += f'set_case_analysis 0 [get_ports {{ui_in[0]}}]\nset_case_analysis 0 [get_ports {{ui_in[2]}}]\nset_case_analysis {int(name=="wordA")} [get_ports {{ui_in[3]}}]\n'
    path.write_text(script.replace('read_spef $spef\n','read_spef $spef\n'+cases))
    env=dict(os.environ,PIO_TIMING_RUN=str(repo/'test/sim_build/closure/grt_capacity25-01/replay-input'),
             PDK_ROOT='/home/shane/eda/pdk-2bbec755', PIO_TIMING_CORNER='nom_slow_1p08V_125C',
             PIO_TIMING_MODE='baseline',PIO_TIMING_OUT=str(out/name),PIO_TIMING_TARGET='_31993_/D')
    with (out/f'{name}.log').open('w') as log:
        run=subprocess.run(['sta','-exit',str(path)],env=env,stdout=log,stderr=subprocess.STDOUT)
    assert run.returncode==0
    print(name,'global',slack(out/name/'worst_setup.rpt'),flush=True)
    report=(out/name/'input_ui_in_1__max.rpt').read_text().partition('\nStartpoint:')[0]
    for line in report.splitlines():
        if any(s in line for s in ('Startpoint:', 'Endpoint:', 'slack (')): print(line,flush=True)

