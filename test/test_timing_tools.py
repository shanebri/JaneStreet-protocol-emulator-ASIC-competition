"""The release gate must reject missing corners and malformed/failed evidence."""
import importlib.util
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import sys

TOOLS = Path(__file__).resolve().parents[1] / "tools/timing"
spec = importlib.util.spec_from_file_location("check_signoff", TOOLS / "check_signoff.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
sys.path.insert(0, str(TOOLS))
import replay
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

    def test_ambiguous_or_missing_artifact_rejected(self):
        path = Mock()
        for matches in ([], [Path("a"), Path("b")]):
            path.glob.return_value = iter(matches)
            with self.assertRaises(ValueError):
                replay.unique(path, "pattern")
        path.glob.return_value = iter([Path("only")])
        self.assertEqual(replay.unique(path, "pattern"), Path("only"))


if __name__ == "__main__":
    unittest.main()
