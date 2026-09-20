from __future__ import annotations

import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from comparison.common import upper_z_flags
from comparison.frad import FradDetector, FradInputs, _pagerank_from_contributions
from comparison.frida import FridaLossDetector


def test_upper_z_flags_marks_only_high_outliers() -> None:
    flags, z_scores = upper_z_flags({0: 1.0, 1: 1.0, 2: 10.0}, threshold=1.0)
    assert flags == {0: False, 1: False, 2: True}
    assert z_scores[2] > 1.0


def test_pagerank_is_finite_and_normalized() -> None:
    values = torch.tensor([[0.0, 0.0], [0.1, 0.2], [1.0, 1.0]])
    rank = _pagerank_from_contributions(values, damping=0.85, iterations=30)
    assert torch.isfinite(rank).all()
    assert torch.allclose(rank.sum(), torch.tensor(1.0), atol=1e-5)


def test_frad_returns_one_score_per_client() -> None:
    torch.manual_seed(4)
    inputs = FradInputs(
        computation=torch.tensor([1.0, 0.9, 0.1, 0.0]),
        communication=torch.tensor([1.0, 1.0, 0.5, 0.5]),
        data_quality=torch.tensor([1.0, 0.8, 0.1, 0.0]),
        history=torch.tensor([0.8, 0.7, 0.1, 0.0]),
    )
    output = FradDetector(epochs=2, anomaly_quantile=0.5).detect(
        inputs, torch.device("cpu")
    )
    assert set(output.scores) == {0, 1, 2, 3}
    assert all(torch.isfinite(torch.tensor(value)) for value in output.scores.values())
    assert output.metadata["official_code"] is False


def test_frida_loss_restores_model_state() -> None:
    model = nn.Linear(2, 2)
    original = {key: value.detach().clone() for key, value in model.state_dict().items()}
    high_loss_state = {key: value.detach().clone() for key, value in original.items()}
    high_loss_state["bias"] = torch.tensor([10.0, -10.0])
    states = {0: original, 1: high_loss_state}
    loader = DataLoader(
        TensorDataset(torch.zeros(4, 2), torch.ones(4, dtype=torch.long)),
        batch_size=2,
    )
    output = FridaLossDetector(z_threshold=0.5).detect(
        model, states, loader, torch.device("cpu")
    )
    assert output.flags[1]
    for key, value in original.items():
        assert torch.equal(model.state_dict()[key], value)
