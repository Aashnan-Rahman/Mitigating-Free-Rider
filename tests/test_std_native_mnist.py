import pytest
import torch

from run_std_dagmm_mnist import high_energy_flags, projection
from comparison.std_dagmm import StdDagmm


def test_flag_rule_is_one_sided_and_has_no_attack_quota():
    flags, threshold, mean, sd = high_energy_flags([1, 1, 1, 10])
    assert flags == [False, False, False, True]
    assert threshold == pytest.approx(mean+sd)
    assert high_energy_flags([2, 2, 2])[0] == [False, False, False]


def test_invalid_scores_do_not_produce_detection_results():
    for values in ([float('nan'),1], [float('inf'),1], [1]):
        with pytest.raises(ValueError):
            high_energy_flags(values)


def test_projection_is_explicitly_fixed_workload_and_uses_observed_components():
    rows = [dict(preparation_seconds=1., fit_seconds=10., inference_seconds=2., decision_seconds=1.,
        detector_seconds=14., baseline_compute_seconds=28., round_compute_seconds=42.) for _ in range(10)]
    result = projection(rows)
    assert result['detector_seconds']['projected_100_round_seconds'] == 1400
    assert result['added_detector_time_percent_of_same_trajectory_baseline'] == 50
    assert result['detector_fraction_of_instrumented_compute_percent'] == pytest.approx(100/3)
    assert result['fit_seconds']['coefficient_of_variation'] == 0


def test_zero_and_small_actual_update_scales_have_finite_joint_objective():
    torch.manual_seed(42)
    model = StdDagmm(16, widths=(8,4,2))
    x = torch.randn(20,16)*.001
    x[:8] = 0
    reconstructed, z, gamma = model(x)
    loss, energies = model.objective(x, reconstructed, z, gamma)
    assert torch.isfinite(loss) and torch.isfinite(energies).all()
    loss.backward()
    assert all(torch.isfinite(p.grad).all() for p in model.parameters())


def test_cifar_update_dimension_includes_floating_buffers_not_integer_counters():
    from clients.attacks import flatten_delta
    from models.architectures import get_model
    state = get_model('cifar10').state_dict()
    delta = flatten_delta(state, state)
    assert delta.numel() == sum(v.numel() for v in state.values() if torch.is_floating_point(v))
    assert delta.numel() == 621258
    assert delta.count_nonzero() == 0


def test_generic_runner_keeps_native_flag_and_projection_rules():
    from run_std_dagmm_native import high_energy_flags as native_flags, projection as native_projection
    assert native_flags([1,1,1,10]) == high_energy_flags([1,1,1,10])
    rows = [dict(preparation_seconds=1., fit_seconds=10., inference_seconds=2., decision_seconds=1.,
        detector_seconds=14., baseline_compute_seconds=28., round_compute_seconds=42.) for _ in range(10)]
    assert native_projection(rows) == projection(rows)
