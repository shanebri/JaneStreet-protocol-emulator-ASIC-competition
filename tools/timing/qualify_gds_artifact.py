"""Qualify an exact completed GDS with native LVS, TT precheck and gate tests.

Run inside the pinned Nix EDA shell. This never borrows a prior route's LVS
proof or changes signoff limits. Each invocation requires a fresh output.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from check_signoff import check_metrics, find_state
from closure_collect import nominal_view
from closure_trial import unique
from qualify_final_route import physical_pin_fingerprint


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('run', 'out', 'pdk-root', 'support-tools', 'precheck-python', 'test-python', 'test-source'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    run, out = a.run.resolve(), a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    manifest = dict(status='running', commands=[], checks={})
    def save(): (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    def command(args, name, cwd, env):
        manifest['commands'].append(dict(args=list(map(str,args)), cwd=str(cwd)))
        save()
        with (out/(name+'.log')).open('w') as log:
            subprocess.run(list(map(str,args)), cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    try:
        state_path = find_state(run); state = json.loads(state_path.read_text())
        final = run/'final'; metrics = json.loads((final/'metrics.json').read_text())
        config = json.loads((run/'resolved.json').read_text())
        if check_metrics(state['metrics']) or check_metrics(metrics):
            raise ValueError('Post-route or final strict metrics fail')
        for key in ('route__drc_errors', 'route__antenna_violation__count', 'magic__illegal_overlap__count',
                    'design__lvs_device_difference__count', 'design__lvs_net_difference__count',
                    'design__lvs_property_fail__count', 'design__lvs_error__count',
                    'design__lvs_unmatched_device__count', 'design__lvs_unmatched_net__count',
                    'design__lvs_unmatched_pin__count'):
            if metrics.get(key) != 0 or isinstance(metrics.get(key), bool):
                raise ValueError('Missing or failed final physical metric: '+key)
        gds = unique(final/'gds', '*.gds'); nl = unique(final/'nl', '*.nl.v')
        lef = unique(final/'lef', '*.lef'); sdc = unique(final/'sdc', '*.sdc')
        spef = unique(final/'spef/nom', '*.spef')
        for target, source in ((nl, state['nl']), (sdc, state['sdc']), (spef, nominal_view(state['spef']))):
            if sha(target) != sha(source):
                raise ValueError('Final artifact differs from accepted timing view: '+str(target))
        extraction = unique(run, '*-magic-spiceextraction/config.json')
        extraction_config = json.loads(extraction.read_text())
        extraction_state = json.loads(extraction.with_name('state_in.json').read_text())
        if not extraction_config.get('MAGIC_EXT_USE_GDS') or sha(extraction_state['gds']) != sha(gds):
            raise ValueError('LVS did not extract this final GDS')
        if physical_pin_fingerprint(config['FP_DEF_TEMPLATE']) != physical_pin_fingerprint(state['def']):
            raise ValueError('Boundary or signal-pin geometry changed')
        route_manifest = unique(run, '*-pio-routeacceptance/qualification/manifest.json')
        route = json.loads(route_manifest.read_text())
        if route['status'] != 'complete' or route['sha256'].get(str(state_path)) != sha(state_path):
            raise ValueError('Final route acceptance does not match this artifact')
        for path, expected in route['sha256'].items():
            if sha(path) != expected:
                raise ValueError('Accepted route artifact changed: '+path)
        manifest['checks'].update(strict_metrics='pass', native_routing_drc_antenna='pass',
            independent_gds_lvs='pass', final_view_identity='pass', pin_geometry='pass', route_acceptance='pass')
        files = [gds,nl,lef,sdc,spef,state_path,extraction,extraction.with_name('state_in.json'),
                 final/'metrics.json',run/'resolved.json',route_manifest]
        manifest['sha256'] = {str(f): sha(f) for f in files}
        save()
        project = out/'project'; project.mkdir()
        shutil.copy2(a.test_source.resolve().parent/'info.yaml', project/'info.yaml')
        for source in (gds,nl,lef):
            target = project/(gds.stem+'.v') if source==nl else project/source.name
            shutil.copy2(source,target)
        shutil.copytree(a.support_tools/'precheck', out/'precheck',
                        ignore=shutil.ignore_patterns('reports','__pycache__','.pytest_cache'))
        (out/'tech').symlink_to((a.support_tools/'tech').resolve(), target_is_directory=True)
        env = dict(os.environ, PDK_ROOT=str(a.pdk_root.resolve()), PDK='ihp-sg13cmos5l',
                   PYTHONPATH='', PYTHONDONTWRITEBYTECODE='1')
        command([a.precheck_python.absolute(),out/'precheck/precheck.py','--gds',project/gds.name,
                 '--tech','ihp-sg13cmos5l'], 'precheck', out/'precheck', env)
        precheck = ET.parse(out/'precheck/reports/results.xml')
        if precheck.findall('.//failure') or precheck.findall('.//error') or not precheck.findall('.//testcase'):
            raise ValueError('Missing or failed precheck tests')
        manifest['checks']['tt_precheck'] = dict(status='pass', tests=len(precheck.findall('.//testcase')))
        test = out/'test'
        shutil.copytree(a.test_source,test,ignore=shutil.ignore_patterns('sim_build','__pycache__','*.fst','*.vcd','results.xml','gate_level_netlist.v'))
        shutil.copy2(nl,test/'gate_level_netlist.v')
        # tb.v includes definitions from the submission source directory.
        shutil.copytree(a.test_source.resolve().parent/'src',out/'src')
        gate_env = dict(env, PATH=str(a.test_python.absolute().parent)+':'+env['PATH'], GATES='yes')
        version = subprocess.run(['iverilog','-V'],env=gate_env,capture_output=True,text=True,check=True)
        (out/'iverilog-version.log').write_text(version.stdout+version.stderr)
        if not re.search(r'Icarus Verilog version 13\.0\b', version.stdout):
            raise ValueError('Gate tests require Icarus 13.0')
        command(['make','-B','GATES=yes'], 'gate_tests', test, gate_env)
        results = ET.parse(test/'results.xml'); cases = results.findall('.//testcase')
        if len(cases)!=39 or results.findall('.//failure') or results.findall('.//error') or results.findall('.//skipped'):
            raise ValueError('Expected all 39 gate-level tests to pass without skips')
        manifest['checks']['gate_tests'] = dict(status='pass', tests=len(cases), netlist_sha256=sha(test/'gate_level_netlist.v'))
        manifest['status'] = 'complete'
    except Exception as exc:
        manifest.update(status='failed', error=str(exc)); raise
    finally:
        save()
    print('PASS: exact final timing views, native GDS LVS, TT precheck, pin geometry, and all 39 gate tests')


if __name__ == '__main__':
    main()
