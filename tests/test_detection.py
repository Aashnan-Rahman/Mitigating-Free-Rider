import torch

from config import ExperimentConfig
from server.detection import (
    combine_coverage_checks,
    evaluate_suspicion_group,
    evaluate_updates,
    merge_detection_results,
    should_rehabilitate,
)


def _batch(fr_norm: float) -> dict[int, torch.Tensor]:
    return {
        **{client_id: torch.tensor([1.0, 0.0]) for client_id in range(6)},
        **{client_id: torch.tensor([fr_norm, 0.0]) for client_id in range(6, 10)},
    }


def test_high_norm_z_flags_outlying_updates() -> None:
    config = ExperimentConfig()
    deltas = _batch(fr_norm=3.0)

    results = evaluate_updates(deltas, torch.ones(2), set(), config)

    assert all(not results[client_id].flagged for client_id in range(6))
    assert all(results[client_id].reason == "norm_z_outlier" for client_id in range(6, 10))


def test_low_norm_z_flags_outlying_updates() -> None:
    config = ExperimentConfig()
    deltas = _batch(fr_norm=0.1)

    results = evaluate_updates(deltas, torch.ones(2), set(), config)

    assert all(not results[client_id].flagged for client_id in range(6))
    assert all(results[client_id].norm_z_score < -3 for client_id in range(6, 10))
    assert all(results[client_id].reason == "norm_z_outlier" for client_id in range(6, 10))


def test_gradient_only_detection_leaves_legacy_loss_fields_empty() -> None:
    config = ExperimentConfig()
    deltas = {client_id: torch.tensor([1.0, 0.0]) for client_id in range(10)}

    results = evaluate_updates(deltas, torch.ones(2), set(), config)

    assert all(not result.flagged for result in results.values())
    assert all(result.loss_z_score is None for result in results.values())


def test_cosine_direction_never_causes_a_flag() -> None:
    config = ExperimentConfig()
    deltas = {client_id: torch.tensor([1.0, 0.0]) for client_id in range(10)}
    results = evaluate_updates(deltas, torch.tensor([-1.0, 0.0]), set(), config)

    assert all(result.cosine_similarity == -1.0 for result in results.values())
    assert all(not result.flagged for result in results.values())


def test_zero_update_penalty_applies_during_warmup() -> None:
    config = ExperimentConfig()
    deltas = {
        0: torch.zeros(2),
        **{client_id: torch.tensor([1.0, 0.0]) for client_id in range(1, 10)},
    }
    results = evaluate_updates(deltas, torch.ones(2), set(), config)

    assert results[0].flagged
    assert results[0].reason == "zero_update"
    assert results[0].penalty == 5


def test_repeated_coverage_checks_add_one_point_per_magnitude_flag() -> None:
    config = ExperimentConfig()
    deltas = _batch(fr_norm=3.0)
    results = evaluate_updates(deltas, torch.ones(2), set(), config)
    normal = results[0]
    suspicious = results[6]

    assert combine_coverage_checks([suspicious, normal]).penalty == 1
    assert combine_coverage_checks([suspicious, suspicious]).penalty == 2


def test_each_zero_update_in_double_coverage_adds_five_points() -> None:
    config = ExperimentConfig()
    zero_results = evaluate_updates(
        {0: torch.zeros(2)}, torch.ones(2), {0}, config
    )
    deltas = _batch(fr_norm=3.0)
    suspicious = evaluate_updates(
        deltas, torch.ones(2), set(), config
    )[6]

    combined = combine_coverage_checks([zero_results[0], suspicious])

    assert combined.reason == "zero_update"
    assert combined.penalty == 6
    assert combine_coverage_checks([zero_results[0], zero_results[0]]).penalty == 10


def test_coverage_reporting_keeps_the_largest_absolute_outlier() -> None:
    config = ExperimentConfig()
    positive = evaluate_updates(
        _batch(fr_norm=3.0), torch.ones(2), set(), config
    )[6]
    negative = evaluate_updates(
        _batch(fr_norm=0.1), torch.ones(2), set(), config
    )[6]

    combined = combine_coverage_checks([positive, negative])

    expected = max(
        (positive.norm_z_score, negative.norm_z_score), key=abs
    )
    assert combined.norm_z_score == expected


def test_suspicion_group_uses_anchor_range_and_penalty_three() -> None:
    config = ExperimentConfig()
    deltas = {
        0: torch.tensor([2.0]),
        1: torch.tensor([0.5]),
        10: torch.tensor([0.95]),
        11: torch.tensor([1.0]),
        12: torch.tensor([1.05]),
    }

    results = evaluate_suspicion_group(deltas, {0, 1}, {10, 11, 12}, config)

    assert results[0].reason == "anchor_norm_outlier"
    assert results[0].penalty == 3
    assert results[1].reason == "anchor_norm_outlier"
    assert results[1].penalty == 3
    assert all(not results[client_id].flagged for client_id in (10, 11, 12))


def test_anchor_zero_update_still_gets_sendback_penalty() -> None:
    config = ExperimentConfig()
    deltas = {
        0: torch.tensor([1.0]),
        10: torch.tensor([0.0]),
        11: torch.tensor([1.0]),
        12: torch.tensor([1.1]),
    }

    result = evaluate_suspicion_group(deltas, {0}, {10, 11, 12}, config)[10]

    assert result.reason == "zero_update"
    assert result.penalty == 5


def test_dodge_rehabilitation_requires_ten_probes_and_at_most_ten_percent() -> None:
    config = ExperimentConfig()

    assert not should_rehabilitate(9, 0, config)
    assert should_rehabilitate(10, 0, config)
    assert should_rehabilitate(10, 1, config)
    assert not should_rehabilitate(10, 2, config)
    assert config.removal_threshold == 15


def test_independent_zero_and_surveillance_flags_are_not_overwritten() -> None:
    config = ExperimentConfig()
    zero = evaluate_updates(
        {0: torch.zeros(1)}, torch.ones(1), set(), config
    )[0]
    deltas = _batch(fr_norm=3.0)
    magnitude = evaluate_updates(
        deltas, torch.ones(2), set(), config
    )[6]

    combined = merge_detection_results(zero, magnitude)

    assert combined.flagged
    assert combined.penalty == 6
    assert "zero_update" in combined.reason
