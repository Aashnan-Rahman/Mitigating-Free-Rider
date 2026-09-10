import torch

from clients.attacks import FreeRiderAttacker
from config import ExperimentConfig


def _state(value: float) -> dict[str, torch.Tensor]:
    return {"weight": torch.tensor([value, value], dtype=torch.float32)}


def _attacker(attack_type: str, **overrides) -> tuple[FreeRiderAttacker, torch.Generator]:
    config = ExperimentConfig(attack_type=attack_type, **overrides)
    generator = torch.Generator(device="cpu")
    generator.manual_seed(7)
    return FreeRiderAttacker(config, torch.device("cpu")), generator


def test_fr1_replays_only_models_the_client_previously_received() -> None:
    attacker, generator = _attacker("FR1")

    first = attacker.fabricate(4, _state(1.0), 1, generator)
    second = attacker.fabricate(4, _state(3.0), 2, generator)

    assert torch.equal(first["weight"], _state(1.0)["weight"])
    assert torch.equal(second["weight"], _state(1.0)["weight"])


def test_fr2_adds_a_bounded_random_update_instead_of_redrawing_weights() -> None:
    update_range = 0.01
    attacker, generator = _attacker("FR2", fr2_update_range=update_range)
    received = _state(5.0)

    returned = attacker.fabricate(2, received, 1, generator)
    delta = returned["weight"] - received["weight"]

    assert torch.any(delta != 0)
    assert torch.all(delta.abs() <= update_range)


def test_fr3_averages_every_received_model_without_trap_metadata() -> None:
    attacker, generator = _attacker("FR3", fr3_window=2)

    first = attacker.fabricate(1, _state(1.0), 1, generator)
    second = attacker.fabricate(1, _state(3.0), 2, generator)
    third = attacker.fabricate(1, _state(5.0), 3, generator)

    assert torch.equal(first["weight"], _state(1.0)["weight"])
    assert torch.equal(second["weight"], _state(2.0)["weight"])
    assert torch.equal(third["weight"], _state(4.0)["weight"])


def test_fr4_uses_every_received_model_in_its_trajectory() -> None:
    attacker, generator = _attacker(
        "FR4", fr4_history_size=2, fr4_noise_fraction=0.0
    )

    attacker.fabricate(8, _state(0.0), 1, generator)
    second = attacker.fabricate(8, _state(1.0), 2, generator)
    third = attacker.fabricate(8, _state(11.0), 3, generator)

    # After observations 0 -> 1, the expected delta is 1.
    assert torch.allclose(second["weight"], _state(2.0)["weight"])
    # The next received model is not labelled as a trap or excluded. Its 10-unit
    # movement joins history, so the two-delta mean is (1 + 10) / 2 = 5.5.
    assert torch.allclose(third["weight"], _state(16.5)["weight"])


def test_attacker_visible_history_survives_checkpoint_restore() -> None:
    attacker, generator = _attacker("FR3", fr3_window=2)
    attacker.fabricate(3, _state(1.0), 1, generator)
    attacker.fabricate(3, _state(3.0), 2, generator)

    restored, restored_generator = _attacker("FR3", fr3_window=2)
    restored.load_state_dict(attacker.state_dict())
    returned = restored.fabricate(3, _state(5.0), 3, restored_generator)

    assert torch.equal(returned["weight"], _state(4.0)["weight"])
