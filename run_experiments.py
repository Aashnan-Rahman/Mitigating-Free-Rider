from __future__ import annotations

import argparse
import itertools
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from config import ExperimentConfig
from train import run_experiment


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an experiment matrix sequentially.")
    parser.add_argument("--plan", type=Path, default=Path("configs/experiment_plan.json"))
    parser.add_argument("--include-disabled", action="store_true")
    parser.add_argument("--stop-on-error", action="store_true")
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    experiments = expand_plan(plan, args.include_disabled)
    batch_id = plan.get("batch_name") or datetime.now().strftime("batch_%Y%m%d_%H%M%S")
    results_root = Path(plan.get("results_root", "./results"))
    batch_dir = results_root / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    status_path = results_root / "experiment_status.json"
    batch_status_path = batch_dir / "experiment_status.json"
    started = time.time()
    status: dict[str, Any] = {
        "batch_id": batch_id,
        "plan": str(args.plan),
        "state": "running",
        "started_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "total_experiments": len(experiments),
        "total_rounds": sum(
            int(item["config"].get("num_rounds", plan.get("defaults", {}).get("num_rounds", 100)))
            for item in experiments
        ),
        "completed_rounds": 0,
        "completed_experiments": 0,
        "failed_experiments": 0,
        "current_experiment": None,
        "experiments": [
            {"id": item["id"], "state": "queued", "config": item["config"]}
            for item in experiments
        ],
    }
    write_json(
        batch_dir / "experiment_manifest.json",
        {
            "batch_id": batch_id,
            "source_plan": str(args.plan),
            "defaults": plan.get("defaults", {}),
            "experiments": experiments,
            "created_at": datetime.now().isoformat(),
        },
    )

    def save_status() -> None:
        status["updated_at"] = datetime.now().isoformat()
        status["elapsed_seconds"] = time.time() - started
        write_json(status_path, status)
        write_json(batch_status_path, status)

    save_status()
    try:
        for index, experiment in enumerate(experiments):
            record = status["experiments"][index]
            record.update({"state": "running", "started_at": datetime.now().isoformat()})
            status["current_experiment"] = experiment["id"]
            save_status()

            values = {**plan.get("defaults", {}), **experiment["config"]}
            values["output_dir"] = str(batch_dir)
            values["run_name"] = experiment["id"]
            config = ExperimentConfig.from_dict(values)

            def progress(update: dict[str, object]) -> None:
                record["progress"] = update
                completed_rounds = int(update["round"])
                elapsed = time.time() - started
                all_done_rounds = sum(
                    int(item.get("progress", {}).get("round", 0))
                    for item in status["experiments"]
                )
                total_rounds = sum(
                    int(item["config"].get("num_rounds", plan.get("defaults", {}).get("num_rounds", 100)))
                    for item in status["experiments"]
                )
                status["completed_rounds"] = all_done_rounds
                status["total_rounds"] = total_rounds
                status["estimated_remaining_seconds"] = (
                    elapsed / all_done_rounds * (total_rounds - all_done_rounds)
                    if all_done_rounds
                    else None
                )
                record["completed_rounds"] = completed_rounds
                save_status()

            try:
                run_dir = Path(run_experiment(config, progress_callback=progress))
                summary_path = run_dir / "run_config.json"
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                record.update(
                    {
                        "state": "completed",
                        "finished_at": datetime.now().isoformat(),
                        "run_dir": str(run_dir),
                        "summary": {
                            key: summary.get(key)
                            for key in (
                                "total_wall_clock_seconds", "average_round_time_seconds",
                                "final_global_accuracy", "best_global_accuracy",
                                "final_global_loss", "peak_process_rss_mb",
                                "peak_cuda_allocated_mb", "removed_free_riders",
                                "removed_honest_clients", "missed_free_riders",
                                "precision", "recall", "f1", "detection_accuracy",
                                "false_positive_removal_rate",
                            )
                        },
                    }
                )
                status["completed_experiments"] += 1
            except Exception as exc:
                record.update(
                    {
                        "state": "failed",
                        "finished_at": datetime.now().isoformat(),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                status["failed_experiments"] += 1
                if args.stop_on_error:
                    raise
            finally:
                save_status()
    except KeyboardInterrupt:
        status["state"] = "interrupted"
        status["current_experiment"] = None
        save_status()
        raise
    except Exception:
        status["state"] = "failed"
        status["current_experiment"] = None
        save_status()
        raise

    status["state"] = "completed" if not status["failed_experiments"] else "completed_with_failures"
    status["current_experiment"] = None
    status["finished_at"] = datetime.now().isoformat()
    save_status()
    write_json(
        batch_dir / "batch_summary.json",
        {
            "batch_id": batch_id,
            "state": status["state"],
            "started_at": status["started_at"],
            "finished_at": status["finished_at"],
            "elapsed_seconds": status["elapsed_seconds"],
            "completed_experiments": status["completed_experiments"],
            "failed_experiments": status["failed_experiments"],
            "experiments": status["experiments"],
        },
    )


def expand_plan(plan: dict[str, Any], include_disabled: bool) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for stage in plan.get("stages", []):
        if not stage.get("enabled", True) and not include_disabled:
            continue
        matrix = stage["matrix"]
        keys = list(matrix)
        for values in itertools.product(*(matrix[key] for key in keys)):
            config = dict(zip(keys, values))
            pct = int(round(float(config.get("free_rider_pct", 0)) * 100))
            experiment_id = "_".join(
                (
                    stage["id"], str(config.get("dataset", "data")),
                    str(config.get("distribution", "dist")),
                    str(config.get("attack_type", "attack")).lower(), f"fr{pct}",
                )
            )
            expanded.append({"id": experiment_id, "config": config})
    return expanded


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    main()
