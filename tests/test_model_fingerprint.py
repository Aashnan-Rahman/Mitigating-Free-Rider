import torch
from collections import deque

from config import ExperimentConfig
from server.model_fingerprint import model_fingerprint


def test_model_fingerprint_matches_exact_clones() -> None:
    state = {
        "weight": torch.tensor([[1.0, 2.0]], dtype=torch.float32),
        "counter": torch.tensor(3, dtype=torch.int64),
    }
    clone = {key: value.clone() for key, value in state.items()}

    assert model_fingerprint(state) == model_fingerprint(clone)


def test_model_fingerprint_changes_with_tensor_content() -> None:
    original = {"weight": torch.tensor([1.0, 2.0])}
    changed = {"weight": torch.tensor([1.0, 2.0001])}

    assert model_fingerprint(original) != model_fingerprint(changed)


def test_default_replay_history_retains_only_the_previous_model() -> None:
    config = ExperimentConfig()
    history: deque[str] = deque(maxlen=config.sendback_history_size)
    first = model_fingerprint({"weight": torch.tensor([1.0])})
    second = model_fingerprint({"weight": torch.tensor([2.0])})

    history.append(first)
    assert first in history
    history.append(second)
    assert list(history) == [second]
