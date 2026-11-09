"""Preserve streaming evidence and inherited ASIC budgets without activation."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
ACTIVE=ROOT/'test/sim_build/timing_headroom_20261104_01/production'
sys.path.insert(0,str(ROOT/'tools/timing'))
from check_signoff import REQUIRED_CORNERS,check_metrics,find_state
from diagnose_cones import paths
from summarize_refactor_endpoints import register_map


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();campaign,out=a.campaign.resolve(),a.out.resolve()
    out.mkdir(parents=True,exist_ok=False)
    with (out/'verify_active.log').open('x') as log:
        subprocess.run([sys.executable,'-B',str(ROOT/'tools/timing/headroom_release.py'),
            '--verify-active',str(ROOT/'docs/timing/20261104-headroom/activation.json')],
            stdout=log,stderr=subprocess.STDOUT,check=True)
    path=find_state(ACTIVE/'run');active=json.loads(path.read_text())
    if check_metrics(active['metrics']):raise ValueError('Active strict signoff no longer passes')
    fixed_path=ROOT/'docs/timing/20261030-control-refactor/qualified-parent/69-openroad-stapostpnr/state_out.json'
    fixed=json.loads(fixed_path.read_text())['metrics']
    result=dict(status='EVALUATED_PHYSICAL_PEERS_PENDING',automatic_activation=False,
        fixed_release='bb7c5ef3c54a7ae2733bbfae82aa940016375007',
        fixed_state_sha256=sha(fixed_path),active_state_sha256=sha(path),
        timing_evidence='Inherited exact qualified ASIC; no new extraction or physical implementation',
        corner_budgets={},new_asic_paths=[],tests={})
    for corner in REQUIRED_CORNERS:
        result['corner_budgets'][corner]={}
        for check in ('setup','hold'):
            key=f'timing__{check}__ws__corner:{corner}'
            value=active['metrics'][key]
            result['corner_budgets'][corner][check]=dict(parent_ns=value,candidate_ns=value,
                incremental_consumed_ns=0.0,cumulative_consumed_ns=fixed[key]-value,
                approved_floor_ns=None,approved_remaining_budget_ns=None,
                proposed_floor_ns=fixed[key],proposed_remaining_budget_ns=value-fixed[key],
                proposed_floor_status='not approved; original CI reserve proposal',
                signoff_violations=active['metrics'][f'timing__{check}_vio__count__corner:{corner}'],
                signoff_tns_ns=active['metrics'][f'timing__{check}__tns__corner:{corner}'])
    mapping={v:k for k,v in register_map(Path(active['nl']).read_text()).items()}
    result['inherited_limiting_paths']={}
    for corner in REQUIRED_CORNERS:
        for delay,check in (('max','setup'),('min','hold')):
            records=sorted(paths((path.parent/corner/(delay+'.rpt')).read_text()),key=lambda x:x['slack'])
            worst=records[0]
            result['inherited_limiting_paths'][corner+'-'+check]=dict(
                start=worst['start'],endpoint=worst['endpoint'],architectural_q=mapping.get(worst['endpoint']),
                slack_report_ns=worst['slack'])
    result['asic_identity']=dict(netlist_sha256=sha(active['nl']),sdc_sha256=sha(active['sdc']),
        clock_sinks=len(re.findall(r'\.CLK\s*\(',Path(active['nl']).read_text())),
        area_um2=active['metrics']['design__instance__area__stdcell'],area_increment_um2=0,
        activation_receipt_sha256=sha(ROOT/'docs/timing/20261104-headroom/activation.json'))
    runs=('validated_rtl','validated_gate','usb_rtl_final2','usb_gates_final2','rtl_final',
          'depth8_diagnostic','long4','long8')
    for name in runs:
        receipt=campaign/name/'receipt.json'
        data=json.loads(receipt.read_text())
        if (not data['tests'] or any(data[k] for k in ('failures','errors','skipped'))
                or data.get('software_changes')):raise ValueError('Unclean validation: '+name)
        if data['kind']=='functional_gate_simulation' and data['source_sha256'].get(active['nl'])!=sha(active['nl']):
            raise ValueError('Gate tests do not match active exact netlist')
        result['tests'][name]=dict(receipt=data,receipt_sha256=sha(receipt))
        target=out/name;target.mkdir()
        for filename in ('receipt.json','results.xml','measurements.json','software_inputs.json','usb_ls_ff8_samples.csv'):
            source=campaign/name/filename
            if source.exists():shutil.copy2(source,target/filename)
    # The old 39-test regression remains independent of the new opt-in modules.
    xml=ET.parse(ROOT/'test/results.xml')
    if (len(xml.findall('.//testcase'))!=39 or xml.findall('.//failure')
            or xml.findall('.//error') or xml.findall('.//skipped')):raise ValueError('Core regression not complete')
    core_log=ROOT/'test/sim_build/streaming_20261104_01-core_regression_final.log'
    if not re.search(r'TESTS=39\s+PASS=39\s+FAIL=0\s+SKIP=0',core_log.read_text()):
        raise ValueError('Core runner lacks fresh successful completion')
    shutil.copy2(ROOT/'test/results.xml',out/'core_results.xml');shutil.copy2(core_log,out/'core_regression.log')
    result['existing_core_regression']=dict(tests=39,failures=0,skipped=0,
        report_sha256=sha(out/'core_results.xml'))
    result['unit_tests']={}
    for pattern in ('test_streaming_host.py','test_usb_ls_tools.py'):
        log=out/(pattern+'.log')
        with log.open('x') as stream:
            subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(ROOT/'test'),
                '-p',pattern,'-v'],stdout=stream,stderr=subprocess.STDOUT,check=True)
        count=re.search(r'Ran (\d+) tests?',log.read_text())
        if not count:raise ValueError('Missing unit test count')
        result['unit_tests'][pattern]=dict(tests=int(count[1]),status='pass',log_sha256=sha(log))
    probe=ROOT/'.bringup/campaigns/streaming_20261104_01/probe/receipt.json'
    shutil.copy2(probe,out/'hardware_probe.json')
    result['physical_validation']=dict(status='PENDING',arty_port_reported_by_user='COM3',
        probe=json.loads(probe.read_text()),uart_receiver='not arrived, confirmed by user',
        peer_runs=0,waveforms='NOT_ACQUIRED',electrical='NOT_MEASURED')
    # A conservative bound uses all 96 unstuffed bits (SYNC/PID/8 data/CRC),
    # ceil(96/6) stuff bits and three EOP symbols. No buffer assumption depends
    # on favorable payload data or CRC patterns.
    symbols_bound=12*8+(12*8)//6+3
    command_words=1+(symbols_bound+3)//4
    requirements=dict(status='PROVISIONAL_PENDING_PHYSICAL_SERVICE_MEASUREMENTS',
        existing_fifo_useful_bytes=16,packet_length_bytes_max=65536,
        usb_ls=dict(payload_bytes_max=8,symbols_upper_bound=symbols_bound,
            script_bytes_including_header=command_words*4,descriptor_bytes=8,
            proposed_command_slot_bytes=128,proposed_slots=2,proposed_total_bytes=256,
            location='future FPGA-side autonomous feeder; no ASIC SRAM added',
            launch_rule='complete immutable script and descriptor before enabling TX',
            local_service_requirement='refill before OSR/FIFO exhaustion; no mid-packet starvation'),
        decision='retain four-word ASIC queues for measured packed/batched workload; defer deeper FIFO promotion')
    write(out/'packet_requirements.json',requirements)
    result['packet_requirements']=requirements
    for protocol in ('uart_packed_stream','spi_packed_stream','usb_ls_tx_symbols'):
        for suffix in ('asm','hex'):
            source=ROOT/'examples'/f'{protocol}.{suffix}'
            target=out/'firmware'/source.name;target.parent.mkdir(exist_ok=True);shutil.copy2(source,target)
    write(out/'receipt.json',result)
    files=[p for p in out.rglob('*') if p.is_file()]
    files += [p for p in (ROOT/'tools/streaming').iterdir() if p.is_file()]
    files += [ROOT/'test'/n for n in ('test_streaming.py','test_streaming_long.py','test_usb_ls_tx.py',
                                     'test_streaming_host.py','test_usb_ls_tools.py')]
    write(out/'evidence_sha256.json',{str(p):sha(p) for p in files})
    print(out)


if __name__=='__main__':main()
