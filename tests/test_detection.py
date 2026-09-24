import torch

from config import ExperimentConfig
from server.detection import (
    combine_coverage_checks,
    evaluate_suspicion_group,
    evaluate_updates,
    evaluate_zero_updates_only,
    merge_detection_results,
    should_rehabilitate,
)
from train import build_layer_profile


def _batch(fr_norm: float) -> dict[int, torch.Tensor]:
    return {
        **{client_id: torch.tensor([1.0, 0.0]) for client_id in range(6)},
        **{client_id: torch.tensor([fr_norm, 0.0]) for client_id in range(6, 10)},
    }


def _profiles(*, outlying: bool = False) -> dict[int, torch.Tensor]:
    profiles = {client_id: torch.tensor([1.0, 0.0]) for client_id in range(10)}
    if outlying:
        profiles.update(
            {client_id: torch.tensor([0.0, 1.0]) for client_id in range(6, 10)}
        )
    return profiles


def test_magnitude_only_is_candidate_evidence_without_penalty() -> None:
    config = ExperimentConfig()
    results = evaluate_updates(
        _batch(fr_norm=3.0), _profiles(), torch.ones(2), set(), config
    )

    assert all(not results[client_id].flagged for client_id in range(6))
    assert all(results[client_id].magnitude_flag for client_id in range(6, 10))
    assert all(not results[client_id].profile_flag for client_id in range(6, 10))
    assert all(results[client_id].reason == "norm_z_outlier" for client_id in range(6, 10))
    assert all(results[client_id].penalty == 0 for client_id in range(6, 10))


def test_low_magnitude_only_is_two_sided_but_not_penalized() -> None:
    config = ExperimentConfig()
    results = evaluate_updates(
        _batch(fr_norm=0.1), _profiles(), torch.ones(2), set(), config
    )

    assert all(results[client_id].norm_z_score < -3 for client_id in range(6, 10))
    assert all(results[client_id].magnitude_flag for client_id in range(6, 10))
    assert all(results[client_id].penalty == 0 for client_id in range(6, 10))


def test_update_statistics_can_use_only_trusted_reference_clients() -> None:
    config = ExperimentConfig()
    honest_norms = [0.50, 0.60, 0.65, 0.70, 0.80, 0.85]
    deltas = {
        **{
            client_id: torch.tensor([norm, 0.0])
            for client_id, norm in enumerate(honest_norms)
        },
        **{
            client_id: torch.tensor([0.26, 0.0])
            for client_id in range(6, 10)
        },
    }
    profiles = {client_id: torch.tensor([1.0, 0.0]) for client_id in deltas}

    population_results = evaluate_updates(
        deltas, profiles, torch.ones(2), set(deltas), config
    )
    trusted_results = evaluate_updates(
        deltas,
        profiles,
        torch.ones(2),
        set(deltas),
        config,
        reference_ids=set(range(6)),
    )

    assert not population_results[6].magnitude_flag
    assert trusted_results[6].magnitude_flag


def test_profile_only_is_candidate_evidence_without_penalty() -> None:
    config = ExperimentConfig()
    deltas = {client_id: torch.tensor([1.0, 0.0]) for client_id in range(10)}
    results = evaluate_updates(
        deltas, _profiles(outlying=True), torch.ones(2), set(), config
    )

    assert all(not results[client_id].flagged for client_id in range(6))
    assert all(results[client_id].profile_flag for client_id in range(6, 10))
    assert all(not results[client_id].magnitude_flag for client_id in range(6, 10))
    assert all(results[client_id].penalty == 0 for client_id in range(6, 10))


def test_joint_magnitude_and_profile_failure_earns_penalty() -> None:
    config = ExperimentConfig()
    results = evaluate_updates(
        _batch(fr_norm=3.0), _profiles(outlying=True), torch.ones(2), set(), config
    )

    assert all(results[client_id].joint_flag_count == 1 for client_id in range(6, 10))
    assert all(results[client_id].penalty == 1 for client_id in range(6, 10))


def test_gradient_only_detection_leaves_legacy_loss_fields_empty() -> None:
    config = ExperimentConfig()
    deltas = {client_id: torch.tensor([1.0, 0.0]) for client_id in range(10)}
    results = evaluate_updates(deltas, _profiles(), torch.ones(2), set(), config)

    assert all(not result.flagged for result in results.values())
    assert all(result.loss_z_score is None for result in results.values())


def test_cosine_direction_never_causes_a_flag() -> None:
    config = ExperimentConfig()
    deltas = {client_id: torch.tensor([1.0, 0.0]) for client_id in range(10)}
    results = evaluate_updates(
        deltas, _profiles(), torch.tensor([-1.0, 0.0]), set(), config
    )

    assert all(result.cosine_similarity == -1.0 for result in results.values())
    assert all(not result.flagged for result in results.values())


def test_warmup_zero_only_check_ignores_nonzero_outliers() -> None:
    config = ExperimentConfig()
    results = evaluate_zero_updates_only(
        {0: torch.zeros(2), 1: torch.tensor([100.0, 0.0])}, config
    )

    assert set(results) == {0}
    assert results[0].reason == "zero_update"
    assert results[0].penalty == 5


def test_repeated_coverage_checks_penalize_only_joint_failures() -> None:
    config = ExperimentConfig()
    deltas = _batch(fr_norm=3.0)
    joint = evaluate_updates(
        deltas, _profiles(outlying=True), torch.ones(2), set(deltas), config
    )[6]
    magnitude_only = evaluate_updates(
        deltas, _profiles(), torch.ones(2), set(deltas), config
    )[6]

    assert combine_coverage_checks([joint, magnitude_only]).penalty == 2
    assert combine_coverage_checks([joint, joint]).penalty == 4
    assert combine_coverage_checks([joint, joint]).joint_flag_count == 2


def test_each_zero_update_in_double_coverage_adds_five_points() -> None:
    config = ExperimentConfig()
    zero = evaluate_zero_updates_only({0: torch.zeros(2)}, config)[0]
    deltas = _batch(fr_norm=3.0)
    joint = evaluate_updates(
        deltas, _profiles(outlying=True), torch.ones(2), set(deltas), config
    )[6]

    combined = combine_coverage_checks([zero, joint])

    assert combined.reason == "zero_update"
    assert combined.penalty == 7
    assert combine_coverage_checks([zero, zero]).penalty == 10


def test_coverage_reporting_keeps_the_largest_absolute_outlier() -> None:
    config = ExperimentConfig()
    positive = evaluate_updates(
        _batch(fr_norm=3.0), _profiles(), torch.ones(2), set(), config
    )[6]
    negative = evaluate_updates(
        _batch(fr_norm=0.1), _profiles(), torch.ones(2), set(), config
    )[6]

    combined = combine_coverage_checks([positive, negative])
    assert combined.norm_z_score == max(
        (positive.norm_z_score, negative.norm_z_score), key=abs
    )


def test_suspicion_group_uses_anchor_norm_and_profile_baselines() -> None:
    config = ExperimentConfig()
    deltas = {
        0: torch.tensor([2.0]), 1: torch.tensor([0.5]),
        10: torch.tensor([0.95]), 11: torch.tensor([1.0]), 12: torch.tensor([1.05]),
    }
    profiles = {
        0: torch.tensor([0.0, 1.0]), 1: torch.tensor([0.0, 1.0]),
        10: torch.tensor([1.0, 0.0]), 11: torch.tensor([1.0, 0.0]),
        12: torch.tensor([1.0, 0.0]),
    }
    results = evaluate_suspicion_group(
        deltas, profiles, {0, 1}, {10, 11, 12}, config
    )

    assert results[0].reason == "anchor_norm_outlier+layer_profile_outlier"
    assert results[0].penalty == 3
    assert results[1].reason == "anchor_norm_outlier+layer_profile_outlier"
    assert results[1].penalty == 3
    assert all(not results[client_id].flagged for client_id in (10, 11, 12))


def test_anchor_zero_update_still_gets_sendback_penalty() -> None:
    config = ExperimentConfig()
    deltas = {
        0: torch.tensor([1.0]), 10: torch.tensor([0.0]),
        11: torch.tensor([1.0]), 12: torch.tensor([1.1]),
    }
    profiles = {client_id: torch.tensor([1.0]) for client_id in deltas}
    result = evaluate_suspicion_group(
        deltas, profiles, {0}, {10, 11, 12}, config
    )[10]

    assert result.reason == "zero_update"
    assert result.penalty == 5


def test_layer_profile_is_scale_invariant() -> None:
    received = {"a": torch.zeros(2), "b": torch.zeros(1)}
    first = {"a": torch.tensor([3.0, 4.0]), "b": torch.tensor([5.0])}
    scaled = {key: value * 7 for key, value in first.items()}

    assert torch.allclose(
        build_layer_profile(first, received, 1e-6),
        build_layer_profile(scaled, received, 1e-6),
    )


def test_dodge_rehabilitation_requires_ten_probes_and_at_most_ten_percent() -> None:
    config = ExperimentConfig(methodology_version="swtcp_v8")

    assert not should_rehabilitate(9, 0, config)
    assert should_rehabilitate(10, 0, config)
    assert should_rehabilitate(10, 1, config)
    assert not should_rehabilitate(10, 2, config)
    assert config.removal_threshold == 15


def test_independent_zero_and_joint_flags_are_not_overwritten() -> None:
    config = ExperimentConfig()
    zero = evaluate_zero_updates_only({0: torch.zeros(1)}, config)[0]
    joint = evaluate_updates(
        _batch(fr_norm=3.0), _profiles(outlying=True), torch.ones(2), set(), config
    )[6]
    combined = merge_detection_results(zero, joint)

    assert combined.flagged
    assert combined.penalty == 6
    assert "zero_update" in combined.reason
    assert combined.joint_flag_count == 1
