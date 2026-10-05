from dataclasses import replace
from pathlib import Path

import pytest
import torch
from torch import nn
from torch.utils.data import TensorDataset

import train
from config import ExperimentConfig


@pytest.fixture
def tiny_training(monkeypatch):
    generator = torch.Generator().manual_seed(17)
    data = TensorDataset(torch.randn(120, 1, 28, 28, generator=generator),
                         torch.arange(120) % 10)
    data.targets = data.tensors[1]
    monkeypatch.setattr(train, "get_datasets", lambda config: (data, data))
    monkeypatch.setattr(train, "get_model", lambda dataset: nn.Sequential(nn.Flatten(), nn.Linear(784, 10)))
    def forbidden(*args, **kwargs):
        raise AssertionError("v13 must not execute v12 reconstruction or v11 evaluation")
    monkeypatch.setattr(train, "history_reconstruction_scores", forbidden)
    monkeypatch.setattr(train, "evaluate_v12_cycle", forbidden)
    monkeypatch.setattr(train, "evaluate_v11_cycle", forbidden)
    previous_threads = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(previous_threads)


def config(root, name, **changes):
    return ExperimentConfig(methodology_version="swtcp_v13", num_clients=12,
                            num_rounds=14, warmup_rounds=2, surveillance_groups=4,
                            local_epochs=1, batch_size=16, device="cpu", free_rider_pct=.4,
                            attack_type="FR4", cycle_min_reference_clients=4,
                            output_dir=str(root), run_name=name, **changes)


def test_real_training_flow_and_checkpoint_resume_are_identical(tmp_path, tiny_training):
    import csv
    import json
    original = config(tmp_path, "complete")
    train.run_experiment(original)
    interrupted = replace(original, run_name="resumed")
    def stop(update):
        if update["round"] == 7:
            raise RuntimeError("test interruption")
    with pytest.raises(RuntimeError, match="test interruption"):
        train.run_experiment(interrupted, stop)
    checkpoint = Path(interrupted.run_dir()) / "checkpoint_round_0007.pt"
    train.run_experiment(replace(interrupted, resume_checkpoint=str(checkpoint)))
    def rows(name, filename):
        with (tmp_path / name / filename).open(newline="") as handle:
            return list(csv.DictReader(handle))
    a, b = rows("complete", "global_metrics.csv"), rows("resumed", "global_metrics.csv")
    for key in ("round", "global_accuracy", "global_loss", "num_active_clients",
                "num_candidate_clients", "num_suspected_clients", "num_aggregated"):
        assert [row[key] for row in a] == [row[key] for row in b]
    for file in ("removals.csv", "candidate_events.csv", "trap_assignments.csv"):
        assert rows("complete", file) == rows("resumed", file)
    summary = json.loads((tmp_path / "resumed" / "run_config.json").read_text())
    assert summary["completed_rounds"] == 14
    assert summary["detector_uses_attack_history"] is False
    assert "honest_quarantine_client_rounds" in summary
    assert "was_aggregated" in rows("resumed", "client_metrics.csv")[0]


def test_sendback_path_remains_separate(tmp_path, tiny_training):
    import csv
    cfg = replace(config(tmp_path, "sendback"), attack_type="FR1", warmup_rounds=5)
    train.run_experiment(cfg)
    with (cfg.run_dir() / "removals.csv").open(newline="") as handle:
        removed = list(csv.DictReader(handle))
    sendbacks = [row for row in removed if row["removal_basis"] == "five_exact_sendbacks"]
    assert len(sendbacks) == 5
    assert all(int(row["round"]) == 5 and row["is_free_rider"] == "1" for row in sendbacks)
