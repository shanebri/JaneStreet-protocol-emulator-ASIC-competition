"""Inventory the pinned SRAM views; reject missing *exact* production corners.

This is a prerequisite check, never a physical/timing qualification. No library
is renamed, interpolated, or silently mapped to a different temperature.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

MACRO = "RM_IHPSG13_1P_64x16_c2"
PDK_REVISION = "2bbec755dc67ca3db0261c3d6163e15735d66710"
REQUIRED = {
    "nom_slow_1p08V_125C": (1.08, 125),
    "nom_typ_1p20V_25C": (1.20, 25),
    "nom_fast_1p32V_m40C": (1.32, -40),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect(pdk):
    root = pdk / "ihp-sg13cmos5l/libs.ref/sg13cmos5l_sram"
    views = {kind: root / kind / f"{MACRO}.{ext}" for kind, ext in
             (("lef", "lef"), ("gds", "gds"), ("cdl", "cdl"), ("verilog", "v"))}
    views["behavioral"] = root / "verilog/RM_IHPSG13_1P_core_behavioral.v"
    errors = [f"Missing view: {key}: {path}" for key, path in views.items() if not path.is_file()]
    provenance = subprocess.run(["git", "-C", str(pdk), "rev-parse", "HEAD"],
                                capture_output=True, text=True)
    revision = provenance.stdout.strip() if provenance.returncode == 0 else None
    if revision != PDK_REVISION:
        errors.append(f"Expected pinned PDK revision {PDK_REVISION}; found {revision}")
    changes = subprocess.run(["git", "-C", str(pdk), "status", "--porcelain", "--untracked-files=all",
                              "--", "ihp-sg13g2/libs.ref/sg13g2_sram",
                              "ihp-sg13cmos5l/libs.ref/sg13cmos5l_sram"], capture_output=True, text=True)
    if changes.returncode or changes.stdout.strip():
        errors.append("Cannot establish clean pinned SRAM views: " + changes.stdout.strip())
    libraries = []
    for path in sorted((root / "lib").glob(f"{MACRO}_*.lib")):
        text = path.read_text()
        voltage = re.search(r"\bnom_voltage\s*:\s*([-\d.]+)\s*;", text)
        temperature = re.search(r"\bnom_temperature\s*:\s*([-\d.]+)\s*;", text)
        corner = re.search(rf"{MACRO}_(slow|typ|fast)_", path.name)
        if not voltage or not temperature or not corner or not re.search(rf"\bcell\s*\(\s*{MACRO}\s*\)", text):
            errors.append(f"Malformed or wrong-cell library: {path}")
            continue
        libraries.append(dict(path=str(path), sha256=digest(path), process=corner[1],
                              voltage=float(voltage[1]), temperature=float(temperature[1])))
    selected = {}
    for corner, (voltage, temperature) in REQUIRED.items():
        process = corner.split("_")[1]
        matches = [v for v in libraries if (v["process"], v["voltage"], v["temperature"]) ==
                   (process, voltage, temperature)]
        if len(matches) != 1:
            errors.append(f"{corner}: expected one exact {process} / {voltage} V / {temperature} C library; found {len(matches)}")
        else:
            selected[corner] = matches[0]["path"]
    dimensions = None
    if views["lef"].is_file():
        text = views["lef"].read_text()
        size = re.search(r"\bSIZE\s+([\d.]+)\s+BY\s+([\d.]+)\s*;", text)
        if not size or tuple(map(float, size.groups())) != (236.8, 64.36):
            errors.append("Unexpected macro dimensions")
        else:
            dimensions = list(map(float, size.groups()))
        for pin in ("VDD!", "VDDARRAY!", "VSS!", "A_CLK", "A_MEN", "A_WEN", "A_REN", "A_DLY"):
            if not re.search(rf"\bPIN\s+{re.escape(pin)}\s", text):
                errors.append(f"Missing LEF pin: {pin}")
    return dict(status="blocked" if errors else "available", qualification="availability only; not physical signoff",
                pdk_revision=revision, macro=MACRO, capacity_bytes=128, organization="64x16", ports="one synchronous read/write port",
                dimensions_um=dimensions, power_pins=["VDD!", "VDDARRAY!", "VSS!"],
                views={k: dict(path=str(v), sha256=digest(v)) for k, v in views.items() if v.is_file()},
                libraries=libraries, exact_production_libraries=selected, errors=errors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdk-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.pdk_root.resolve())
    # Never overwrite earlier evidence from a different PDK or invocation.
    with args.out.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    for error in result["errors"]:
        print(error)
    print(result["status"].upper(), result["qualification"])
    return int(bool(result["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
