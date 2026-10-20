"""Portable alternative to make: python test/run.py (requires Icarus on PATH)."""
from pathlib import Path
import subprocess
from xml.etree import ElementTree
from cocotb_tools.runner import get_runner

ROOT = Path(__file__).resolve().parents[1]


def main():
    # Read the actual submission manifest so this runner cannot omit a source.
    source_list = (ROOT / "info.yaml").read_text().split("  source_files:\n", 1)[1]
    sources = []
    for line in source_list.splitlines():
        if not line.startswith("    - "):
            break
        sources.append(ROOT / "src" / line.split('"')[1])
    unit_output = ROOT / "test" / "sim_build" / "fifo.vvp"
    unit_output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["iverilog", "-g2012", "-s", "pio_fifo_tb", "-o", str(unit_output),
                    str(ROOT / "src" / "pio_fifo.sv"), str(ROOT / "test" / "pio_fifo_tb.sv")], check=True)
    subprocess.run(["vvp", str(unit_output)], check=True)
    for unit, modules in (("host_interface", ["host_interface"]), ("pio_pads", ["pio_pads"])):
        output = unit_output.parent / (unit + ".vvp")
        subprocess.run(["iverilog", "-g2012", "-Wall", "-Wno-timescale", "-s", unit+"_tb", "-o", str(output),
                        *[str(ROOT / "src" / (m+".sv")) for m in modules],
                        str(ROOT / "test" / (unit+"_tb.sv"))], check=True)
        subprocess.run(["vvp", str(output)], check=True)
    runner = get_runner("icarus")
    runner.build(
        sources=[*sources, ROOT / "test" / "tb.v"],
        hdl_toplevel="tb",
        build_dir=ROOT / "test" / "sim_build" / "rtl",
        build_args=["-Wall", "-Wno-timescale"],
        defines={"COCOTB_RUNNER": 1},
        always=True,
        timescale=("1ns", "1ps"),
        waves=True,
    )
    results = runner.test(
        hdl_toplevel="tb",
        test_module="test,test_pio21,test_i2c",
        test_dir=ROOT / "test",
        results_xml=ROOT / "test" / "results.xml",
        waves=True,
        plusargs=["+dumpfile_path=tb.fst"],
    )
    report = ElementTree.parse(results)
    assert report.findall(".//testcase"), "No tests ran"
    assert not report.findall(".//failure"), "RTL regression failed"
    assert not report.findall(".//error"), "RTL regression errored"


if __name__ == "__main__":
    main()
