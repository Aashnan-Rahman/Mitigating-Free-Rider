"""Report finished round-20 decisions; never select or tune a cutoff."""
import argparse
import csv
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path)
    args = parser.parse_args()
    print("run | round | FR: suspected/candidate/safe | honest: suspected/candidate/safe")
    for run in sorted(args.batch.iterdir()):
        if not run.is_dir():
            continue
        latest = run / "latest_results.json"
        if not latest.exists():
            continue
        round_index = json.loads(latest.read_text(encoding="utf-8")).get("latest_round", 0)
        summary = run / "preliminary_decision_summary.csv"
        rows = list(csv.DictReader(summary.open(newline="", encoding="utf-8"))) if summary.exists() else []
        if not rows:
            print(f"{run.name} | {round_index}/20 | pending | pending")
            continue
        groups = {row["population"]: row for row in rows}
        counts = ["/".join(groups[label][key] for key in ("suspected", "candidate", "safe"))
                  for label in ("free_rider", "honest")]
        print(f"{run.name} | {round_index}/20 | {counts[0]} | {counts[1]}")
    print("Suspected honest clients are provisional false positives; candidates are unresolved.")
    print("These runs do not remove or quarantine clients.")


if __name__ == "__main__":
    main()
