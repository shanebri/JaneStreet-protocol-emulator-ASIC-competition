"""Run the six independent diagnostic STA sessions in the original Linux/PDK environment.

Example: python3 tools/timing/replay.py --run /path/runs/wokwi --pdk-root /path/pdk
         --out /path/reports --reference
Omit --reference for candidate RTL. No constraint exceptions are installed.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess

from check_signoff import REQUIRED_CORNERS

BASELINE_SETUP = dict(zip(REQUIRED_CORNERS, (-5.885337, 2.427593, 7.069545)))
BASELINE_HOLD = dict(zip(REQUIRED_CORNERS, (0.646020, 0.301122, 0.112777)))


def unique(run, pattern):
    matches = list(run.glob(pattern))
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one {pattern} in {run}; found {len(matches)}")
    return matches[0]


def slack(path):
    match = re.search(r"^\s*worst slack\s+(?:(?:max|min)\s+)?(\S+)", path.read_text(), re.I | re.M)
    if not match:
        raise ValueError(f"Missing numeric worst slack in {path}")
    value = float(match[1])
    if not math.isfinite(value):
        raise ValueError(f"Non-finite worst slack in {path}")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--pdk-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sta", default="sta")
    parser.add_argument("--reference", action="store_true")
    parser.add_argument("--reset-active", action="store_true",
                        help="Also run diagnostic sessions with reset held low")
    parser.add_argument("--target", help="Rediscovered candidate endpoint pin (optional)")
    args = parser.parse_args()
    args.run = args.run.resolve()
    args.out = args.out.resolve()
    args.pdk_root = args.pdk_root.resolve()
    try:
        files = [unique(args.run, "*-openroad-fillinsertion/tt_um_shanebri_top.nl.v"),
                 unique(args.run, "*-openroad-rcx/nom/tt_um_shanebri_top.nom.spef"),
                 args.run / "final/sdc/tt_um_shanebri_top.sdc"]
        models = args.pdk_root / "ihp-sg13cmos5l/libs.ref"
        for std, io in (("slow_1p08V_125C", "slow_1p08V_3p0V_125C"),
                        ("typ_1p20V_25C", "typ_1p2V_3p3V_25C"),
                        ("fast_1p32V_m40C", "fast_1p32V_3p6V_m40C")):
            files += [models / f"sg13cmos5l_stdcell/lib/sg13cmos5l_stdcell_{std}.lib",
                      models / f"sg13cmos5l_io/lib/sg13cmos5l_io_{io}.lib"]
        script = Path(__file__).with_name("report_io_paths.tcl").resolve()
        files.append(script)
        hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        # Never mix reports from different invocations, or accept stale reports.
        args.out.mkdir(parents=True, exist_ok=False)
        manifest = {"sha256": hashes, "reference": args.reference, "status": "running", "sessions": []}
        (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        for corner in REQUIRED_CORNERS:
            for mode in (("baseline", "operational", "reset_active") if args.reset_active
                         else ("baseline", "operational")):
                output = args.out / f"{corner}-{mode}"
                env = dict(os.environ, PIO_TIMING_RUN=str(args.run), PDK_ROOT=str(args.pdk_root),
                           PIO_TIMING_CORNER=corner, PIO_TIMING_MODE=mode, PIO_TIMING_OUT=str(output),
                           PIO_TIMING_TARGET=args.target or ("_32168_/D" if args.reference else "none"))
                log = args.out / f"{corner}-{mode}.log"
                print(f"STA {corner} {mode}", flush=True)
                with log.open("w") as stream:
                    result = subprocess.run([args.sta, "-exit", str(script)], env=env,
                                            stdout=stream, stderr=subprocess.STDOUT)
                contents = log.read_text()
                if result.returncode or re.search(
                    r"(?im)^\s*(?:error\b|\[ERROR\])|^.*(?:unresolved|not linked|"
                    r"no liberty cell|does not have a model|not found).*$", contents
                ):
                    raise ValueError(f"STA execution failed; inspect {log}")
                setup = slack(output / "worst_setup.rpt")
                hold = slack(output / "worst_hold.rpt")
                manifest["sessions"].append(dict(corner=corner, mode=mode, setup=setup, hold=hold))
                (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
                if args.reference and mode == "baseline":
                    if abs(setup - BASELINE_SETUP[corner]) > 0.001 or abs(hold - BASELINE_HOLD[corner]) > 0.001:
                        raise ValueError(f"Reference slack mismatch at {corner}; resolve replay provenance")
        manifest["status"] = "complete"
        (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"Diagnostic matrix complete: {args.out}. Review coverage/electrical reports; this is not signoff.")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Replay failed: {exc}\n")


if __name__ == "__main__":
    main()
