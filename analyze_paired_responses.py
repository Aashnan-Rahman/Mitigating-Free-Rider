"""Evaluation-only response summaries; never imported by server detection.

Reports distributions without choosing a detection threshold from outcomes.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import median, quantiles


def summarize(path: Path) -> dict:
    groups: dict[tuple[int, int], list[float]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["directional_gain"]:
                groups.setdefault((int(row["cycle"]), int(row["is_free_rider"])), []).append(
                    float(row["directional_gain"]))
    result = {"run": path.parent.name, "cycles": []}
    for cycle in sorted({key[0] for key in groups}):
        entry = {"cycle": cycle}
        for label, name in ((0, "honest"), (1, "attacker")):
            values = groups.get((cycle, label), [])
            if values:
                entry[name] = {"count": len(values), "median": median(values),
                               "quartiles": quantiles(values, n=4, method="inclusive")
                               if len(values) > 1 else [values[0]] * 3,
                               "min": min(values), "max": max(values)}
        result["cycles"].append(entry)
    return result


def summarize_shadow(path: Path) -> dict:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    scored = {int(row["client_id"]): row for row in rows if row["score"]}
    proposals = {int(row["client_id"]) for row in rows if row["proposed_remove"] == "1"}
    result = {"run": path.parent.name, "scored_clients": len(scored),
              "enforced": any(row["enforced"] != "0" for row in rows),
              "calibration_fingerprints": sorted({row["calibration_fingerprint"] for row in rows})}
    for label, name in (("0", "honest"), ("1", "attacker")):
        ids = {client for client, row in scored.items() if row["is_free_rider"] == label}
        result[name] = {"scored": len(ids), "proposed": len(ids & proposals),
                        "not_proposed": len(ids - proposals)}
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path)
    parser.add_argument("--shadow", action="store_true", help="Report shadow proposals separately from actual removals")
    args = parser.parse_args()
    filename = "paired_shadow_decisions.csv" if args.shadow else "paired_responses.csv"
    analyze = summarize_shadow if args.shadow else summarize
    print(json.dumps([analyze(path) for path in sorted(args.batch.glob("*/" + filename))], indent=2))
