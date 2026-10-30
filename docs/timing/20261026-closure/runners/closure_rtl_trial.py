"""Fresh matched RTL screens using timing-driven three-view placement and GRT .25."""
import argparse
import json
from pathlib import Path
import shutil

from check_signoff import REQUIRED_CORNERS
from implementation_trial import sha, template_fingerprint, validate_baseline
from physical_trial import final_gate, relocate


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('archive-root', 'pdk-root', 'design-root', 'template', 'out'):
        p.add_argument('--'+key, type=Path, required=True)
    p.add_argument('--trial', choices=('host_control', 'host_pending_word'), required=True)
    p.add_argument('--threads', type=int, default=8)
    a = p.parse_args()
    archive, pdk, design, template, out = (v.resolve() for v in
        (a.archive_root, a.pdk_root, a.design_root, a.template, a.out))
    if out.exists() or a.threads < 1:
        p.error('Require new output and positive thread count')
    original = json.loads((archive/'runs/wokwi/resolved.json').read_text())
    validate_baseline(original)
    if template_fingerprint(template.read_text()) != template_fingerprint(
            (archive/'runs/wokwi/27-odb-applydeftemplate/tt_um_shanebri_top.def').read_text()):
        p.error('8x4 die/signal template mismatch')
    from librelane.config import Config
    from librelane.flows.classic import Classic
    from librelane.steps.openroad import GlobalPlacement

    class PlacementViews(GlobalPlacement):
        def __init__(self, config, *args, **kwargs):
            super().__init__(config.copy(PNR_CORNERS=list(REQUIRED_CORNERS)), *args, **kwargs)

    last = next(i for i, s in enumerate(Classic.Steps) if s.id == 'OpenROAD.STAPostPNR')

    class Screen(Classic):
        Steps = [PlacementViews if s.id == 'OpenROAD.GlobalPlacement' else s for s in Classic.Steps[:last+1]]

    out.mkdir(parents=True)
    frozen = out/'frozen'
    shutil.copytree(design/'src', frozen/'src')
    shutil.copy2(design/'info.yaml', frozen/'info.yaml')
    shutil.copy2(template, frozen/'template.def')
    names = []
    for line in (design/'info.yaml').read_text().split('  source_files:\n', 1)[1].splitlines():
        if not line.startswith('    - '):
            break
        names.append(line.split('"')[1])
    raw = relocate(original, [(str(Path(original['DESIGN_DIR']).parent), str(archive)),
                              (original['PDK_ROOT'], str(pdk))])
    raw.update(PL_TIMING_DRIVEN=True, GRT_ADJUSTMENT=0.25, OPENROAD_THREADS=a.threads,
               DESIGN_DIR=str(frozen/'src'), FP_DEF_TEMPLATE=str(frozen/'template.def'),
               VERILOG_FILES=[str(frozen/'src'/name) for name in names])
    variables = Screen.get_all_config_variables(Screen)
    keys = {v.name for v in variables}
    config, _ = Config.load({k: v for k, v in raw.items() if k in keys}, flow_config_vars=variables,
                            design_dir=raw['DESIGN_DIR'], pdk_root=str(pdk), _load_pdk_configs=False)
    manifest = dict(trial=a.trial, status='running', scope='fresh_synthesis_post_route_screen',
        source_sha256={name: sha(frozen/'src'/name) for name in names},
        runner_sha256=sha(Path(__file__)), template_sha256=sha(template),
        resolved_config_sha256=sha(archive/'runs/wokwi/resolved.json'),
        changes={'PL_TIMING_DRIVEN': True, 'GRT_ADJUSTMENT': 0.25},
        step_overrides={'OpenROAD.GlobalPlacement': {'PNR_CORNERS': list(REQUIRED_CORNERS)}},
        execution_overrides={'OPENROAD_THREADS': a.threads})
    (out/'resolved_input.json').write_text(config.dumps())
    (out/'experiment.json').write_text(json.dumps(manifest, indent=2)+'\n')
    try:
        Screen(config).start(_force_run_dir=str(out/'run'))
        manifest['status'] = 'screen_complete'
    except Exception as exc:
        manifest.update(status='failed', error=str(exc))
        raise
    finally:
        manifest['signoff_exit'] = final_gate(out)
        if manifest['status'] == 'screen_complete' and manifest['signoff_exit']:
            manifest['status'] = 'rejected_signoff'
        (out/'experiment.json').write_text(json.dumps(manifest, indent=2)+'\n')
    if manifest['signoff_exit']:
        p.exit(1, 'Strict extracted signoff rejected this screen\n')


if __name__ == '__main__':
    main()
