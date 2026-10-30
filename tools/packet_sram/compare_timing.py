"""Reject any extracted setup/hold margin loss against a passing parent.

This additional numeric gate does not replace the production flow, matching
constraints/model audits, macro timing coverage, DRC, LVS, antenna or gate tests.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "timing"))
from check_signoff import REQUIRED_CORNERS, check_metrics, find_state
sys.path.pop(0)


def compare(parent, candidate):
    errors = ["parent: " + e for e in check_metrics(parent)]
    errors += ["candidate: " + e for e in check_metrics(candidate)]
    margins = {}
    for corner in REQUIRED_CORNERS:
        margins[corner] = {}
        for analysis in ("setup", "hold"):
            key = f"timing__{analysis}__ws__corner:{corner}"
            # Preserve measured headroom consumption even on a rejected route.
            values = (parent.get(key), candidate.get(key))
            if not all(type(v) in (int,float) and math.isfinite(v) for v in values):
                continue
            consumed = parent[key] - candidate[key]
            margins[corner][analysis] = dict(parent_ns=parent[key], candidate_ns=candidate[key],
                                             consumed_ns=consumed)
            if consumed > 0:
                errors.append(f"{corner} {analysis}: consumed {consumed:.12g} ns of headroom")
    return dict(status="rejected" if errors else "numeric_checks_pass",
                scope="timing/electrical comparison only; full physical qualification required",
                margins=margins, errors=errors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    parent, candidate = find_state(args.parent), find_state(args.candidate)
    result = compare(json.loads(parent.read_text())["metrics"], json.loads(candidate.read_text())["metrics"])
    result["sha256"] = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in (parent, candidate)}
    with args.out.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    for error in result["errors"]:
        print(error)
    print(result["status"], result["scope"])
    return int(bool(result["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
