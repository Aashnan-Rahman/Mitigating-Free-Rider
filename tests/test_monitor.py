import json

from monitor import render, resolve_status_path


def _write_status(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")


def test_auto_selects_running_batch_over_completed_batch(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    completed = tmp_path / "results" / "old" / "experiment_status.json"
    running = tmp_path / "results" / "new" / "experiment_status.json"
    _write_status(completed, {"state": "completed"})
    _write_status(running, {"state": "running"})

    assert resolve_status_path(None) == running.relative_to(tmp_path)


def test_v9_monitor_uses_probe_and_cycle_labels(capsys):
    render(
        {
            "batch_id": "v9-test",
            "state": "running",
            "total_experiments": 1,
            "completed_experiments": 0,
            "failed_experiments": 0,
            "current_experiment": "run-1",
            "experiments": [
                {
                    "id": "run-1",
                    "state": "running",
                    "config": {},
                    "progress": {
                        "round": 12,
                        "total_rounds": 100,
                        "phase": "double_probe",
                        "candidate_clients": 3,
                        "suspected_clients": 2,
                    },
                }
            ],
        }
    )

    output = capsys.readouterr().out
    assert "Probe:   double-probe cycle" in output
    assert "Cycle C:  3" in output
    assert "Cycle S:  2" in output
    assert "Candidate:" not in output
