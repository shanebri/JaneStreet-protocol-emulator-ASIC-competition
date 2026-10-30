"""Run existing pin-level regression on the frozen candidate with PDK models.

Adapt only the simulation model list/define in memory; frozen production inputs
are not edited. The macro synthesis black box is not a simulation model.
"""
import subprocess
import shutil
import sys
from pathlib import Path
import production_trial as trial

root = Path(sys.argv[1]).resolve() if len(sys.argv)>1 else trial.ROOT
for path in (trial.REPO / "tools").glob("*.py"):
    shutil.copy2(path, root / "tools" / path.name)
shutil.copytree(trial.REPO / "examples", root / "examples", dirs_exist_ok=True)
model = trial.PDK / "ihp-sg13cmos5l/libs.ref/sg13cmos5l_sram/verilog"
script = (root / "test/run.py").read_text()
marker = '    unit_output = ROOT / "test" / "sim_build" / "fifo.vvp"'
assert script.count(marker) == 1
script = script.replace(marker, f'    sources += [Path({str(model / "RM_IHPSG13_1P_64x16_c2.v")!r}), Path({str(model / "RM_IHPSG13_1P_core_behavioral.v")!r})]\n' + marker)
script = script.replace('defines={"COCOTB_RUNNER": 1}', 'defines={"COCOTB_RUNNER": 1, "FUNCTIONAL": 1}')
original = subprocess.run
def run(command, *args, **kwargs):
    if isinstance(command, list) and command[0] == "iverilog":
        command = [command[0], "-DFUNCTIONAL", *command[1:]]
    return original(command, *args, **kwargs)
subprocess.run = run
exec(compile(script, str(root / "test/run.py"), "exec"),
     {"__name__": "__main__", "__file__": str(root / "test/run.py")})
