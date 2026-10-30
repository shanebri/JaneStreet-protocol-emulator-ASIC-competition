"""Clean production qualification of the registered portal and measured repairs.

Nothing is promoted automatically. Native flow, parent headroom rejection,
macro-aware replay, physical checks, precheck and old/new gate tests all remain
required. Missing exact fast SRAM characterization is a separate release block.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import production_trial as trial
from install_candidate_tools import install
from gate_runtime import gate_environment,provenance

BASE=trial.REPO/'test/sim_build/packet_sram_buffered_20261030_01'
MAIN=BASE/'recipe_01/contract.json'
TAIL=trial.REPO/'test/sim_build/packet_sram_buffered_repair_20261030_01/recipe_tail_01/contract.json'
ROOT=trial.REPO/'test/sim_build/packet_sram_buffered_production_20261030_01'


def freeze():
    ROOT.mkdir(exist_ok=False); (ROOT/'run').mkdir()
    for folder in ('src','tools/timing','test'):
        shutil.copytree(BASE/folder,ROOT/folder,ignore=shutil.ignore_patterns('sim_build','__pycache__','*.fst','*.vcd','results.xml','packet_results.xml','gate_level_netlist.v','user_config.json','config_merged.json'))
    for file in ('info.yaml','librelane_plugin_pio.py'): shutil.copy2(BASE/file,ROOT/file)
    for path in (trial.REPO/'tools').glob('*.py'): shutil.copy2(path,ROOT/'tools'/path.name)
    shutil.copytree(trial.REPO/'examples',ROOT/'examples')
    (ROOT/'tt').symlink_to(trial.TOOLING/'tt',target_is_directory=True)
    install(ROOT)
    shutil.copy2(Path(__file__).with_name('compare_timing.py'),ROOT/'tools/timing/compare_timing.py')
    contracts=ROOT/'tools/timing/packet_contracts'; contracts.mkdir()
    shutil.copy2(MAIN,contracts/'main.json'); shutil.copy2(TAIL,contracts/'tail.json')
    (contracts/'adaptive.json').write_text('{"schema":1,"entries":[]}\n')
    def relocate(obj):
        if isinstance(obj,str): return obj.replace(str(BASE),str(ROOT))
        if isinstance(obj,list): return [relocate(v) for v in obj]
        if isinstance(obj,dict): return {k:relocate(v) for k,v in obj.items()}
        return obj
    config=relocate(json.loads((ROOT/'src/config.json').read_text()))
    config['PIO_ECO_CONTRACT']=str(contracts/'main.json')
    config['PIO_INCREMENTAL_ECO_CONTRACTS']=[str(contracts/'tail.json'),str(contracts/'adaptive.json')]
    (ROOT/'src/config.json').write_text(json.dumps(config,indent=2)+'\n')
    parent=ROOT/'parent/69-openroad-stapostpnr'; parent.mkdir(parents=True)
    source=trial.REPO/'test/sim_build/github_analysis_40938542430/runs/wokwi/69-openroad-stapostpnr/state_out.json'
    assert hashlib.sha256(source.read_bytes()).hexdigest()=='af8ced2439790ea47598651acacfbb0eb9d9848a858972a1124358e074ec0ae5'
    shutil.copy2(source,parent/'state_out.json')
    files=[p for folder in ('src','tools','test','examples','parent') for p in (ROOT/folder).rglob('*') if p.is_file()]
    files += [ROOT/'info.yaml',ROOT/'librelane_plugin_pio.py']
    (ROOT/'frozen_inputs.json').write_text(json.dumps({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)},indent=2)+'\n')


def worker():
    status=dict(status='running',commands=[],candidate_promoted=False,exact_fast_sram_model_available=False)
    def save(): (ROOT/'job.json').write_text(json.dumps(status,indent=2)+'\n')
    def run(command,label,env=None):
        status['commands'].append(command); save()
        with (ROOT/(label+'.log')).open('w') as log:
            subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    try:
        env=dict(os.environ,PYTHONPATH='',PATH=str(trial.TOOLING/'venv/bin')+':'+os.environ['PATH'],XDG_CACHE_HOME=str(ROOT/'.cache'))
        run([str(trial.TOOLING/'venv/bin/python'),str(ROOT/'tt/tt_tool.py'),'--create-user-config','--ihp'],'configure',env)
        run([sys.executable,'-m','librelane','--pdk','ihp-sg13cmos5l','--manual-pdk','--pdk-root',str(trial.PDK),
             '--run-tag','packet','--force-run-dir',str(ROOT/'run'),'src/config_merged.json'],'production')
        status['status']='qualifying_gds'; save()
        (ROOT/'gate_runtime.json').write_text(json.dumps(provenance(),indent=2)+'\n')
        run([sys.executable,str(ROOT/'tools/timing/qualify_gds_artifact.py'),'--run',str(ROOT/'run'),
             '--out',str(ROOT/'qualification'),'--pdk-root',str(trial.PDK),'--support-tools',str(trial.TOOLING/'tt'),
             '--precheck-python',str(trial.TOOLING/'precheck-venv/bin/python'),'--test-python','/home/shane/eda/pio-test-venv/bin/python',
             '--test-source',str(ROOT/'test')],'artifact_qualification',gate_environment(os.environ))
        status.update(status='physical_flow_passed_model_blocked',reason='Exact fast -40 C SRAM characterization remains unavailable; not release approval')
    except Exception as exc:
        status.update(status='failed',error=str(exc))
    finally: save()


if __name__=='__main__':
    if '--worker' in sys.argv: worker()
    elif '--freeze-only' in sys.argv: freeze(); print(ROOT)
    else:
        freeze()
        command=['/nix/var/nix/profiles/default/bin/nix','develop','--offline','--command','python3','-B',str(Path(__file__).resolve()),'--worker']
        with (ROOT/'launcher.log').open('w') as log:
            proc=subprocess.Popen(command,cwd='/home/shane/eda/librelane-3.1.0.dev3',stdin=subprocess.DEVNULL,
                stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
        (ROOT/'process.json').write_text(json.dumps(dict(pid=proc.pid,command=command),indent=2)+'\n')
        print('Started clean normal production qualification',proc.pid)
