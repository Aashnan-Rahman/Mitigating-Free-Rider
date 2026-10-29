from __future__ import annotations

import argparse
import csv
import json
import os
import time
from datetime import timedelta
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor the experiment batch status.")
    parser.add_argument(
        "--status",
        type=Path,
        default=None,
        help="Status JSON to monitor; defaults to the active/latest batch under results.",
    )
    parser.add_argument("--watch", action="store_true", help="Refresh through recovery until the selected schedule finishes.")
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()

    while True:
        if args.watch:
            clear_screen()
            print("Refreshing status...")
        try:
            schedule = scheduled_status_paths() if args.status is None else []
            status_path = resolve_status_path(args.status)
        except (OSError, ValueError) as error:
            print(f"Cannot read schedule: {error}")
            if not args.watch:
                break
            time.sleep(max(args.interval, 0.2))
            continue
        if schedule:
            print("Batch schedule (in order):")
            for path in schedule:
                label = ("complete" if batch_complete(path) else
                         "current / awaiting recovery" if path == status_path else "queued")
                print(f"  {path.parent.name}: {label}")
            print()
        state = read_status(status_path) if status_path else None
        if state is None:
            waiting_for = status_path or Path("results/**/experiment_status.json")
            print(f"Waiting for status file: {waiting_for}")
            if schedule:
                print("Automatic recovery checks every five minutes; watch stays open through the handoff.")
        else:
            render(state, status_path)
            if args.watch and state.get("state") in {"failed", "interrupted", "recovering"}:
                print("Waiting for automatic recovery; watch will keep refreshing.")
            if state.get("state") in {"completed", "completed_with_failures", "stopped"}:
                if not (args.watch and schedule and not all(batch_complete(p) for p in schedule)):
                    break
                print("Schedule is not complete. Stops/failures block later batches; watch stays open.")
        if not args.watch:
            break
        time.sleep(max(args.interval, 0.2))


def clear_screen() -> None:
    if os.name == "nt":
        os.system("cls")
    else:
        print("\033[2J\033[H", end="")


def read_status(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def batch_complete(status_path: Path) -> bool:
    """Mirror the recovery launcher's gate; never infer success from recall."""
    batch = status_path.parent
    if (batch / "STOP_REQUESTED").exists():
        return False
    status = read_status(status_path) or {}
    manifest = read_status(batch / "experiment_manifest.json") or {}
    experiments = manifest.get("experiments") or []
    if (status.get("state") != "completed" or status.get("failed_experiments") != 0
            or not experiments):
        return False
    if manifest.get("workflow") == "fedavg_no_detection":
        for entry in experiments:
            if not isinstance(entry, dict) or not entry.get("id"):
                return False
            output = batch / entry["id"]
            horizon = entry.get("rounds", manifest.get("defaults", {}).get("rounds"))
            summary = read_status(output / "summary.json") or {}
            run_status = read_status(output / "status.json") or {}
            if (summary.get("state") != "completed" or summary.get("completed_rounds") != horizon
                    or run_status.get("state") != "completed" or not isinstance(horizon, int)):
                return False
            try:
                with (output / "round_timings.csv").open(newline="", encoding="utf-8-sig") as handle:
                    rounds = [int(row["round"]) for row in csv.DictReader(handle)]
                if rounds != list(range(1, horizon + 1)):
                    return False
            except (OSError, ValueError, KeyError):
                return False
        return True
    return all(isinstance(entry, dict) and isinstance(entry.get("id"), str)
               and bool(entry["id"])
               and (read_status(batch / entry["id"] / "latest_results.json") or {}).get("completed")
               for entry in experiments)


def scheduled_status_paths() -> list[Path]:
    selection_path = Path("configs/active_experiment_schedule.json")
    if not selection_path.is_file():
        return []
    active = read_status(selection_path)
    if active is None:
        raise ValueError(f"Unreadable active schedule: {selection_path}")
    if not active.get("auto_resume") or active.get("workflow") != "v15_detection":
        return []
    anchor = active.get("plan")
    if not anchor:
        raise ValueError("Active schedule must name a plan")
    plans = [anchor]
    if active.get("queue"):
        queue = read_status(Path(active["queue"])) or {}
        plans = queue.get("plans") or []
        normalized = [Path(p).resolve() for p in plans]
        if (not plans or len(set(normalized)) != len(plans)
                or Path(anchor).resolve() not in normalized):
            raise ValueError("Active recovery queue must contain unique plans including the active plan")
        plans = plans[normalized.index(Path(anchor).resolve()):]
    paths = []
    for name in plans:
        plan = read_status(Path(name)) or {}
        if not plan.get("batch_name"):
            raise ValueError(f"Unreadable or unnamed plan: {name}")
        paths.append(Path(plan.get("results_root", "results")) / plan["batch_name"] / "experiment_status.json")
    if len(set(p.resolve() for p in paths)) != len(paths):
        raise ValueError("Recovery plans must use distinct batch directories")
    return paths


def resolve_status_path(explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit

    # Follow the declared current schedule, including while its first status is
    # not yet published or while the watchdog is recovering a failed runner.
    schedule = scheduled_status_paths()
    if schedule:
        return next((p for p in schedule if not batch_complete(p)), schedule[-1])

    results = Path("results")
    root_status = results / "experiment_status.json"
    candidates = list(results.glob("*/experiment_status.json"))
    if root_status.is_file():
        candidates.append(root_status)
    if not candidates:
        return None

    def rank(path: Path) -> tuple[int, float]:
        state = read_status(path) or {}
        running = int(state.get("state") in {"running", "recovering"})
        try:
            modified = path.stat().st_mtime
        except OSError:
            modified = 0.0
        return running, modified

    return max(candidates, key=rank)


def render(status: dict, status_path: Path | None = None) -> None:
    total = int(status.get("total_experiments", 0))
    completed = int(status.get("completed_experiments", 0))
    failed = int(status.get("failed_experiments", 0))
    if status_path is not None:
        print(f"Status:  {status_path}")
    print(f"Batch:   {status.get('batch_id', '-')}")
    print(f"State:   {status.get('state', '-')}")
    print(f"Runs:    {completed}/{total} completed, {failed} failed")
    print(f"Rounds:  {status.get('completed_rounds', 0)}/{status.get('total_rounds', '-')} completed")
    print(f"Updated: {status.get('updated_at', '-')}")
    print(f"Elapsed: {duration(status.get('elapsed_seconds'))}")
    print(f"ETA:     {duration(status.get('estimated_remaining_seconds'))}")
    if status.get('error'):
        print(f"Recovery: {status['error']}")

    current_id = status.get("current_experiment")
    if current_id:
        current = next(
            (item for item in status.get("experiments", []) if item["id"] == current_id),
            {},
        )
        progress = current.get("progress", {})
        round_idx = int(progress.get("round", 0))
        config = current.get("config", {})
        rounds = int(progress.get("total_rounds") or config.get("num_rounds")
                     or (int(status.get("total_rounds", 0)) // total if total else 0))
        percent = 100.0 * round_idx / rounds if rounds else 0.0
        methodology = str(
            current.get("config", {}).get("methodology_version", "")
            or progress.get("methodology_version", "")
        )
        if not methodology:
            batch_identity = f"{status.get('batch_id', '')} {status.get('plan', '')}".lower()
            if "v15_4" in batch_identity:
                methodology = "swtcp_v15_4"
            elif "v13" in batch_identity:
                methodology = "swtcp_v13"
            elif "v12" in batch_identity:
                methodology = "swtcp_v12"
            elif "v11" in batch_identity:
                methodology = "swtcp_v11"
            elif "v10" in batch_identity:
                methodology = "swtcp_v10"
            elif "v9" in batch_identity:
                methodology = "swtcp_v9"
        print()
        print(f"Current: {current_id}")
        print(f"Setting: {config.get('dataset', '-')} / {config.get('distribution', '-')} / {config.get('attack_type', '-')} | seed {config.get('seed', '-')}")
        if config.get("free_rider_pct") is not None:
            print(f"Free riders: {100 * float(config['free_rider_pct']):g}%")
        print(f"Round:   {round_idx}/{rounds} ({percent:.1f}%)")
        if methodology.startswith("swtcp_v15"):
            print("Round progress is published after each complete round/checkpoint.")
        if methodology in {'std_dagmm_native_observational','fedavg_no_detection'}:
            print(f"Working round: {progress.get('working_round', '-')} | client responses: {progress.get('completed_clients', 0)}/{progress.get('active_clients', '-')} (round completion is checkpointed)")
        phase = str(progress.get("phase", "-"))
        if methodology in {"swtcp_v9", "swtcp_v10", "swtcp_v11", "swtcp_v12", "swtcp_v13"}:
            phase_names = {
                "warmup": "warmup (no secret probe cycle yet)",
                "double_probe": "double-probe cycle",
                "single_probe": "single-probe cycle",
                "dormant": "dormant (passive send-back checks)",
            }
            print(f"Probe:   {phase_names.get(phase, phase)}")
        else:
            print(f"Phase:   {phase}")
        print(f"Device:  {progress.get('device', '-')}")
        print(f"Active:  {progress.get('active_clients', '-')}")
        if methodology=='fedavg_no_detection':
            print('Policy: no detector/traps/filtering/removal; every response aggregates')
        elif phase in {"frida_loss", "frad_reproduction"} or methodology == 'std_dagmm_native_observational':
            flagged = progress.get(
                "flagged_clients", progress.get("suspected_clients", "-")
            )
            print(f"Flagged this round: {flagged}")
            if methodology == 'std_dagmm_native_observational':
                print('Policy: flags only, no removals')
        elif methodology in {"swtcp_v9", "swtcp_v10", "swtcp_v11", "swtcp_v12", "swtcp_v13"}:
            print(f"Cycle C:  {progress.get('candidate_clients', '-')}")
            print(f"Cycle S:  {progress.get('suspected_clients', '-')}")
            if methodology in {"swtcp_v10", "swtcp_v11", "swtcp_v12", "swtcp_v13"}:
                print(f"Reference R: {progress.get('reference_eligible_clients', '-')}")
        else:
            print(f"Candidate: {progress.get('candidate_clients', '-')}")
            print(f"Suspected: {progress.get('suspected_clients', '-')}")
        if methodology.startswith("swtcp_v15"):
            print(f"Quarantined: {progress.get('quarantined_clients', '-')}")
            if status_path is not None:
                report = read_status(status_path.parent / current_id / "run_config.json") or {}
                if report.get("removed_free_riders") is not None:
                    print(f"Removed FR / honest: {report['removed_free_riders']} / {report.get('removed_honest_clients', '-')} | FR remaining: {report.get('missed_free_riders', '-')}")
        print(f"Round time: {format_number(progress.get('round_time_seconds'), 's')}")
        if progress.get("detector_time_seconds") not in (None, ""):
            print(
                f"Detector:   {format_number(progress.get('detector_time_seconds'), 's')}"
            )
        if methodology == 'std_dagmm_native_observational':
            print(f"Fit / score: {format_number(progress.get('fit_seconds'), 's')} / {format_number(progress.get('inference_seconds'), 's')} (last complete round)")
        print(f"Accuracy:   {format_number(progress.get('global_accuracy'), '')}")
        print(f"Loss:       {format_number(progress.get('global_loss'), '')}")
        print(f"RSS:        {format_number(progress.get('process_rss_mb'), ' MB')}")
        print(f"CUDA peak:  {format_number(progress.get('cuda_peak_allocated_mb'), ' MB')}")

    print()
    print("Experiments:")
    for item in status.get("experiments", []):
        marker = {"completed": "OK", "failed": "ERR", "running": ">>"}.get(
            item.get("state"), "--"
        )
        rounds = item.get("progress", {}).get("round", 0)
        error = f" | {item.get('error')}" if item.get("error") else ""
        print(f"  {marker:>3} {item['id']:<42} {item.get('state', '-'):>10} R{rounds}{error}")


def duration(seconds) -> str:
    if seconds is None:
        return "calculating"
    return str(timedelta(seconds=int(float(seconds))))


def format_number(value, suffix: str) -> str:
    if value in (None, ""):
        return "n/a"
    return f"{float(value):.4f}{suffix}"


if __name__ == "__main__":
    main()
