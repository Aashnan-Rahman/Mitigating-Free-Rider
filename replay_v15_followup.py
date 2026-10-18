"""Replay the first two full cycles; labels are evaluation-only, not scoring."""
import argparse
import csv
import json
from pathlib import Path

from server.v15_followup import CycleState, screen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path)
    args = parser.parse_args()
    total_free = total_honest = total_expected = 0
    for folder in sorted(args.batch.iterdir()):
        source = folder / "cycle_signals.csv"
        if not source.is_file():
            continue
        with source.open(newline="", encoding="utf-8") as handle:
            saved = [r for r in csv.DictReader(handle) if int(r["round"]) in (20, 30)]
        truth = {int(r["client_id"]): int(r["is_free_rider"]) for r in saved}
        state = CycleState(list(truth))
        for cycle, round_index in enumerate((20, 30)):
            public = []
            for r in saved:
                if int(r["round"]) != round_index:
                    continue
                row = {k: None if r[k] == "" else float(r[k])
                       for k in ("norm_z", "profile_z", "delta_norm", "profile_distance")}
                row.update(client_id=int(r["client_id"]), trap_id=int(r["trap_id"]),
                    exact_zero_delta=int(r["exact_zero_delta"]), exact_sendback=int(r["exact_sendback"]))
                public.append(row)
            decisions, _ = screen(public, round_index, state.confirmation_context())
            state.apply(decisions, cycle, round_index)
        removed = set(truth) - set(state.active)
        free = sum(truth[c] for c in removed)
        honest = sum(not truth[c] for c in removed)
        expected = sum(truth.values())
        total_free += free
        total_honest += honest
        total_expected += expected
        print(json.dumps(dict(run=folder.name, free_riders_confirmed=free,
                              expected_free_riders=expected, honest_confirmed=honest)))
    print(json.dumps(dict(total_free_rider_cases_confirmed=total_free,
                          total_free_rider_cases=total_expected, total_honest_cases_confirmed=total_honest)))
    print("Recorded first-two-cycle eligibility, not a guarantee of live rerun outcomes.")


if __name__ == "__main__":
    main()
