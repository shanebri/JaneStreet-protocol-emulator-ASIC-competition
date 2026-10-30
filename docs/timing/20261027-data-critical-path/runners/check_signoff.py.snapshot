"""Fail closed on the three required post-route corners in LibreLane state.

Usage: python tools/timing/check_signoff.py runs/wokwi
Accepts a run directory or a specific post-route STA state_out.json. This gate
does not replace the independent per-port/register reports or DRC/LVS checks.
"""
import argparse
import json
import math
from pathlib import Path

REQUIRED_CORNERS = ("nom_slow_1p08V_125C", "nom_typ_1p20V_25C", "nom_fast_1p32V_m40C")


def check_metrics(metrics):
    failures = []

    def require(key, minimum=0, maximum=0):
        value = metrics.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            failures.append(f"{key}: missing or non-finite numeric result ({value!r})")
        elif value < minimum or value > maximum:
            failures.append(f"{key}: {value} outside [{minimum}, {maximum}]")

    for corner in REQUIRED_CORNERS:
        for analysis in ("setup", "hold"):
            # WS retains positive margin; WNS alone would conceal it.
            require(f"timing__{analysis}__ws__corner:{corner}", maximum=math.inf)
            require(f"timing__{analysis}__tns__corner:{corner}")
            require(f"timing__{analysis}_vio__count__corner:{corner}")
        for kind in ("slew", "cap", "fanout"):
            require(f"design__max_{kind}_violation__count__corner:{corner}")
        require(f"timing__unannotated_net_filtered__count__corner:{corner}")
    for key in ("design__inferred_latch__count", "design__instance_unmapped__count",
                "synthesis__check_error__count"):
        require(key)
    return failures


def find_state(path):
    if path.is_file():
        if path.name != "state_out.json" or not path.parent.name.endswith("-openroad-stapostpnr"):
            raise ValueError("Expected post-route *-openroad-stapostpnr/state_out.json")
        return path
    matches = list(path.glob("*-openroad-stapostpnr/state_out.json"))
    if len(matches) != 1:
        raise ValueError(f"Expected one completed post-route STA state in {path}; found {len(matches)}")
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    try:
        state = find_state(args.run)
        data = json.loads(state.read_text())
        if not isinstance(data, dict) or not isinstance(data.get("metrics"), dict):
            raise ValueError("Expected a post-route state with a metrics object")
        failures = check_metrics(data["metrics"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"Signoff evidence error: {exc}\n")
    if failures:
        parser.exit(1, "Post-route signoff FAILED:\n" + "\n".join(f"  {item}" for item in failures) + "\n")
    print(f"PASS: setup/hold, slew/cap/fanout, annotation and structural metrics in all three corners ({state})")


if __name__ == "__main__":
    main()
