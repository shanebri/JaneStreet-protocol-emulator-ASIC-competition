"""Functional checks for the frozen production candidate using PDK models."""
from pathlib import Path
import subprocess
import sys
import production_trial as trial

root = Path(sys.argv[1]).resolve() if len(sys.argv)>1 else trial.ROOT
models = trial.PDK / "ihp-sg13cmos5l/libs.ref/sg13cmos5l_sram/verilog"
macro_files = [models / "RM_IHPSG13_1P_64x16_c2.v", models / "RM_IHPSG13_1P_core_behavioral.v"]
sources = [root / "src" / line.split('"')[1] for line in
           (root / "info.yaml").read_text().split("  source_files:\n")[1].splitlines() if line.startswith("    - ")]
for name, tb in (("trial_portal_tb", trial.REPO / "tools/packet_sram/trial_portal_tb.sv"),
                 ("pio_subsystem_tb", root / "test/pio_subsystem_tb.sv")):
    binary = root / (name + ".vvp")
    with (root / (name + ".log")).open("x") as log:
        subprocess.run(["iverilog", "-g2012", "-DFUNCTIONAL", "-s", name, "-o", str(binary),
                        *map(str, sources + macro_files + [tb])], stdout=log, stderr=subprocess.STDOUT, check=True)
        subprocess.run(["vvp", "-N", str(binary)], stdout=log, stderr=subprocess.STDOUT, check=True)
    print((root / (name + ".log")).read_text())
