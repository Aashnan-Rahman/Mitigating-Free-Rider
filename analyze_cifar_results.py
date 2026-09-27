from __future__ import annotations

import csv
import argparse
import json
import statistics
from pathlib import Path
from typing import Any


RESULTS_ROOT = Path("results")
BATCHES = (
    RESULTS_ROOT / "cifar10_iid_fr40_seed42",
    RESULTS_ROOT / "cifar10_noniid_fr40_seed43",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def number(row: dict[str, str], key: str, default: float = 0.0) -> float:
    value = row.get(key, "")
    return float(value) if value not in (None, "") else default


def summarize_run(run_dir: Path) -> dict[str, Any]:
    config = json.loads((run_dir / "run_config.json").read_text(encoding="utf-8"))
    metrics = read_csv(run_dir / "global_metrics.csv")
    removals = read_csv(run_dir / "removals.csv")
    detection = read_csv(run_dir / "detection_summary.csv")[0]
    by_round = {int(row["round"]): row for row in metrics}
    free_rider_rounds = [
        int(row["round"]) for row in removals if int(row["is_free_rider"]) == 1
    ]
    honest_rounds = [
        int(row["round"]) for row in removals if int(row["is_free_rider"]) == 0
    ]
    accuracies = [number(row, "global_accuracy") for row in metrics]
    round_times = [number(row, "round_time_seconds") for row in metrics]

    def accuracy_at(round_idx: int) -> float | None:
        row = by_round.get(round_idx)
        return number(row, "global_accuracy") if row else None

    def first_accuracy_round(threshold: float) -> int | None:
        for row in metrics:
            if number(row, "global_accuracy") >= threshold:
                return int(row["round"])
        return None

    return {
        "distribution": config["distribution"],
        "seed": int(config["seed"]),
        "attack": config["attack_type"],
        "rounds": len(metrics),
        "final_accuracy": float(config["final_global_accuracy"]),
        "best_accuracy": float(config["best_global_accuracy"]),
        "mean_accuracy": statistics.fmean(accuracies),
        "final_loss": float(config["final_global_loss"]),
        "accuracy_r10": accuracy_at(10),
        "accuracy_r30": accuracy_at(30),
        "accuracy_r50": accuracy_at(50),
        "accuracy_r100": accuracy_at(100),
        "round_reached_50pct": first_accuracy_round(0.50),
        "round_reached_60pct": first_accuracy_round(0.60),
        "round_reached_70pct": first_accuracy_round(0.70),
        "removed_free_riders": int(detection["removed_free_riders"]),
        "removed_honest_clients": int(detection["removed_honest_clients"]),
        "missed_free_riders": int(detection["missed_free_riders"]),
        "precision": float(detection["precision"]),
        "recall": float(detection["recall"]),
        "f1": float(detection["f1"]),
        "detection_accuracy": float(detection["detection_accuracy"]),
        "false_positive_removal_rate": float(detection["false_positive_removal_rate"]),
        "first_free_rider_removal_round": min(free_rider_rounds) if free_rider_rounds else None,
        "median_free_rider_removal_round": (
            statistics.median(free_rider_rounds) if free_rider_rounds else None
        ),
        "last_free_rider_removal_round": max(free_rider_rounds) if free_rider_rounds else None,
        "first_honest_removal_round": min(honest_rounds) if honest_rounds else None,
        "mean_round_seconds": statistics.fmean(round_times),
        "metric_wall_hours": sum(round_times) / 3600.0,
        "peak_rss_mb": float(config["peak_process_rss_mb"]),
        "resumed": config.get("resume_checkpoint") is not None,
        "run_dir": str(run_dir),
    }


def fmt_percent(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:.2f}%"


def fmt_round(value: float | int | None) -> str:
    return "n/a" if value is None else f"{value:g}"


def markdown_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Distribution | Seed | Attack | Final acc. | Best acc. | F1 | Precision | Recall | FR removed | Honest removed | Removal rounds (first/median/last) | Hours |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|---:|",
    ]
    for row in rows:
        removal = "/".join(
            fmt_round(row[key])
            for key in (
                "first_free_rider_removal_round",
                "median_free_rider_removal_round",
                "last_free_rider_removal_round",
            )
        )
        lines.append(
            "| {distribution} | {seed} | {attack} | {final} | {best} | {f1} | "
            "{precision} | {recall} | {removed_fr} | {removed_honest} | {removal} | {hours:.2f} |".format(
                distribution=row["distribution"],
                seed=row["seed"],
                attack=row["attack"],
                final=fmt_percent(row["final_accuracy"]),
                best=fmt_percent(row["best_accuracy"]),
                f1=fmt_percent(row["f1"]),
                precision=fmt_percent(row["precision"]),
                recall=fmt_percent(row["recall"]),
                removed_fr=row["removed_free_riders"],
                removed_honest=row["removed_honest_clients"],
                removal=removal,
                hours=row["metric_wall_hours"],
            )
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze completed CIFAR-10 batches.")
    parser.add_argument("--batches", nargs="+", type=Path, default=list(BATCHES))
    parser.add_argument("--output-dir", type=Path, default=RESULTS_ROOT)
    args = parser.parse_args()
    rows: list[dict[str, Any]] = []
    for batch in args.batches:
        if not batch.is_dir():
            raise FileNotFoundError(batch)
        for run_dir in sorted(batch.iterdir()):
            latest_path = run_dir / "latest_results.json"
            if (run_dir / "run_config.json").is_file() and latest_path.is_file() and json.loads(latest_path.read_text(encoding="utf-8")).get("completed"):
                rows.append(summarize_run(run_dir))
    if not rows:
        raise FileNotFoundError("No completed CIFAR-10 result directories were found.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.output_dir / "cifar10_analytics_summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    best_accuracy = max(rows, key=lambda row: row["final_accuracy"])
    best_detection = max(rows, key=lambda row: (row["f1"], row["precision"]))
    distribution_means = {
        distribution: {
            "final_accuracy": statistics.fmean(
                row["final_accuracy"] for row in rows if row["distribution"] == distribution
            ),
            "f1": statistics.fmean(
                row["f1"] for row in rows if row["distribution"] == distribution
            ),
            "honest_removed": sum(
                row["removed_honest_clients"]
                for row in rows
                if row["distribution"] == distribution
            ),
        }
        for distribution in sorted({row["distribution"] for row in rows})
    }
    by_key = {(row["distribution"], row["attack"], row["seed"]): row for row in rows}
    comparison_lines = []
    for attack, seed in sorted({(row['attack'], row['seed']) for row in rows}):
        iid = by_key.get(("iid", attack, seed))
        noniid = by_key.get(("noniid", attack, seed))
        if iid and noniid:
            comparison_lines.append(
                f"- {attack}, seed {seed}: non-IID minus IID final accuracy "
                f"{100 * (noniid['final_accuracy'] - iid['final_accuracy']):+.2f} pp; "
                f"F1 {100 * (noniid['f1'] - iid['f1']):+.2f} pp; "
                f"honest removals {noniid['removed_honest_clients'] - iid['removed_honest_clients']:+d}."
            )

    report = f"""# CIFAR-10 Result Analytics

Analyzed {len(rows)} completed runs from {', '.join(str(path) for path in args.batches)}.
Seeds: {', '.join(str(seed) for seed in sorted({row['seed'] for row in rows}))}.
Comparisons below match attack and seed. These are descriptive results, not causal estimates.

## Run summary

{markdown_table(rows)}

## Main findings

- Highest final global accuracy: {best_accuracy['distribution']} {best_accuracy['attack']} at {fmt_percent(best_accuracy['final_accuracy'])}.
- Strongest final detection: {best_detection['distribution']} {best_detection['attack']} with F1 {fmt_percent(best_detection['f1'])} and precision {fmt_percent(best_detection['precision'])}.
- Total free riders removed across runs: {sum(row['removed_free_riders'] for row in rows)}; total missed: {sum(row['missed_free_riders'] for row in rows)}.
{chr(10).join(f"- {distribution}: mean final accuracy {fmt_percent(values['final_accuracy'])}; mean F1 {fmt_percent(values['f1'])}; total honest removals {values['honest_removed']}." for distribution, values in distribution_means.items())}
- Runtime is reconstructed from per-round metrics, because a resumed process's `total_wall_clock_seconds` only covers its final process segment.

## Attack-matched IID vs non-IID differences

{chr(10).join(comparison_lines)}

## Interpretation limits

- Results from a single seed do not establish robustness. More seeds are required for uncertainty estimates or claims about generalization.
- There is no no-attack baseline in these two batches, so accuracy cost cannot be attributed solely to the defense or attack.
- Detection recall is a final removal metric; early-round flags and transient candidates should be interpreted from the event-level CSV files.
"""
    report_path = args.output_dir / "CIFAR10_ANALYTICS.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"Wrote {summary_path}")
    print(f"Wrote {report_path}")


if __name__ == "__main__":
    main()
