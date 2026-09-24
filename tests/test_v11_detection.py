import math
import inspect

import torch

from config import ExperimentConfig
from server.v11_detection import (
    MAD_NORMAL_CONSISTENCY,
    corrected_scale,
    cutoff_from_false_alarm_budget,
    evaluate_v11_cycle,
)


def test_mad_consistency_factor_is_the_normal_conversion() -> None:
    assert math.isclose(MAD_NORMAL_CONSISTENCY, 1.4826022185, rel_tol=1e-9)


def test_corrected_scale_uses_prior_history_without_an_absolute_detector_floor() -> None:
    config = ExperimentConfig(methodology_version="swtcp_v11")
    _, raw_mad, current = corrected_scale([0.0, 1.0, 2.0], [], config)
    assert raw_mad == 1.0
    assert math.isclose(current, MAD_NORMAL_CONSISTENCY, rel_tol=1e-9)

    _, _, stabilized = corrected_scale([0.99, 1.0, 1.01], [2.0], config)
    assert stabilized > MAD_NORMAL_CONSISTENCY * 0.01


def test_cutoff_is_derived_from_risk_budget_and_prior_cycles() -> None:
    config = ExperimentConfig(
        methodology_version="swtcp_v11",
        cycle_target_false_alarm_rate=0.01,
    )
    base = cutoff_from_false_alarm_budget(config, 2, [])
    adapted = cutoff_from_false_alarm_budget(config, 2, [[1.0, 2.0, 4.0]])

    assert 2.9 < base < 3.0
    assert adapted == 4.0


def test_same_signature_is_strong_but_cross_signal_failures_are_weak() -> None:
    config = ExperimentConfig(
        methodology_version="swtcp_v11",
        cycle_min_reference_clients=10,
        cycle_scale_prior_strength=1.0,
    )
    reference_clients = set(range(20))
    active_clients = reference_clients | {20, 21}
    norms = {
        client_id: [1.0 + (client_id % 5) * 0.01] * 2
        for client_id in reference_clients
    }
    profiles = {
        client_id: [torch.tensor([1.0, 0.001 * (client_id % 4)])] * 2
        for client_id in reference_clients
    }
    norms[20] = [4.0, 4.0]
    profiles[20] = [torch.tensor([1.0, 0.0]), torch.tensor([1.0, 0.0])]
    norms[21] = [4.0, 1.02]
    profiles[21] = [torch.tensor([1.0, 0.0]), torch.tensor([0.0, 1.0])]

    evidence = evaluate_v11_cycle(
        coverage_norms=norms,
        coverage_profiles=profiles,
        coverage_trap_ids={client_id: [0, 1] for client_id in active_clients},
        coverage_observation_rounds={client_id: [11, 12] for client_id in active_clients},
        active_clients=active_clients,
        checks=2,
        config=config,
        trusted_reference_clients=reference_clients,
        calibration_history=[],
        norm_scale_history=[],
        profile_scale_history=[],
    )

    assert evidence["reference_valid"]
    assert evidence["coherent_strong"][20]
    assert not evidence["coherent_strong"][21]
    assert evidence["reference_outliers"] == set()


def test_v11_detector_interface_has_no_ground_truth_or_attack_type_input() -> None:
    parameters = set(inspect.signature(evaluate_v11_cycle).parameters)
    assert "free_riders" not in parameters
    assert "is_free_rider" not in parameters
    assert "attack_type" not in parameters
