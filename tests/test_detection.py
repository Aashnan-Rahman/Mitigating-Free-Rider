import torch

from config import ExperimentConfig
from server.detection import evaluate_updates


def _batch(fr_norm: float) -> tuple[dict[int, torch.Tensor], dict[int, float]]:
    deltas = {
        **{client_id: torch.tensor([1.0, 0.0]) for client_id in range(6)},
        **{client_id: torch.tensor([fr_norm, 0.0]) for client_id in range(6, 10)},
    }
    losses = {
        **{client_id: 1.0 for client_id in range(6)},
        **{client_id: 3.0 for client_id in range(6, 10)},
    }
    return deltas, losses


def test_large_norm_z_flags_fr2_style_updates() -> None:
    config = ExperimentConfig(use_loss_check=False)
    deltas, losses = _batch(fr_norm=3.0)

    results = evaluate_updates(deltas, losses, torch.ones(2), set(), 11, config)

    assert all(not results[client_id].flagged for client_id in range(6))
    assert all(results[client_id].reason == "large_norm_z" for client_id in range(6, 10))


def test_early_loss_and_low_norm_flags_fr3_style_updates() -> None:
    config = ExperimentConfig()
    deltas, losses = _batch(fr_norm=0.1)

    results = evaluate_updates(deltas, losses, torch.ones(2), set(), 3, config)

    assert all(not results[client_id].flagged for client_id in range(6))
    assert all(
        results[client_id].reason == "early_loss_low_norm"
        for client_id in range(6, 10)
    )


def test_loss_signal_stops_after_empirical_window() -> None:
    config = ExperimentConfig()
    deltas, losses = _batch(fr_norm=0.1)

    results = evaluate_updates(deltas, losses, torch.ones(2), set(), 7, config)

    assert all(not result.flagged for result in results.values())


def test_cosine_direction_never_causes_a_flag() -> None:
    config = ExperimentConfig(use_loss_check=False)
    deltas = {client_id: torch.tensor([1.0, 0.0]) for client_id in range(10)}
    losses = {client_id: 1.0 for client_id in deltas}

    results = evaluate_updates(deltas, losses, torch.tensor([-1.0, 0.0]), set(), 11, config)

    assert all(result.cosine_similarity == -1.0 for result in results.values())
    assert all(not result.flagged for result in results.values())
