import json

from run_experiments import (
    completed_run_exists,
    expand_plan,
    published_latest_round,
    refresh_totals,
    select_resume_checkpoint,
)


def test_plan_can_use_simple_experiment_ids() -> None:
    plan = {
        "stages": [
            {
                "id": "stage",
                "id_format": "{attack_type}",
                "matrix": {"attack_type": ["FR1", "FR2"], "free_rider_pct": [0.3]},
            }
        ]
    }

    experiments = expand_plan(plan, include_disabled=False)

    assert [item["id"] for item in experiments] == ["FR1", "FR2"]


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


def test_missing_batch_status_is_rebuilt_and_completed_runs_are_not_repeated(tmp_path, monkeypatch):
    import run_experiments as runner
    batch_dir = tmp_path/'batch'
    (batch_dir/'run').mkdir(parents=True)
    (batch_dir/'experiment_manifest.json').write_text(json.dumps(dict(
        batch_id='batch', defaults=dict(num_rounds=100),
        experiments=[dict(id='run', config={})])))
    (batch_dir/'run/latest_results.json').write_text(json.dumps(dict(completed=True, latest_round=100)))
    def forbidden(*args, **kwargs):
        raise AssertionError('A completed run must never restart')
    monkeypatch.setattr(runner, 'run_experiment', forbidden)
    monkeypatch.setattr('sys.argv', ['run_experiments.py', '--resume-batch', str(batch_dir)])
    runner.main()
    state = json.loads((batch_dir/'experiment_status.json').read_text())
    assert state['state'] == 'completed'
    assert state['completed_experiments'] == 1 and state['completed_rounds'] == 100


def test_missing_status_resumes_the_published_checkpoint_without_training(tmp_path, monkeypatch):
    import run_experiments as runner
    batch_dir = tmp_path/'batch'
    (batch_dir/'run').mkdir(parents=True)
    (batch_dir/'experiment_manifest.json').write_text(json.dumps(dict(
        batch_id='batch', defaults=dict(num_rounds=100),
        experiments=[dict(id='run', config=dict(seed=73))])))
    checkpoint = batch_dir/'run/checkpoint_round_0005.pt'
    checkpoint.write_bytes(b'fake checkpoint; fake runner must not deserialize it')
    (batch_dir/'run/latest_results.json').write_text(json.dumps(dict(completed=False, latest_round=5)))
    (batch_dir/'run/run_config.json').write_text('{}')
    seen = []
    def fake_runner(config, progress_callback):
        seen.append(config.resume_checkpoint)
        progress_callback(dict(round=100))
        return batch_dir/'run'
    monkeypatch.setattr(runner, 'run_experiment', fake_runner)
    monkeypatch.setattr('sys.argv', ['run_experiments.py', '--resume-batch', str(batch_dir)])
    runner.main()
    state = json.loads((batch_dir/'experiment_status.json').read_text())
    assert seen == [str(checkpoint)]
    assert state['state'] == 'completed' and state['completed_rounds'] == 100
