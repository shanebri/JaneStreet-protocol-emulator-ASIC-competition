"""The prerequisite gate must not accept relabeled or incomplete SRAM views."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

spec = importlib.util.spec_from_file_location("packet_macro", Path(__file__).resolve().parents[1] /
                                            "tools/packet_sram/check_macro.py")
macro = importlib.util.module_from_spec(spec)
spec.loader.exec_module(macro)
timing_spec = importlib.util.spec_from_file_location("packet_compare", Path(__file__).resolve().parents[1] /
                                                   "tools/packet_sram/compare_timing.py")
timing = importlib.util.module_from_spec(timing_spec)
timing_spec.loader.exec_module(timing)


class MacroAvailabilityTests(unittest.TestCase):
    def fixture(self, root, fast_temperature=-40):
        base = root / "ihp-sg13cmos5l/libs.ref/sg13cmos5l_sram"
        for kind, extension in (("lef", "lef"), ("gds", "gds"), ("cdl", "cdl"), ("verilog", "v")):
            (base / kind).mkdir(parents=True)
            (base / kind / f"{macro.MACRO}.{extension}").write_text("fixture")
        (base / "verilog/RM_IHPSG13_1P_core_behavioral.v").write_text("fixture")
        (base / "lef" / f"{macro.MACRO}.lef").write_text(
            "SIZE 236.8 BY 64.36 ;\n" + "\n".join(f"PIN {p} DIRECTION INPUT ;" for p in
                ("VDD!", "VDDARRAY!", "VSS!", "A_CLK", "A_MEN", "A_WEN", "A_REN", "A_DLY")))
        (base / "lib").mkdir()
        for corner, (voltage, temperature) in macro.REQUIRED.items():
            process = corner.split("_")[1]
            if process == "fast":
                temperature = fast_temperature
            (base / "lib" / f"{macro.MACRO}_{corner[4:]}.lib").write_text(
                f"nom_voltage : {voltage}; nom_temperature : {temperature}; cell({macro.MACRO}) {{}}")
        return base

    def inspect(self, root):
        with patch.object(macro.subprocess, "run", side_effect=[
            Mock(returncode=0, stdout=macro.PDK_REVISION), Mock(returncode=0, stdout="")]):
            return macro.inspect(root)

    def test_complete_availability_is_not_signoff(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            result = self.inspect(root)
            self.assertEqual(result["status"], "available")
            self.assertIn("not physical signoff", result["qualification"])

    def test_relabeling_minus55_as_minus40_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root, -55)
            result = self.inspect(root)
            self.assertEqual(result["status"], "blocked")
            self.assertNotIn("nom_fast_1p32V_m40C", result["exact_production_libraries"])

    def test_missing_physical_view_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base = self.fixture(root)
            (base / "gds" / f"{macro.MACRO}.gds").unlink()
            self.assertEqual(self.inspect(root)["status"], "blocked")

    def test_unverified_pdk_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            with patch.object(macro.subprocess, "run", return_value=Mock(returncode=1, stdout="")):
                self.assertEqual(macro.inspect(root)["status"], "blocked")


class TimingComparisonTests(unittest.TestCase):
    def metrics(self):
        data = {}
        for corner in timing.REQUIRED_CORNERS:
            for analysis in ("setup", "hold"):
                data[f"timing__{analysis}__ws__corner:{corner}"] = .3
                data[f"timing__{analysis}__tns__corner:{corner}"] = 0
                data[f"timing__{analysis}_vio__count__corner:{corner}"] = 0
            for kind in ("slew", "cap", "fanout"):
                data[f"design__max_{kind}_violation__count__corner:{corner}"] = 0
            data[f"timing__unannotated_net_filtered__count__corner:{corner}"] = 0
        for key in ("design__inferred_latch__count", "design__instance_unmapped__count", "synthesis__check_error__count"):
            data[key] = 0
        return data

    def test_equal_and_improved_margins_pass_numeric_gate(self):
        parent, candidate = self.metrics(), self.metrics()
        self.assertEqual(timing.compare(parent, candidate)["status"], "numeric_checks_pass")
        candidate[f"timing__hold__ws__corner:{timing.REQUIRED_CORNERS[0]}"] = .4
        result = timing.compare(parent, candidate)
        self.assertEqual(result["status"], "numeric_checks_pass")
        self.assertAlmostEqual(result["margins"][timing.REQUIRED_CORNERS[0]]["hold"]["consumed_ns"], -.1)

    def test_positive_slack_regression_is_rejected_in_each_corner(self):
        for corner in timing.REQUIRED_CORNERS:
            for analysis in ("setup", "hold"):
                parent, candidate = self.metrics(), self.metrics()
                candidate[f"timing__{analysis}__ws__corner:{corner}"] -= .000001
                self.assertEqual(timing.compare(parent, candidate)["status"], "rejected")

    def test_new_electrical_error_is_rejected(self):
        parent, candidate = self.metrics(), self.metrics()
        candidate[f"design__max_slew_violation__count__corner:{timing.REQUIRED_CORNERS[0]}"] = 1
        self.assertEqual(timing.compare(parent, candidate)["status"], "rejected")

    def test_rejected_route_still_reports_measured_headroom(self):
        parent, candidate = self.metrics(), self.metrics()
        corner = timing.REQUIRED_CORNERS[0]
        candidate[f"timing__setup__ws__corner:{corner}"] = -.2
        candidate[f"design__max_cap_violation__count__corner:{corner}"] = 1
        result = timing.compare(parent,candidate)
        self.assertEqual(result["status"],"rejected")
        self.assertAlmostEqual(result["margins"][corner]["setup"]["consumed_ns"],.5)

    def test_failing_or_missing_parent_is_rejected(self):
        self.assertEqual(timing.compare({}, self.metrics())["status"], "rejected")
        parent = self.metrics()
        parent[f"timing__hold__ws__corner:{timing.REQUIRED_CORNERS[0]}"] = -.01
        self.assertEqual(timing.compare(parent, self.metrics())["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
