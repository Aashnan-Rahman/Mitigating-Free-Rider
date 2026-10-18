import copy

import pytest
import torch

from benchmark_mnist_std_dagmm import prepare_std, summaries, workload
from comparison.std_dagmm import StdDagmm


def test_std_model_reconstructs_full_input_and_appends_std():
    torch.manual_seed(1)
    model = StdDagmm(16, widths=(8, 4, 2))
    x = torch.randn(12, 16)
    reconstruction, z, gamma = model(x)
    assert reconstruction.shape == x.shape and z.shape == (12, 5)
    assert gamma.shape == (12, 3)
    assert torch.allclose(z[:, -1], x.std(dim=1, correction=0))
    assert torch.allclose(gamma.sum(1), torch.ones(12))


def test_joint_objective_has_finite_gradients_and_handles_low_rank_covariance():
    model = StdDagmm(16, widths=(8, 4, 2))
    x = torch.randn(3, 16)  # latent+3 > sample count: ridge is necessary
    reconstruction, z, gamma = model(x)
    loss, energy = model.objective(x, reconstruction, z, gamma)
    assert torch.isfinite(loss) and torch.isfinite(energy).all()
    loss.backward()
    assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters())


def test_energy_agrees_with_torch_gaussian_mixture_density():
    torch.manual_seed(2)
    z = torch.randn(7, 5, dtype=torch.float64)
    means = torch.randn(3, 5, dtype=torch.float64)
    covariance = torch.eye(5, dtype=torch.float64).repeat(3, 1, 1)
    phi = torch.tensor([.2, .5, .3], dtype=torch.float64)
    expected = -torch.logsumexp(torch.stack([
        torch.distributions.MultivariateNormal(means[k], covariance[k]).log_prob(z)+phi[k].log()
        for k in range(3)], dim=1), dim=1)
    assert torch.allclose(StdDagmm.energy(z, (phi, means, covariance)), expected)


def test_returned_states_have_same_flattening_order_as_baseline_preparation():
    base, batches, digest, dimensions = workload(2, 42)
    assert dimensions == 206922 and len(digest) == 64 and len(batches) == 2
    x = prepare_std(base, batches[0])
    assert x.shape == (2, dimensions)
    from clients.attacks import flatten_delta
    assert torch.equal(x[0], flatten_delta(batches[0][0], base))
    assert workload(2, 42)[2] == digest


def fixtures():
    ours = dict(input_sha256='same', clients=100,
        trials=[dict(total_seconds=2.), dict(total_seconds=4.)])
    std = dict(input_sha256='same', clients=100, trials=[
        dict(trial=i, input_batch=t, preparation_seconds=.5, inference_seconds=.5, fit_seconds=4.)
        for i in range(2) for t in range(2)])
    return ours, std


def test_percentages_distinguish_online_from_fit_and_keep_negative_savings():
    ours, std = fixtures()
    result = summaries(ours, std)
    assert result['ours_online_time_reduction_percent'] == -50
    assert result['ours_fit_plus_score_time_reduction_percent'] == 70
    assert result['overall_federated_round_overhead_percent'] is None


def test_mismatched_workload_and_incomplete_paired_trial_are_rejected():
    ours, std = fixtures()
    altered = copy.deepcopy(std)
    altered['input_sha256'] = 'different'
    with pytest.raises(ValueError, match='identical'):
        summaries(ours, altered)
    std['trials'].pop()
    with pytest.raises(ValueError, match='Incomplete'):
        summaries(ours, std)


def test_invalid_network_dimensions_are_rejected():
    with pytest.raises(ValueError):
        StdDagmm(0)
