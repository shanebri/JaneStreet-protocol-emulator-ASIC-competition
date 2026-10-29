"""Strict gate, nine exact-artifact STA sessions, and final clock connectivity.

This is a route acceptance check. GDS DRC/LVS, precheck and functional gate
tests remain separate mandatory qualifications of the completed production run.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from check_signoff import find_state
from closure_collect import nominal_view
from collect_implementation import selected_metrics, validate_replay
from implementation_trial import template_fingerprint
from routing_delta import read_def


def physical_pin_fingerprint(path):
    # Resizing may rename internal nets attached to outputs. Net identity is
    # checked by logical/LVS audits; geometry compares every pin's direction,
    # layer rectangles, physical location and orientation and the die boundary.
    text = re.sub(r'(\+ NET)\s+\S+', r'\1 SAME_NET', Path(path).read_text())
    return template_fingerprint(text)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--pdk-root', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    out = a.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    tool = Path(__file__).resolve().parent
    state_path = find_state(a.run.resolve())
    state = json.loads(state_path.read_text())
    manifest = dict(status='running', state=str(state_path), commands=[])

    def command(args, name):
        manifest['commands'].append(args)
        with (out/(name+'.log')).open('w') as log:
            subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, check=True)

    try:
        command([sys.executable, str(tool/'check_signoff.py'), str(state_path)], 'strict_signoff')
        config = json.loads((a.run.resolve()/'resolved.json').read_text())
        template = Path(config['FP_DEF_TEMPLATE'])
        if physical_pin_fingerprint(template) != physical_pin_fingerprint(state['def']):
            raise ValueError('Die boundary or physical signal-pin geometry changed')
        preservation = []
        for audit_path in sorted(a.run.resolve().glob('*/preserved/audit.json')):
            audit = json.loads(audit_path.read_text())
            if audit['status'] != 'pass' or not audit['fixed_net_count']:
                raise ValueError('Invalid route-preservation audit')
            for path, expected in audit['sha256'].items():
                if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
                    raise ValueError('Preservation artifact changed: '+path)
            source = json.loads((audit_path.parent.parent/'state_in.json').read_text())
            before_routes = read_def(Path(source['def']))[0]
            final_routes = read_def(Path(state['def']))[0]
            if any(before_routes[net] != final_routes.get(net) for net in audit['fixed_nets']):
                raise ValueError('Detailed routing changed a protected wire')
            preservation.append(dict(audit=str(audit_path), fixed_routes_preserved=audit['fixed_net_count']))
        view = out/'replay-input'
        links = {'input-openroad-fillinsertion/tt_um_shanebri_top.nl.v': Path(state['nl']),
                 'output-openroad-rcx/nom/tt_um_shanebri_top.nom.spef': nominal_view(state['spef']),
                 'final/sdc/tt_um_shanebri_top.sdc': Path(state['sdc'])}
        for name, target in links.items():
            link = view/name; link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(target)
        command([sys.executable, str(tool/'replay.py'), '--run', str(view), '--pdk-root',
                 str(a.pdk_root.resolve()), '--out', str(out/'replay'), '--reset-active'], 'replay')
        replay = json.loads((out/'replay/manifest.json').read_text())
        validate_replay(replay, selected_metrics(state['metrics']))
        for session in replay['sessions']:
            coverage = out/f"replay/{session['corner']}-{session['mode']}/coverage.rpt"
            if coverage.read_text().strip():
                raise ValueError('Incomplete constraint coverage: '+str(coverage))
        command(['openroad', '-no_init', '-exit', '-python', str(tool/'audit_clock_tree.py'),
                 '--odb', state['odb'], '--out', str(out/'clock_audit.json')], 'clock_audit')
        topology = json.loads((out/'clock_audit.json').read_text())['topology']
        if topology['clock_sink_count'] != 2421 or topology['clock_buffer_outputs_above8']:
            raise ValueError('Unexpected final clock sink count or overloaded clock buffer')
        inputs = [state_path, Path(state['odb']), Path(state['def']), template, *links.values()]
        manifest.update(status='complete', qualification='route only; full GDS qualification still required',
                        sha256={str(v): hashlib.sha256(v.read_bytes()).hexdigest() for v in inputs},
                        metrics=selected_metrics(state['metrics']), clock_topology=topology,
                        route_preservation=preservation,
                        boundary_and_all_43_signal_pin_geometries_unchanged=True)
    except Exception as exc:
        manifest.update(status='failed', error=str(exc))
        raise
    finally:
        (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print('PASS: strict route gate, nine STA sessions, coverage and final clock connectivity')


if __name__ == '__main__':
    main()
