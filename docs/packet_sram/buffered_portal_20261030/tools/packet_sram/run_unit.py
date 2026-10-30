"""Exercise the isolated packet SRAM against the installed PDK's real model."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdk-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    model = args.pdk_root / "ihp-sg13cmos5l/libs.ref/sg13cmos5l_sram/verilog"
    args.out.mkdir(parents=True, exist_ok=False)
    binary = args.out / "packet_sram.vvp"
    files = [repo / "src/packet/packet_sram.sv", model / "RM_IHPSG13_1P_64x16_c2.v",
             model / "RM_IHPSG13_1P_core_behavioral.v", repo / "test/packet_sram_tb.sv"]
    manifest = dict(status="running", scope="isolated functional model test; no physical qualification",
                    sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    commands = [["iverilog", "-g2012", "-DFUNCTIONAL", "-Wall", "-Wno-timescale",
                    "-s", "packet_sram_tb", "-o", str(binary),
                    *map(str, files)], ["vvp", "-N", str(binary)]]
    manifest["commands"] = commands
    try:
        for name, command in zip(("compile", "simulation"), commands):
            result = subprocess.run(command, capture_output=True, text=True)
            (args.out / (name + ".log")).write_text(result.stdout + result.stderr)
            print(result.stdout + result.stderr, end="")
            result.check_returncode()
            if name == "simulation" and "PASS packet SRAM:" not in result.stdout:
                raise RuntimeError("Simulation did not reach its passing result")
        manifest["status"] = "pass"
    except Exception as exc:
        manifest.update(status="failed", error=str(exc))
        raise
    finally:
        (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
