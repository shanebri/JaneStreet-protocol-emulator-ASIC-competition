"""Measured diagnostic tail from qualified-parent pre-final-repair state.

This is an inexpensive hypothesis screen, never a passing physical parent.
Any successful hypothesis still requires a new clean normal production run.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from check_signoff import find_state
from production_flow import LastFanoutRepair, PIOClosure, run_tool
from closure_trial import validate_config
from librelane.flows.classic import Classic


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--case", choices=("control", "hold", "host_drive", "host_clone", "host_buffer", "buffer_hold"), required=True)
    p.add_argument('--eco-only', action='store_true', help='Stop after mutation/audit/legalization; no timing claim')
    a = p.parse_args()
    repo, out = a.repo.resolve(), a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    base = repo/"test/sim_build/production_final_20261029_01/run"
    source = base/"56-openroad-lastfanoutrepair/state_in.json"
    raw = json.loads((base/"resolved.json").read_text())
    # Baseline config remains the source of all clocks, corners, budgets,
    # derates, physical geometry and execution settings.
    if a.case != "control":
        raw["PIO_INCREMENTAL_ECO_CONTRACTS"][1] = str(repo/"docs/timing/20261030-control-refactor"/(a.case+".json"))
    first = PIOClosure.Steps.index(LastFanoutRepair)
    last = next(i for i, step in enumerate(PIOClosure.Steps) if step.id == "OpenROAD.STAPostPNR")
    selected_steps = list(PIOClosure.Steps[first:last+1])
    if a.case == 'host_clone':
        from refactor_eco import render_script
        from librelane.state import DesignFormat
        class CloneRepair(LastFanoutRepair):
            def render_script(self, operations):
                return render_script(operations)
            def run(self, state_in, **kwargs):
                # Keep native target resolution, routing preservation and the
                # original audit for ordinary repair stages. Only this stage
                # needs the stronger replica-aware audit entry point.
                import production_flow
                previous = production_flow.run_tool
                def audited(step, name, arguments):
                    return previous(step, 'refactor_eco.py' if name == 'audit_data_eco.py' else name, arguments)
                production_flow.run_tool = audited
                try:
                    return super().run(state_in, **kwargs)
                finally:
                    production_flow.run_tool = previous
        selected_steps[0] = CloneRepair
    if a.eco_only:
        selected_steps = selected_steps[:1]
    validate_config(raw)
    if raw['OPENROAD_THREADS'] != 8 or raw['GRT_ADJUSTMENT'] != .25 or not raw['PL_TIMING_DRIVEN']:
        raise ValueError('Pinned execution settings changed')
    class Screen(Classic):
        Steps = selected_steps
        gating_config_vars = PIOClosure.gating_config_vars
    from librelane.config import Config
    from librelane.state import State
    variables = PIOClosure.get_all_config_variables(PIOClosure)
    # Keep the entire production config schema even though this run is a tail.
    names = {v.name for v in variables}
    config, _ = Config.load({k:v for k,v in raw.items() if k in names}, flow_config_vars=variables,
                            design_dir=raw["DESIGN_DIR"], pdk_root=raw["PDK_ROOT"], _load_pdk_configs=False)
    initial = State.loads(source.read_text())
    initial.validate()
    manifest = dict(status="running", case=a.case, scope="diagnostic physical tail; not production qualification",
                    source_state=str(source), source_state_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    changed_contract=raw["PIO_INCREMENTAL_ECO_CONTRACTS"][1])
    (out/"resolved_input.json").write_text(config.dumps())
    try:
        Screen(config).start(with_initial_state=initial, _force_run_dir=str(out/"run"))
        manifest["status"] = "mutation_audit_complete" if a.eco_only else "screen_complete"
    except Exception as exc:
        manifest.update(status="failed", error=str(exc))
        raise
    finally:
        try:
            state_path = find_state(out/"run")
        except (ValueError, FileNotFoundError):
            state_path = None
        if state_path:
            command = [sys.executable, str(repo/"tools/packet_sram/compare_timing.py"),
                       "--parent", str(repo/"docs/timing/20261030-control-refactor/qualified-parent/69-openroad-stapostpnr/state_out.json"),
                       "--candidate", str(state_path), "--out", str(out/"parent_comparison.json")]
            with (out/"parent_comparison.log").open("w") as log:
                result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
            manifest["parent_comparison_exit"] = result.returncode
            if result.returncode:
                manifest['status'] = 'rejected_parent_comparison'
            manifest["state"] = str(state_path)
        (out/"experiment.json").write_text(json.dumps(manifest, indent=2)+"\n")
    if manifest.get('parent_comparison_exit'):
        p.exit(1, 'Diagnostic candidate rejected by strict timing/electrical or no-regression checks\n')
    print("Diagnostic finished; no candidate promoted", out)


if __name__ == "__main__":
    main()
