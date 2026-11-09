"""Portable alternative to make: python test/run.py (requires Icarus on PATH)."""
import argparse
from pathlib import Path
import subprocess
import sys
from xml.etree import ElementTree
from cocotb_tools.runner import get_runner

ROOT = Path(__file__).resolve().parents[1]


def run_units(sources):
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "test"),
                    "-p", "test_timing_tools.py"], check=True)
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "test"),
                    "-p", "test_headroom_campaign.py"], check=True)
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "test"),
                    "-p", "test_pio_host.py"], check=True)
    unit_output = ROOT / "test" / "sim_build" / "fifo.vvp"
    unit_output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["iverilog", "-g2012", "-s", "pio_fifo_tb", "-o", str(unit_output),
                    str(ROOT / "src" / "pio_fifo.sv"), str(ROOT / "test" / "pio_fifo_tb.sv")], check=True)
    subprocess.run(["vvp", str(unit_output)], check=True)
    output = unit_output.parent / "frontend_timing.vvp"
    subprocess.run(["iverilog", "-g2012", "-Wall", "-Wno-timescale", "-s", "frontend_timing_tb",
                    "-o", str(output), str(ROOT / "src/frontend/pc.sv"),
                    str(ROOT / "src/frontend/instruction_fetch.sv"),
                    str(ROOT / "test/frontend_timing_tb.sv")], check=True)
    subprocess.run(["vvp", str(output)], check=True)
    for unit, modules in (("host_interface", ["host_interface"]), ("pio_pads", ["pio_pads"])):
        output = unit_output.parent / (unit + ".vvp")
        subprocess.run(["iverilog", "-g2012", "-Wall", "-Wno-timescale", "-s", unit+"_tb", "-o", str(output),
                        *[str(ROOT / "src" / (m+".sv")) for m in modules],
                        str(ROOT / "test" / (unit+"_tb.sv"))], check=True)
        subprocess.run(["vvp", str(output)], check=True)
    output = unit_output.parent / "pio_subsystem.vvp"
    subprocess.run(["iverilog", "-g2012", "-Wall", "-Wno-timescale", "-s", "pio_subsystem_tb",
                    "-o", str(output), *map(str, sources),
                    str(ROOT / "test" / "pio_subsystem_tb.sv")], check=True)
    subprocess.run(["vvp", str(output)], check=True)
    output = unit_output.parent / "io_timing.vvp"
    subprocess.run(["iverilog", "-g2012", "-Wall", "-Wno-timescale", "-s", "io_timing_tb",
                    "-o", str(output), *map(str, sources),
                    str(ROOT / "test" / "reference" / "io_timing_37c74dc.v"),
                    str(ROOT / "test" / "io_timing_tb.sv")], check=True)
    subprocess.run(["vvp", str(output)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--isa-reference", action="store_true", help="run only the RTL ISA differential suite")
    args = parser.parse_args()
    # Read the actual submission manifest so this runner cannot omit a source.
    source_list = (ROOT / "info.yaml").read_text().split("  source_files:\n", 1)[1]
    sources = []
    for line in source_list.splitlines():
        if not line.startswith("    - "):
            break
        sources.append(ROOT / "src" / line.split('"')[1])

    test_dir = ROOT / "test"
    if args.isa_reference:
        build_dir = test_dir / "sim_build" / "isa_reference"
        modules, results_xml = "test_pio_reference", build_dir / "results.xml"
        dumpfile = (build_dir / "tb.fst").as_posix()
    else:
        run_units(sources)
        build_dir = test_dir / "sim_build" / "rtl"
        modules, results_xml = "test,test_pio21,test_i2c,test_dual_pio", test_dir / "results.xml"
        dumpfile = "tb.fst"
    runner = get_runner("icarus")
    runner.build(
        sources=[*sources, ROOT / "test" / "tb.v"],
        hdl_toplevel="tb",
        build_dir=build_dir,
        build_args=["-Wall", "-Wno-timescale"],
        defines={"COCOTB_RUNNER": 1},
        always=True,
        timescale=("1ns", "1ps"),
        waves=True,
    )
    results = runner.test(
        hdl_toplevel="tb",
        test_module=modules,
        test_dir=test_dir,
        results_xml=results_xml,
        waves=True,
        plusargs=[f"+dumpfile_path={dumpfile}"],
    )
    report = ElementTree.parse(results)
    assert any(case.find("skipped") is None for case in report.findall(".//testcase")), "No tests ran"
    assert not report.findall(".//failure"), "RTL regression failed"
    assert not report.findall(".//error"), "RTL regression errored"


if __name__ == "__main__":
    main()
