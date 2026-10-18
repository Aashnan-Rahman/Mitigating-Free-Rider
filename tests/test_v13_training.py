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
                            # Small synthetic fixtures need rank resolution;
                            # deployment keeps its preselected 1% risk budget.
                            cycle_target_false_alarm_rate=.1,
                            output_dir=str(root), run_name=name, **changes)


@pytest.mark.parametrize("paired", [False, True])
def test_real_training_flow_and_checkpoint_resume_are_identical(tmp_path, tiny_training, paired):
    import csv
    import json
    original = config(tmp_path, "complete", paired_measurement_only=paired)
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
    if paired:
        assert rows("complete", "paired_responses.csv") == rows("resumed", "paired_responses.csv")
        assert len(rows("complete", "paired_responses.csv")) == 36
        assert not rows("complete", "candidate_events.csv")
        assert not rows("complete", "removals.csv")
        assert summary["statistical_decisions_enabled"] is False
        assert not any(row["v13_calibration_ready"] == "1" for row in a)
    else:
        assert any(row["v13_calibration_ready"] == "1" for row in a)


@pytest.mark.parametrize("paired", [False, True])
def test_sendback_path_remains_separate(tmp_path, tiny_training, paired):
    import csv
    cfg = replace(config(tmp_path, "sendback", paired_measurement_only=paired), attack_type="FR1", warmup_rounds=5)
    train.run_experiment(cfg)
    with (cfg.run_dir() / "removals.csv").open(newline="") as handle:
        removed = list(csv.DictReader(handle))
    sendbacks = [row for row in removed if row["removal_basis"] == "five_exact_sendbacks"]
    assert len(sendbacks) == 5
    assert all(int(row["round"]) == 5 and row["is_free_rider"] == "1" for row in sendbacks)


def test_paired_mode_never_uses_population_classifier(tmp_path, tiny_training, monkeypatch):
    from server.v13_detection import V13Detector
    def forbidden(*args, **kwargs):
        raise AssertionError("Measurement-only protocol must not classify")
    monkeypatch.setattr(V13Detector, "evaluate_cycle", forbidden)
    train.run_experiment(config(tmp_path, "paired_only", paired_measurement_only=True))


def test_shadow_training_proposes_but_never_enforces_and_resumes(tmp_path, tiny_training):
    import csv
    import json
    from server.paired_shadow import context_from_config, REVISION
    from atomic_io import atomic_write_json
    cfg = config(tmp_path, "shadow", paired_measurement_only=True)
    # A deliberately tiny synthetic boundary tests enforcement isolation, not
    # performance. Production artifacts use separate clean control windows.
    calibration = tmp_path / "synthetic_calibration.json"
    atomic_write_json(calibration, {"revision": REVISION, "window": 3,
        "context": context_from_config(cfg), "alpha": .1,
        "center": [0.] * 5, "scale": [1.] * 5, "cutoff": 0.,
        "fit_windows": 100, "calibration_windows": 100, "guarantee": "test"})
    cfg = replace(cfg, paired_shadow_calibration=str(calibration))
    def interrupt(update):
        if update["round"] == 7:
            raise RuntimeError("shadow interruption")
    with pytest.raises(RuntimeError, match="shadow interruption"):
        train.run_experiment(cfg, interrupt)
    checkpoint = cfg.run_dir() / "checkpoint_round_0007.pt"
    train.run_experiment(replace(cfg, resume_checkpoint=str(checkpoint)))
    complete = replace(cfg, run_name="shadow_complete")
    train.run_experiment(complete)
    def rows(run, filename):
        with (run.run_dir() / filename).open(newline="") as handle:
            return list(csv.DictReader(handle))
    assert rows(cfg, "paired_shadow_decisions.csv") == rows(complete, "paired_shadow_decisions.csv")
    assert sum(int(row["proposed_remove"]) for row in rows(cfg, "paired_shadow_decisions.csv")) == 12
    assert not rows(cfg, "removals.csv")
    assert not rows(cfg, "candidate_events.csv")


@pytest.mark.parametrize("diagonal", [False, True])
def test_preliminary_keeps_fr1_and_records_both_traps(tmp_path, tiny_training, diagonal):
    import csv
    cfg = replace(config(tmp_path, "preli"), methodology_version="v14_1_preli",
                  paired_measurement_only=True, num_rounds=20, warmup_rounds=10,
                  surveillance_groups=10, attack_type="FR1", preliminary_diagonal_decisions=diagonal)
    train.run_experiment(cfg)
    with (cfg.run_dir() / "preliminary_signals.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 24
    assert sum(int(row["exact_zero_delta"]) for row in rows) == 10
    with (cfg.run_dir() / "removals.csv").open(newline="") as handle:
        assert not list(csv.DictReader(handle))
    with (cfg.run_dir() / "client_metrics.csv").open(newline="") as handle:
        metrics = list(csv.DictReader(handle))
    assert all(row["was_aggregated"] == "0" for row in metrics if row["was_trapped"] == "1")
    interrupted = replace(cfg, run_name="preli_resumed")
    def stop(update):
        if update["round"] == 15:
            raise RuntimeError("preli interruption")
    with pytest.raises(RuntimeError, match="preli interruption"):
        train.run_experiment(interrupted, stop)
    train.run_experiment(replace(interrupted, resume_checkpoint=str(interrupted.run_dir() / "checkpoint_round_0015.pt")))
    with (interrupted.run_dir() / "preliminary_signals.csv").open(newline="") as handle:
        assert list(csv.DictReader(handle)) == rows
    if diagonal:
        with (cfg.run_dir() / "preliminary_decisions.csv").open(newline="") as handle:
            decisions = list(csv.DictReader(handle))
        assert len(decisions) == 12
        assert sum(row["state"] == "S" and row["is_free_rider"] == "1" for row in decisions) == 5
        assert all(row["enforced"] == "0" for row in decisions)
        with (interrupted.run_dir() / "preliminary_decisions.csv").open(newline="") as handle:
            assert list(csv.DictReader(handle)) == decisions


@pytest.mark.parametrize("method", ["swtcp_v15", "swtcp_v15_1", "swtcp_v15_2", "swtcp_v15_3", "swtcp_v15_4"])
def test_v15_removes_fr1_only_after_two_full_cycles_and_resumes(tmp_path, tiny_training, method):
    import csv
    import json
    cfg = replace(config(tmp_path, "v15_full"), methodology_version=method, num_rounds=50,
                  warmup_rounds=10, surveillance_groups=10, attack_type="FR1", seed=73)
    train.run_experiment(cfg)
    def rows(run, filename):
        with (run.run_dir() / filename).open(newline="") as handle:
            return list(csv.DictReader(handle))
    removed = rows(cfg, "removals.csv")
    assert all(int(row["round"]) >= 30 for row in removed)
    assert len([r for r in removed if r["is_free_rider"] == "1" and r["round"] == "30"]) == 5
    probes = rows(cfg, "cycle_probes.csv")
    for client in {r["client_id"] for r in probes if r["is_free_rider"] == "1"}:
        assert len([r for r in probes if r["client_id"] == client and 21 <= int(r["round"]) <= 30]) == 10
    decisions = rows(cfg, "cycle_decisions.csv")
    assert all(r["removed"] == "0" for r in decisions if r["round"] == "20")
    metrics = rows(cfg, "client_metrics.csv")
    assert all(r["was_aggregated"] == "0" for r in metrics if r["was_trapped"] == "1" or r["was_quarantined"] == "1")
    resumed = replace(cfg, run_name="v15_resume")
    def interrupt(update):
        if update["round"] == 25:
            raise RuntimeError("v15 interruption")
    with pytest.raises(RuntimeError, match="v15 interruption"):
        train.run_experiment(resumed, interrupt)
    checkpoint = resumed.run_dir() / "checkpoint_round_0025.pt"
    train.run_experiment(replace(resumed, resume_checkpoint=str(checkpoint)))
    for filename in ("cycle_signals.csv", "cycle_decisions.csv", "cycle_probes.csv", "cycle_groups.csv", "removals.csv"):
        assert rows(cfg, filename) == rows(resumed, filename)
    assert [r["global_accuracy"] for r in rows(cfg, "global_metrics.csv")] == [r["global_accuracy"] for r in rows(resumed, "global_metrics.csv")]
    summary = json.loads((cfg.run_dir() / "run_config.json").read_text())
    assert summary["removed_free_riders"] == 5 and summary["detector_uses_attack_history"] is False


def test_v15_4_gap_certificate_survives_real_training_checkpoint(tmp_path, tiny_training, monkeypatch):
    import csv
    import server.v15_certificate_memory as backend
    cfg = replace(config(tmp_path, "v154_gap_full"), methodology_version="swtcp_v15_4",
                  num_rounds=40, warmup_rounds=10, surveillance_groups=10, seed=73)
    original_screen = backend.screen
    def scripted_screen(signals, round_index):
        decisions, metadata = original_screen(signals, round_index)
        for decision in decisions:
            is_selected = decision["client_id"] == 0
            fresh = is_selected and round_index in (20, 40)
            decision.update(state="S" if fresh else "C" if is_selected else "R",
                            strong_channels="norm_low" if fresh else "")
        return decisions, metadata
    monkeypatch.setattr(backend, "screen", scripted_screen)
    train.run_experiment(cfg)
    resumed = replace(cfg, run_name="v154_gap_resume")
    def interrupt(update):
        if update["round"] == 35:
            raise RuntimeError("gap checkpoint interruption")
    with pytest.raises(RuntimeError, match="gap checkpoint"):
        train.run_experiment(resumed, interrupt)
    checkpoint = resumed.run_dir() / "checkpoint_round_0035.pt"
    saved = torch.load(checkpoint, weights_only=False)
    assert saved["state"][0]["fresh_certificate_counts"] == {"norm_low": 1}
    train.run_experiment(replace(resumed, resume_checkpoint=str(checkpoint)))
    def rows(cfg, filename):
        with (cfg.run_dir() / filename).open(newline="") as handle:
            return list(csv.DictReader(handle))
    for filename in ("cycle_decisions.csv", "cycle_probes.csv", "removals.csv", "cycle_groups.csv"):
        assert rows(cfg, filename) == rows(resumed, filename)
    removals = rows(cfg, "removals.csv")
    assert len(removals) == 1 and removals[0]["client_id"] == "0" and removals[0]["round"] == "40"
    assert removals[0]["removal_basis"] == "repeated_fresh_component_certificates"
