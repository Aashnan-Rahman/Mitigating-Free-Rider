import json

from run_experiments import (
    completed_run_exists,
    published_latest_round,
    refresh_totals,
    select_resume_checkpoint,
)


def test_selects_newest_checkpoint_not_ahead_of_published_logs(tmp_path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "latest_results.json").write_text(
        json.dumps({"latest_round": 8}), encoding="utf-8"
    )
    for round_idx in (7, 8, 9):
        (run_dir / f"checkpoint_round_{round_idx:04d}.pt").write_bytes(b"checkpoint")

    published = published_latest_round(run_dir, {})

    assert published == 8
    assert select_resume_checkpoint(run_dir, published).name == "checkpoint_round_0008.pt"


def test_completed_marker_controls_batch_skip(tmp_path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    latest = run_dir / "latest_results.json"
    latest.write_text(json.dumps({"latest_round": 100}), encoding="utf-8")
    assert not completed_run_exists(run_dir)

    latest.write_text(
        json.dumps({"latest_round": 100, "completed": True}), encoding="utf-8"
    )
    assert completed_run_exists(run_dir)


def test_refresh_totals_preserves_partial_progress() -> None:
    status = {
        "experiments": [
            {"state": "completed", "completed_rounds": 100, "config": {}},
            {"state": "running", "progress": {"round": 79}, "config": {}},
            {"state": "queued", "config": {}},
        ]
    }

    refresh_totals(status, {"defaults": {"num_rounds": 100}})

    assert status["completed_experiments"] == 1
    assert status["failed_experiments"] == 0
    assert status["completed_rounds"] == 179
    assert status["total_rounds"] == 300
