from __future__ import annotations

import inspect

import torch

from config import ExperimentConfig
from server.v12_detection import (
    compact_sketch,
    evaluate_v12_cycle,
    history_reconstruction_scores,
    one_sided_robust_z,
)


def test_compact_sketch_is_linear() -> None:
    left = torch.arange(101, dtype=torch.float32)
    right = torch.linspace(-2.0, 3.0, 101)
    combined = compact_sketch(left + right, 16, 43)
    separate = compact_sketch(left, 16, 43) + compact_sketch(right, 16, 43)
    assert torch.allclose(combined, separate, atol=1e-4)


def test_mean_history_reconstruction_is_exact_for_an_averaged_sendback() -> None:
    sent = [
        torch.tensor([1.0, 2.0, 3.0]),
        torch.tensor([2.0, 3.0, 4.0]),
        torch.tensor([4.0, 5.0, 6.0]),
    ]
    fabricated_update = torch.stack(sent).mean(dim=0) - sent[-1]
    unrelated_update = torch.tensor([0.3, -0.2, 0.7])

    fabricated = history_reconstruction_scores(fabricated_update, sent, 5, 1e-8)
    unrelated = history_reconstruction_scores(unrelated_update, sent, 5, 1e-8)

    assert fabricated["mean_replay"] > unrelated["mean_replay"] + 10.0


def test_high_minority_cannot_inflate_one_sided_scale() -> None:
    values = {client_id: float(client_id % 5) / 10.0 for client_id in range(60)}
    values.update({client_id: 10.0 for client_id in range(60, 100)})
    scores = one_sided_robust_z(values, set(values), 1e-8)

    assert min(scores[client_id] for client_id in range(60, 100)) > 10.0


def test_isolated_profile_outlier_is_weak_but_history_match_is_strong() -> None:
    config = ExperimentConfig(
        methodology_version="swtcp_v12",
        cycle_min_reference_clients=10,
        cycle_scale_prior_strength=1.0,
    )
    clients = set(range(20))
    norms = {client_id: [1.0, 1.0] for client_id in clients}
    profiles = {
        client_id: [torch.tensor([1.0, 0.001 * (client_id % 3)])] * 2
        for client_id in clients
    }
    profiles[19] = [torch.tensor([0.0, 1.0]), torch.tensor([0.0, 1.0])]
    history = {
        client_id: [
            {"mean_replay": float(client_id % 3) / 10.0},
            {"mean_replay": float(client_id % 3) / 10.0},
        ]
        for client_id in clients
    }
    for client_id in (15, 16, 17, 18):
        history[client_id] = [{"mean_replay": 20.0}, {"mean_replay": 20.0}]

    evidence = evaluate_v12_cycle(
        coverage_norms=norms,
        coverage_profiles=profiles,
        coverage_history_scores=history,
        coverage_trap_ids={client_id: [0, 1] for client_id in clients},
        coverage_observation_rounds={client_id: [11, 12] for client_id in clients},
        active_clients=clients,
        checks=2,
        config=config,
        trusted_reference_clients=None,
        calibration_history=[],
        norm_scale_history=[],
        profile_scale_history=[],
    )

    assert not evidence["coherent_strong"][19]
    assert evidence["coherent_strong"][18]


def test_v12_detector_interface_has_no_ground_truth_or_attack_type() -> None:
    parameters = set(inspect.signature(evaluate_v12_cycle).parameters)
    assert "free_riders" not in parameters
    assert "is_free_rider" not in parameters
    assert "attack_type" not in parameters
