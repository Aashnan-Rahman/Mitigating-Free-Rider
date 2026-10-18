"""Read-only replay of evidence eligibility; not counterfactual training metrics."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from server.v15_evidence import screen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path)
    args = parser.parse_args()
    for folder in sorted(args.batch.iterdir()):
        source = folder / "cycle_signals.csv"
        if not source.is_file():
            continue
        with source.open(newline="", encoding="utf-8") as handle:
            saved = list(csv.DictReader(handle))
        truth, groups = {}, {}
        for row in saved:
            client = int(row["client_id"])
            truth[client] = int(row["is_free_rider"])
            public = {key: None if row[key] == "" else float(row[key])
                      for key in ("norm_z", "profile_z", "delta_norm", "profile_distance")}
            public.update(client_id=client, trap_id=int(row["trap_id"]),
                exact_zero_delta=int(row["exact_zero_delta"]), exact_sendback=int(row["exact_sendback"]))
            groups.setdefault(int(row["round"]), []).append(public)
        previous, early = {}, []
        later_events = 0
        for index, public in groups.items():
            if {r["trap_id"] for r in public} != {0, 1}:
                continue
            decisions, _ = screen(public, index)
            counts = Counter(("FR" if truth[d["client_id"]] else "H") + "_" + d["state"] for d in decisions)
            confirmations = Counter("FR" if truth[d["client_id"]] else "H" for d in decisions
                if set(filter(None, d["strong_channels"].split(","))) & previous.get(d["client_id"], set()))
            if index in (20, 30):
                early.append(dict(round=index, counts=dict(counts), confirmable=dict(confirmations)))
            if index > 30:
                later_events += confirmations["H"]
            previous = {d["client_id"]: set(filter(None, d["strong_channels"].split(","))) for d in decisions}
        print(json.dumps(dict(run=folder.name, early=early, later_honest_confirmation_events=later_events)))
    print("Old trajectories only: the revised aggregation/schedule will change a live rerun.")


if __name__ == "__main__":
    main()
