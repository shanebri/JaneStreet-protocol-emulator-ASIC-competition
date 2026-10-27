"""The release gate must reject missing corners and malformed/failed evidence."""
import importlib.util
import math
import json
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import sys

TOOLS = Path(__file__).resolve().parents[1] / "tools/timing"
spec = importlib.util.spec_from_file_location("check_signoff", TOOLS / "check_signoff.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
sys.path.insert(0, str(TOOLS))
import replay
import physical_trial
import audit_nor_trial
import implementation_trial
import collect_implementation
import compare_implementation
import closure_trial
import check_net_geometry
import closure_collect
import audit_clock_tree
sys.path.pop(0)


def passing_metrics():
    metrics = {}
    for corner in gate.REQUIRED_CORNERS:
        for mode in ("setup", "hold"):
            metrics[f"timing__{mode}__ws__corner:{corner}"] = 0.1
            metrics[f"timing__{mode}__tns__corner:{corner}"] = 0
            metrics[f"timing__{mode}_vio__count__corner:{corner}"] = 0
        for kind in ("slew", "cap", "fanout"):
            metrics[f"design__max_{kind}_violation__count__corner:{corner}"] = 0
        metrics[f"timing__unannotated_net_filtered__count__corner:{corner}"] = 0
    for key in ("design__inferred_latch__count", "design__instance_unmapped__count",
                "synthesis__check_error__count"):
        metrics[key] = 0
    return metrics


class SignoffGateTests(unittest.TestCase):
    def test_complete_clean_evidence(self):
        self.assertEqual(gate.check_metrics(passing_metrics()), [])

    def test_each_check_is_required(self):
        for key in passing_metrics():
            with self.subTest(key=key):
                data = passing_metrics()
                del data[key]
                self.assertTrue(gate.check_metrics(data))

    def test_bad_values_fail_closed(self):
        for value in (None, "0", True, math.nan, math.inf, -math.inf):
            data = passing_metrics()
            data[f"timing__setup__ws__corner:{gate.REQUIRED_CORNERS[0]}"] = value
            self.assertTrue(gate.check_metrics(data), repr(value))

    def test_violations_in_every_corner(self):
        for key in passing_metrics():
            with self.subTest(key=key):
                data = passing_metrics()
                data[key] = -0.001 if "__ws__" in key or "__tns__" in key else 1
                self.assertTrue(gate.check_metrics(data))

    def test_wrong_stage_or_ambiguous_state_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                gate.find_state(root)
            for prefix in ("55", "56"):
                stage = root / f"{prefix}-openroad-stapostpnr"
                stage.mkdir()
                state = stage / "state_out.json"
                state.write_text("{}")
                self.assertEqual(gate.find_state(state), state)
                if prefix == "55":
                    self.assertEqual(gate.find_state(root), state)
            with self.assertRaises(ValueError):
                gate.find_state(root)
            wrong = root / "state_out.json"
            wrong.write_text("{}")
            with self.assertRaises(ValueError):
                gate.find_state(wrong)


class ReplayTests(unittest.TestCase):
    def test_signed_and_scientific_slack(self):
        for value in ("-5.885337", "+0.112777", "1.25e-5", "0"):
            path = Mock()
            path.read_text.return_value = "worst slack " + value + "\n"
            self.assertEqual(replay.slack(path), float(value))

    def test_missing_or_nonfinite_slack_rejected(self):
        for text in ("", "No paths", "worst slack inf", "worst slack nan", "worst slack broken"):
            path = Mock()
            path.read_text.return_value = text
            with self.assertRaises(ValueError):
                replay.slack(path)

    def test_opensta_27_analysis_label(self):
        for analysis, value in (("max", "-5.885337"), ("min", "+0.112777")):
            path = Mock()
            path.read_text.return_value = f"worst slack {analysis} {value}\n"
            self.assertEqual(replay.slack(path), float(value))

    def test_ambiguous_or_missing_artifact_rejected(self):
        path = Mock()
        for matches in ([], [Path("a"), Path("b")]):
            path.glob.return_value = iter(matches)
            with self.assertRaises(ValueError):
                replay.unique(path, "pattern")
        path.glob.return_value = iter([Path("only")])
        self.assertEqual(replay.unique(path, "pattern"), Path("only"))


class ReplayWorkflowTests(unittest.TestCase):
    """Exercise orchestration with a fake STA process, never claim physical STA."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / "run"
        self.out = self.root / "reports"
        self.pdk = self.root / "pdk"
        paths = [self.run / "42-openroad-fillinsertion/tt_um_shanebri_top.nl.v",
                 self.run / "43-openroad-rcx/nom/tt_um_shanebri_top.nom.spef",
                 self.run / "final/sdc/tt_um_shanebri_top.sdc"]
        for std, io_corner in (("slow_1p08V_125C", "slow_1p08V_3p0V_125C"),
                               ("typ_1p20V_25C", "typ_1p2V_3p3V_25C"),
                               ("fast_1p32V_m40C", "fast_1p32V_3p6V_m40C")):
            for family, suffix in (("stdcell", std), ("io", io_corner)):
                paths.append(self.pdk / "ihp-sg13cmos5l/libs.ref" /
                             f"sg13cmos5l_{family}/lib/sg13cmos5l_{family}_{suffix}.lib")
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture only\n")
        self.calls = []

    def fake_sta(self, command, *, env, stdout, stderr):
        self.calls.append(env)
        out = Path(env["PIO_TIMING_OUT"])
        out.mkdir()
        corner = env["PIO_TIMING_CORNER"]
        (out / "worst_setup.rpt").write_text(f"worst slack {replay.BASELINE_SETUP[corner]}\n")
        (out / "worst_hold.rpt").write_text(f"worst slack {replay.BASELINE_HOLD[corner]}\n")
        return Mock(returncode=0)

    def invoke(self, *extra, process=None):
        argv = ["replay", "--run", str(self.run), "--pdk-root", str(self.pdk),
                "--out", str(self.out), *extra]
        with patch.object(sys, "argv", argv), patch.object(replay.subprocess, "run",
                side_effect=process or self.fake_sta), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            replay.main()

    def test_complete_matrix_and_input_provenance(self):
        self.invoke()
        manifest = json.loads((self.out / "manifest.json").read_text())
        self.assertEqual(manifest["status"], "complete")
        self.assertEqual({(s["corner"], s["mode"]) for s in manifest["sessions"]},
                         {(c, m) for c in gate.REQUIRED_CORNERS for m in ("baseline", "operational")})
        self.assertEqual(len(self.calls), 6)
        self.assertEqual(len(manifest["sha256"]), 10)
        self.assertTrue(all(e["PIO_TIMING_TARGET"] == "none" for e in self.calls))

    def test_reference_reproduction_and_candidate_target(self):
        self.invoke("--reference")
        self.assertTrue(all(e["PIO_TIMING_TARGET"] == "_32168_/D" for e in self.calls))
        self.out = self.root / "candidate"
        self.calls.clear()
        self.invoke("--target", "_33839_/D")
        self.assertTrue(all(e["PIO_TIMING_TARGET"] == "_33839_/D" for e in self.calls))

    def test_reset_active_matrix_is_separate(self):
        self.invoke("--reset-active")
        self.assertEqual(len(self.calls), 9)
        self.assertEqual(sum(e["PIO_TIMING_MODE"] == "reset_active" for e in self.calls), 3)

    def test_existing_output_never_reused(self):
        self.out.mkdir()
        marker = self.out / "manifest.json"
        marker.write_text("old evidence")
        with self.assertRaises(SystemExit):
            self.invoke()
        self.assertEqual(marker.read_text(), "old evidence")
        self.assertEqual(self.calls, [])

    def test_missing_library_stops_before_launch(self):
        next(self.pdk.rglob("*.lib")).unlink()
        with self.assertRaises(SystemExit):
            self.invoke()
        self.assertEqual(self.calls, [])
        self.assertFalse(self.out.exists())

    def test_logged_error_or_nonzero_exit_cannot_complete(self):
        for index, (message, code) in enumerate((("Error: bad model", 0), ("", 1),
                                                ("cell does not have a model", 0))):
            with self.subTest(message=message, code=code):
                self.out = self.root / f"failed{index}"
                def failed(command, **kwargs):
                    self.fake_sta(command, **kwargs)
                    kwargs["stdout"].write(message)
                    return Mock(returncode=code)
                with self.assertRaises(SystemExit):
                    self.invoke(process=failed)
                manifest = json.loads((self.out / "manifest.json").read_text())
                self.assertNotEqual(manifest["status"], "complete")

    def test_reference_mismatch_cannot_complete(self):
        def mismatch(command, **kwargs):
            result = self.fake_sta(command, **kwargs)
            (Path(kwargs["env"]["PIO_TIMING_OUT"]) / "worst_setup.rpt").write_text("worst slack 0\n")
            return result
        with self.assertRaises(SystemExit):
            self.invoke("--reference", process=mismatch)
        manifest = json.loads((self.out / "manifest.json").read_text())
        self.assertNotEqual(manifest["status"], "complete")


class ImplementationTrialTests(unittest.TestCase):
    def test_closure_recipes_isolate_extraction_and_routing_parameters(self):
        self.assertEqual(closure_trial.plan('extract_control')['changes'], {})
        self.assertEqual(closure_trial.plan('extract_no_merge')['changes'], {'RCX_MERGE_VIA_WIRE_RES': False})
        self.assertEqual(closure_trial.plan('grt_capacity25')['changes'], {'GRT_ADJUSTMENT': 0.25})
        self.assertEqual(closure_trial.plan('route_seed43')['router_seed'], 43)
        with self.assertRaises(ValueError):
            closure_trial.plan('ignore_annotation')

    def test_closure_rejects_changed_timing_contract(self):
        raw={'CLOCK_PERIOD':20, 'PDK':'ihp-sg13cmos5l', 'STA_CORNERS':list(gate.REQUIRED_CORNERS)}
        for key in ('SETUP_VIOLATION_CORNERS','HOLD_VIOLATION_CORNERS',
                    'MAX_SLEW_VIOLATION_CORNERS','MAX_CAP_VIOLATION_CORNERS'):
            raw[key]=['*']
        closure_trial.validate_config(raw)
        for key,value in (('CLOCK_PERIOD',25),('STA_CORNERS',[]),('MAX_SLEW_VIOLATION_CORNERS',[])):
            with self.subTest(key=key), self.assertRaises(ValueError):
                closure_trial.validate_config(dict(raw,**{key:value}))

    def test_geometry_contact_includes_edges_but_not_gaps(self):
        self.assertTrue(check_net_geometry.touches((0,0,10,10),(10,2,20,8)))
        self.assertTrue(check_net_geometry.touches((0,0,10,10),(2,2,8,8)))
        self.assertFalse(check_net_geometry.touches((0,0,10,10),(11,0,20,10)))

    def test_replay_must_match_all_fresh_corners_and_modes(self):
        sessions = [dict(corner=c, mode=m, setup=0.1, hold=0.1) for c in gate.REQUIRED_CORNERS
                    for m in ('baseline', 'operational', 'reset_active')]
        collect_implementation.validate_replay({'status': 'complete', 'sessions': sessions}, passing_metrics())
        with self.assertRaises(ValueError):
            collect_implementation.validate_replay({'status': 'complete', 'sessions': sessions[:-1]+sessions[:1]}, passing_metrics())
        sessions[0]['setup'] = -6.8
        with self.assertRaises(ValueError):
            collect_implementation.validate_replay({'status': 'complete', 'sessions': sessions}, passing_metrics())

    def test_comparison_rejects_combined_knobs_or_mismatched_inputs(self):
        def manifest(name):
            return dict(implementation_trial.trial_plan(name), trial=name,
                        source_sha256={'a.sv': 'same'}, input_state_sha256='same',
                        resolved_config_sha256='same', execution_overrides={'OPENROAD_THREADS': 8})
        control, candidate = manifest('placement_control'), manifest('placement_timing')
        before, after = {'PL_TIMING_DRIVEN': False, 'PNR_CORNERS': None}, {'PL_TIMING_DRIVEN': True, 'PNR_CORNERS': None}
        compare_implementation.audit_pair(control, candidate, before, after)
        with self.assertRaises(ValueError):
            compare_implementation.audit_pair(control, candidate, before, dict(after, PNR_CORNERS=['slow']))
        with self.assertRaises(ValueError):
            compare_implementation.audit_pair(control, dict(candidate, input_state_sha256='different'), before, after)
        compare_implementation.audit_pair(candidate, manifest('placement_corners'), after, after)

    def test_collection_rejects_missing_or_invalid_measurements(self):
        metrics = passing_metrics()
        metrics.update({'design__instance__area__stdcell': 100,
                        'design__instance__utilization__stdcell': 0.3})
        self.assertEqual(collect_implementation.selected_metrics(metrics), metrics)
        for value in (None, True, math.inf, '0'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                collect_implementation.selected_metrics(dict(metrics, design__instance__area__stdcell=value))
        del metrics['design__instance__area__stdcell']
        with self.assertRaises(ValueError):
            collect_implementation.selected_metrics(metrics)

    def test_first_path_preserves_critical_endpoint_and_not_later_paths(self):
        report = ('Startpoint: a\nEndpoint: b\n -3.25 slack (VIOLATED)\n\n'
                  'Startpoint: c\nEndpoint: d\n 1.0 slack (MET)\n')
        self.assertEqual(collect_implementation.path_summary(report),
                         {'startpoint': 'a', 'endpoint': 'b', 'slack_ns': -3.25})
        self.assertEqual(collect_implementation.first_path(''), '')

    def test_independent_experiment_changes(self):
        control = implementation_trial.trial_plan('placement_control')
        timing = implementation_trial.trial_plan('placement_timing')
        corners = implementation_trial.trial_plan('placement_corners')
        self.assertEqual(control['input_stage'], timing['input_stage'])
        self.assertEqual(timing['input_stage'], corners['input_stage'])
        self.assertEqual(control['changes'], {})
        self.assertEqual(timing['changes'], {'PL_TIMING_DRIVEN': True})
        self.assertEqual(corners['changes'], timing['changes'])
        self.assertEqual(timing['step_overrides'], {})
        self.assertEqual(corners['step_overrides'], {'OpenROAD.GlobalPlacement':
                         {'PNR_CORNERS': list(gate.REQUIRED_CORNERS)}})
        for strategy in ('4', '0'):
            plan = implementation_trial.trial_plan('mapping_delay'+strategy)
            self.assertIsNone(plan['input_stage'])
            self.assertEqual(plan['changes'], {'SYNTH_STRATEGY': 'DELAY '+strategy})
            self.assertEqual(plan['step_overrides'], {})

    def test_changed_baseline_or_signoff_rejected(self):
        base = {'CLOCK_PERIOD': 20, 'PDK': 'ihp-sg13cmos5l', 'SYNTH_STRATEGY': 'AREA 0',
                'SYNTH_CORNER': None, 'PL_TIMING_DRIVEN': False, 'PNR_CORNERS': None,
                'STA_CORNERS': list(gate.REQUIRED_CORNERS)}
        for key in ('SETUP_VIOLATION_CORNERS', 'HOLD_VIOLATION_CORNERS',
                    'MAX_SLEW_VIOLATION_CORNERS', 'MAX_CAP_VIOLATION_CORNERS'):
            base[key] = ['*']
        implementation_trial.validate_baseline(base)
        for key, value in (('CLOCK_PERIOD', 25), ('SYNTH_STRATEGY', 'DELAY 4'),
                           ('PL_TIMING_DRIVEN', True), ('PNR_CORNERS', ['typ']),
                           ('STA_CORNERS', list(gate.REQUIRED_CORNERS)[1:]),
                           ('MAX_SLEW_VIOLATION_CORNERS', [])):
            with self.subTest(key=key), self.assertRaises(ValueError):
                implementation_trial.validate_baseline(dict(base, **{key: value}))

    def test_pin_audit_accepts_status_but_rejects_geometry_changes(self):
        pins = '\n'.join(f'- p{i} + NET p{i} + DIRECTION INPUT + USE SIGNAL '
                         '+ PORT + LAYER Metal4 ( -1 -2 ) ( 1 2 ) + PLACED ( 10 20 ) N ;'
                         for i in range(43))
        template = 'DIEAREA ( 0 0 ) ( 100 200 ) ; PINS 43 ;\n'+pins+'\nEND PINS'
        audit = implementation_trial.template_fingerprint
        self.assertEqual(audit(template), audit(template.replace('PLACED', 'FIXED')))
        self.assertNotEqual(audit(template), audit(template.replace('( 10 20 )', '( 11 20 )')))
        self.assertNotEqual(audit(template), audit(template.replace('( 100 200 )', '( 100 201 )')))
        with self.assertRaises(ValueError):
            audit('DIEAREA ( 0 0 ) ( 100 200 ) ; PINS 0 ; END PINS')


class NorTrialAuditTests(unittest.TestCase):
    def test_specialized_nor3_audit_and_rc_corner_keys(self):
        before = self.control.replace('_23246_', '_19177_').replace('nor4_', 'nor3_')
        after = before.replace('nor3_1', 'nor3_2')
        self.assertEqual(audit_nor_trial.audit(before, after, '_19177_',
            'sg13cmos5l_nor3_1', 'sg13cmos5l_nor3_2')['changed_instance'], '_19177_')
        for key in ('nom', 'nom_*'):
            self.assertEqual(closure_collect.nominal_view({key: '/tmp/c.spef'}), Path('/tmp/c.spef'))
        for corners in ({}, {'slow': '/tmp/a'}, {'nom': '/tmp/a', 'extra': '/tmp/b'}):
            with self.assertRaises(ValueError):
                closure_collect.nominal_view(corners)

    control = ('module top; wire n;\n'
               'sg13cmos5l_nor4_1 _23246_ (.A(a), .B(b), .C(c), .D(d), .Y(n));\n'
               'sg13cmos5l_buf_1 other (.A(n), .X(out));\nendmodule')
    candidate = control.replace('nor4_1', 'nor4_2').replace('.D(d), .Y(n)', '.Y(n), .D(d)')

    def test_drive_strength_only_with_reordered_ports(self):
        self.assertEqual(audit_nor_trial.audit(self.control, self.candidate)['instance_count'], 2)

    def test_rewiring_other_changes_and_missing_change_rejected(self):
        for candidate in (self.control, self.candidate.replace('.A(a)', '.A(b)'),
                          self.candidate.replace('buf_1', 'buf_2'),
                          self.candidate.replace('wire n;', 'wire n, added;'),
                          self.candidate.replace('_23246_', 'missing')):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                audit_nor_trial.audit(self.control, candidate)

    def test_different_or_missing_pdk_model_rejected(self):
        model = 'module sg13cmos5l_nor4_1(Y,A); not(Y,A); specify endspecify endmodule\n'
        pair = model + model.replace('nor4_1', 'nor4_2')
        audit_nor_trial.audit_models(pair)
        for bad in (model, pair.replace('nor4_2(Y,A); not(Y,A)', 'nor4_2(Y,A); buf(Y,A)')):
            with self.assertRaises(ValueError):
                audit_nor_trial.audit_models(bad)


class ClockInsertionAuditTests(unittest.TestCase):
    def fixture(self, split=False):
        cells = {'root': ('sg13cmos5l_buf_8', {'A': 'clk', 'X': 'branch'}),
                 'ff': ('sg13cmos5l_dfrbpq_1', {'CLK': 'leaf' if split else 'branch', 'D': 'data', 'Q': 'q'})}
        nets = {'clk', 'branch', 'data', 'q'}
        loads = {'clk': [('root', 'A')], 'branch': [('ff', 'CLK')]}
        if split:
            cells['clkbuf_fanoutfix_0'] = ('sg13cmos5l_buf_8', {'A': 'branch', 'X': 'leaf'})
            nets.add('leaf')
            loads['branch'] = [('clkbuf_fanoutfix_0', 'A')]
            loads['leaf'] = [('ff', 'CLK')]
        return cells, {'clk': 'clk'}, nets, loads, {('ff', 'CLK')}

    def test_ideal_buffer_preserves_signal_connectivity_and_clock_reachability(self):
        before, after = self.fixture(), self.fixture(True)
        self.assertEqual(audit_clock_tree.audit(before, after)['added_buffers'], 1)
        self.assertEqual(audit_clock_tree.audit(before, before)['added_buffers'], 0)
        self.assertEqual(audit_clock_tree.topology(before)['sink_buffer_depth_histogram'], {1: 1})
        self.assertEqual(audit_clock_tree.topology(after)['sink_buffer_depth_histogram'], {2: 1})

    def test_data_rewire_inversion_and_detached_clock_are_rejected(self):
        for failure in ('data', 'master', 'clock'):
            after = self.fixture(True)
            if failure == 'data':
                after[0]['ff'][1]['D'] = 'q'
            elif failure == 'master':
                after[0]['clkbuf_fanoutfix_0'] = ('sg13cmos5l_inv_8', {'A': 'branch', 'Y': 'leaf'})
            else:
                after[3]['leaf'] = []
            with self.subTest(failure=failure), self.assertRaises(ValueError):
                if failure == 'clock':
                    audit_clock_tree.topology(after)
                else:
                    audit_clock_tree.audit(self.fixture(), after)


class PhysicalTrialRelocationTests(unittest.TestCase):
    def test_nested_artifact_paths_relocated_without_changing_metrics(self):
        original = {"odb": "/runner/design/runs/39/design.odb",
                    "libraries": ["/runner/pdk/cells.lib"],
                    "metrics": {"timing__setup__ws": -6.809803, "count": 616},
                    "CLOCK_PERIOD": 20, "corners": ["slow", "typ", "fast"]}
        result = physical_trial.relocate(original,
                    [("/runner/design", "/local/design"), ("/runner/pdk", "/local/pdk")])
        self.assertEqual(result["odb"], "/local/design/runs/39/design.odb")
        self.assertEqual(result["libraries"], ["/local/pdk/cells.lib"])
        for key in ("metrics", "CLOCK_PERIOD", "corners"):
            self.assertEqual(result[key], original[key])
        self.assertEqual(original["odb"], "/runner/design/runs/39/design.odb")

    def test_trial_gate_requires_actual_postroute_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.assertNotEqual(physical_trial.final_gate(output), 0)
            state = output / 'run/55-openroad-stapostpnr/state_out.json'
            state.parent.mkdir(parents=True)
            state.write_text(json.dumps({'metrics': passing_metrics()}))
            self.assertEqual(physical_trial.final_gate(output), 0)
            metrics = passing_metrics()
            metrics[f'design__max_fanout_violation__count__corner:{gate.REQUIRED_CORNERS[0]}'] = 1
            state.write_text(json.dumps({'metrics': metrics}))
            self.assertNotEqual(physical_trial.final_gate(output), 0)
            self.assertIn('fanout', (output/'post_route_signoff.log').read_text())


if __name__ == "__main__":
    unittest.main()
