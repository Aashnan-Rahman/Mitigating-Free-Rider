from __future__ import annotations

import argparse
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
    parser.add_argument("--watch", action="store_true", help="Refresh until the batch stops.")
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()

    while True:
        if args.watch:
            clear_screen()
            print("Refreshing status...")
        status_path = resolve_status_path(args.status)
        state = read_status(status_path) if status_path else None
        if state is None:
            waiting_for = args.status or Path("results/**/experiment_status.json")
            print(f"Waiting for status file: {waiting_for}")
        else:
            render(state, status_path)
            if state.get("state") not in {"running"}:
                break
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
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def resolve_status_path(explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit

    results = Path("results")
    root_status = results / "experiment_status.json"
    candidates = list(results.glob("*/experiment_status.json"))
    if root_status.is_file():
        candidates.append(root_status)
    if not candidates:
        return None

    def rank(path: Path) -> tuple[int, float]:
        state = read_status(path) or {}
        running = int(state.get("state") == "running")
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
    print(f"Elapsed: {duration(status.get('elapsed_seconds'))}")
    print(f"ETA:     {duration(status.get('estimated_remaining_seconds'))}")

    current_id = status.get("current_experiment")
    if current_id:
        current = next(
            (item for item in status.get("experiments", []) if item["id"] == current_id),
            {},
        )
        progress = current.get("progress", {})
        round_idx = int(progress.get("round", 0))
        rounds = int(progress.get("total_rounds", 0))
        percent = 100.0 * round_idx / rounds if rounds else 0.0
        methodology = str(
            current.get("config", {}).get("methodology_version", "")
            or progress.get("methodology_version", "")
        )
        if not methodology:
            batch_identity = f"{status.get('batch_id', '')} {status.get('plan', '')}".lower()
            if "v10" in batch_identity:
                methodology = "swtcp_v10"
            elif "v9" in batch_identity:
                methodology = "swtcp_v9"
        print()
        print(f"Current: {current_id}")
        print(f"Round:   {round_idx}/{rounds} ({percent:.1f}%)")
        phase = str(progress.get("phase", "-"))
        if methodology in {"swtcp_v9", "swtcp_v10"}:
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
        if phase in {"frida_loss", "frad_reproduction"}:
            flagged = progress.get(
                "flagged_clients", progress.get("suspected_clients", "-")
            )
            print(f"Flagged this round: {flagged}")
        elif methodology in {"swtcp_v9", "swtcp_v10"}:
            print(f"Cycle C:  {progress.get('candidate_clients', '-')}")
            print(f"Cycle S:  {progress.get('suspected_clients', '-')}")
            if methodology == "swtcp_v10":
                print(f"Reference R: {progress.get('reference_eligible_clients', '-')}")
        else:
            print(f"Candidate: {progress.get('candidate_clients', '-')}")
            print(f"Suspected: {progress.get('suspected_clients', '-')}")
        print(f"Round time: {format_number(progress.get('round_time_seconds'), 's')}")
        if progress.get("detector_time_seconds") not in (None, ""):
            print(
                f"Detector:   {format_number(progress.get('detector_time_seconds'), 's')}"
            )
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
