from __future__ import annotations

import argparse
import itertools
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from atomic_io import atomic_write_json
from config import ExperimentConfig
from train import run_experiment


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an experiment matrix sequentially.")
    parser.add_argument("--plan", type=Path, default=Path("configs/experiment_plan.json"))
    parser.add_argument(
        "--resume-batch",
        type=Path,
        help=(
            "Resume an existing batch directory. Completed experiments are skipped, "
            "the first incomplete experiment uses its newest fully published checkpoint, "
            "and remaining experiments continue sequentially."
        ),
    )
    parser.add_argument("--include-disabled", action="store_true")
    parser.add_argument("--stop-on-error", action="store_true")
    args = parser.parse_args()

    if args.resume_batch:
        batch_dir = args.resume_batch.resolve()
        manifest_path = batch_dir / "experiment_manifest.json"
        batch_status_path = batch_dir / "experiment_status.json"
        if not manifest_path.is_file() or not batch_status_path.is_file():
            raise FileNotFoundError(
                "A resumable batch must contain experiment_manifest.json and "
                f"experiment_status.json: {batch_dir}"
            )
        manifest = read_json(manifest_path)
        plan = {"defaults": manifest.get("defaults", {})}
        experiments = list(manifest.get("experiments", []))
        batch_id = str(manifest.get("batch_id") or batch_dir.name)
        results_root = batch_dir.parent
        try:
            status = read_json(batch_status_path)
        except (json.JSONDecodeError, UnicodeDecodeError):
            status = reconstruct_status(manifest)
        status_records = {item["id"]: item for item in status.get("experiments", [])}
        status["experiments"] = [
            status_records.get(
                item["id"],
                {"id": item["id"], "state": "queued", "config": item["config"]},
            )
            for item in experiments
        ]
        prior_elapsed = float(status.get("elapsed_seconds", 0.0))
        started = time.time() - prior_elapsed
        status.update(
            {
                "batch_id": batch_id,
                "plan": str(manifest.get("source_plan", status.get("plan", args.plan))),
                "state": "running",
                "current_experiment": None,
                "resumed_at": datetime.now().isoformat(),
            }
        )
        status.pop("finished_at", None)
        for record in status["experiments"]:
            run_dir = batch_dir / record["id"]
            if completed_run_exists(run_dir):
                record["state"] = "completed"
                record.pop("error", None)
            elif record.get("state") in {"running", "failed", "interrupted"}:
                record["state"] = "queued"
        refresh_totals(status, plan)
    else:
        plan = read_json(args.plan)
        experiments = expand_plan(plan, args.include_disabled)
        batch_id = plan.get("batch_name") or datetime.now().strftime("batch_%Y%m%d_%H%M%S")
        results_root = Path(plan.get("results_root", "./results"))
        batch_dir = results_root / batch_id
        batch_dir.mkdir(parents=True, exist_ok=True)
        batch_status_path = batch_dir / "experiment_status.json"
        started = time.time()
        status = {
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

    status_path = results_root / "experiment_status.json"

    def save_status() -> None:
        status["updated_at"] = datetime.now().isoformat()
        status["elapsed_seconds"] = time.time() - started
        write_json(status_path, status)
        write_json(batch_status_path, status)

    save_status()
    try:
        for index, experiment in enumerate(experiments):
            record = status["experiments"][index]
            if record.get("state") == "completed":
                continue

            values = {**plan.get("defaults", {}), **experiment["config"]}
            values["output_dir"] = str(batch_dir)
            values["run_name"] = experiment["id"]
            run_dir = batch_dir / experiment["id"]
            published_round = published_latest_round(run_dir, record)
            checkpoint = select_resume_checkpoint(run_dir, published_round)
            if published_round > 0 and checkpoint is None:
                raise FileNotFoundError(
                    f"{experiment['id']} has results through round {published_round}, "
                    "but no matching recovery checkpoint was found."
                )
            if checkpoint is not None:
                values["resume_checkpoint"] = str(checkpoint)
                record["resumed_from_checkpoint"] = str(checkpoint)

            record.update({"state": "running", "started_at": datetime.now().isoformat()})
            record.pop("finished_at", None)
            record.pop("error", None)
            status["current_experiment"] = experiment["id"]
            refresh_totals(status, plan)
            save_status()
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
                                "final_candidate_clients", "final_suspected_clients",
                                "precision", "recall", "f1", "detection_accuracy",
                                "false_positive_removal_rate",
                            )
                        },
                    }
                )
                refresh_totals(status, plan)
            except Exception as exc:
                record.update(
                    {
                        "state": "failed",
                        "finished_at": datetime.now().isoformat(),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                refresh_totals(status, plan)
                if args.stop_on_error:
                    raise
            finally:
                save_status()
    except KeyboardInterrupt:
        current = status.get("current_experiment")
        for record in status["experiments"]:
            if record["id"] == current and record.get("state") == "running":
                record["state"] = "interrupted"
                record["finished_at"] = datetime.now().isoformat()
        status["state"] = "interrupted"
        status["current_experiment"] = None
        refresh_totals(status, plan)
        save_status()
        raise
    except Exception:
        status["state"] = "failed"
        status["current_experiment"] = None
        save_status()
        raise

    refresh_totals(status, plan)
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
            if stage.get("id_format"):
                experiment_id = str(stage["id_format"]).format(
                    stage_id=stage["id"], free_rider_percent=pct, **config
                )
            else:
                experiment_id = "_".join(
                    (
                        stage["id"], str(config.get("dataset", "data")),
                        str(config.get("distribution", "dist")),
                        str(config.get("attack_type", "attack")).lower(), f"fr{pct}",
                    )
                )
            if Path(experiment_id).name != experiment_id or experiment_id in {"", ".", ".."}:
                raise ValueError(f"Invalid experiment id: {experiment_id!r}")
            expanded.append({"id": experiment_id, "config": config})
    return expanded


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def reconstruct_status(manifest: dict[str, Any]) -> dict[str, Any]:
    """Rebuild minimal batch state when an outage damaged only the status JSON."""
    records = []
    batch_dir_name = str(manifest.get("batch_id", ""))
    for experiment in manifest.get("experiments", []):
        record = {"id": experiment["id"], "state": "queued", "config": experiment["config"]}
        records.append(record)
    status: dict[str, Any] = {
        "batch_id": batch_dir_name,
        "plan": str(manifest.get("source_plan", "")),
        "state": "interrupted",
        "started_at": manifest.get("created_at", datetime.now().isoformat()),
        "updated_at": datetime.now().isoformat(),
        "current_experiment": None,
        "experiments": records,
        "elapsed_seconds": 0.0,
    }
    refresh_totals(status, {"defaults": manifest.get("defaults", {})})
    return status


def completed_run_exists(run_dir: Path) -> bool:
    latest_path = run_dir / "latest_results.json"
    if not latest_path.is_file():
        return False
    try:
        return bool(read_json(latest_path).get("completed"))
    except json.JSONDecodeError:
        return False


def published_latest_round(run_dir: Path, record: dict[str, Any]) -> int:
    latest_path = run_dir / "latest_results.json"
    if latest_path.is_file():
        try:
            return int(read_json(latest_path).get("latest_round", 0))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return int(record.get("completed_rounds", record.get("progress", {}).get("round", 0)))


def select_resume_checkpoint(run_dir: Path, published_round: int) -> Path | None:
    """Choose the newest numbered checkpoint consistent with published result logs."""
    numbered: list[tuple[int, Path]] = []
    for path in run_dir.glob("checkpoint_round_*.pt"):
        suffix = path.stem.removeprefix("checkpoint_round_")
        if suffix.isdigit() and int(suffix) <= published_round:
            numbered.append((int(suffix), path))
    if numbered:
        return max(numbered, key=lambda item: item[0])[1]
    latest = run_dir / "latest_checkpoint.pt"
    return latest if published_round > 0 and latest.is_file() else None


def refresh_totals(status: dict[str, Any], plan: dict[str, Any]) -> None:
    defaults = plan.get("defaults", {})
    records = status.get("experiments", [])
    status["total_experiments"] = len(records)
    status["completed_experiments"] = sum(
        item.get("state") == "completed" for item in records
    )
    status["failed_experiments"] = sum(item.get("state") == "failed" for item in records)
    status["total_rounds"] = sum(
        int(item.get("config", {}).get("num_rounds", defaults.get("num_rounds", 100)))
        for item in records
    )
    status["completed_rounds"] = sum(
        int(item.get("progress", {}).get("round", item.get("completed_rounds", 0)))
        for item in records
    )


def write_json(path: Path, value: dict[str, Any]) -> None:
    atomic_write_json(path, value)


if __name__ == "__main__":
    main()
