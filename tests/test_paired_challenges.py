import random
from dataclasses import replace

import pytest
import torch

from config import ExperimentConfig
from server.paired_challenges import (make_pair, pair_features, summarize_response,
                                     derive_seed, stream_seeds)
from server.cycle_trap_selection import CycleTrapSelector


def test_pair_is_symmetric_and_fresh_randomness_is_isolated():
    base = {"weight": torch.arange(20, dtype=torch.float32), "counter": torch.tensor(1)}
    cfg = ExperimentConfig(paired_measurement_only=True)
    s = stream_seeds(cfg)
    other = stream_seeds(replace(cfg, attack_seed=99))
    assert {k: v for k, v in s.items() if k != "attack"} == {
        k: v for k, v in other.items() if k != "attack"}
    attack_generator = torch.Generator().manual_seed(other["attack"])
    torch.randn(1000, generator=attack_generator)
    pair = make_pair(base, .01, 1e-4, torch.Generator().manual_seed(s["trap"]))
    repeated = make_pair(base, .01, 1e-4, torch.Generator().manual_seed(other["trap"]))
    assert torch.equal(pair[0]["weight"], repeated[0]["weight"])
    assert torch.allclose((pair[0]["weight"] + pair[1]["weight"]) / 2, base["weight"])
    assert pair[0]["counter"].item() == pair[1]["counter"].item() == 1
    assert derive_seed(s["trap"], "cycle:1") != derive_seed(s["trap"], "cycle:2")


def test_gain_recovers_a_known_linear_response_without_classifying():
    base = {"weight": torch.arange(20, dtype=torch.float32)}
    pair = make_pair(base, .01, 1e-4, torch.Generator().manual_seed(17))
    h = (pair[0]["weight"] - pair[1]["weight"]) / 2
    common = torch.ones(20)
    observations = {0: summarize_response(common + 2 * h, pair),
                    1: summarize_response(common - 2 * h, pair)}
    f = pair_features(observations)
    assert f["directional_gain"] == pytest.approx(2, abs=1e-5)
    assert f["layer_gains"][0] == pytest.approx(2, abs=1e-5)
    assert "flagged" not in f
    with pytest.raises(ValueError, match="Both"):
        pair_features({0: observations[0]})


@pytest.mark.parametrize("count", [100, 60, 7])
def test_balanced_schedule_covers_each_client_twice_with_equal_gaps(count):
    cfg = ExperimentConfig(paired_measurement_only=True)
    selector = CycleTrapSelector(cfg, random.Random(9))
    queue = selector._build_cycle(list(range(count)), set(), set())
    rounds = {client: {} for client in range(count)}
    for round_index, (sign, clients) in enumerate(queue):
        for client in clients:
            assert sign not in rounds[client]
            rounds[client][sign] = round_index
    assert all(set(pair) == {0, 1} for pair in rounds.values())
    assert len({abs(pair[0] - pair[1]) for pair in rounds.values()}) == 1
    first_signs = [sign for sign, _ in queue[:len(queue) // 2]]
    assert abs(first_signs.count(0) - first_signs.count(1)) <= 1
    selector.finish_cycle(True)
    assert selector.mode == "double_probe"


def test_server_feature_interface_has_no_attack_configuration():
    import inspect
    assert set(inspect.signature(pair_features).parameters) == {"observations"}
    assert set(inspect.signature(summarize_response).parameters) == {"delta", "pair"}


def test_validation_plan_is_fixed_and_has_matched_controls():
    import json
    from pathlib import Path
    from run_experiments import expand_plan
    plan = json.loads(Path("configs/v13_paired_mnist_validation_plan.json").read_text())
    runs = expand_plan(plan, False)
    assert len(runs) == 26
    assert len({run["id"] for run in runs}) == 26
    assert [run["config"]["free_rider_pct"] for run in runs[:2]] == [0, .4]
    for run in runs:
        cfg = ExperimentConfig.from_dict({**plan["defaults"], **run["config"]})
        cfg.validate()
        assert cfg.paired_measurement_only and cfg.num_rounds == 40
    for stage in plan["stages"]:
        if stage["id"].startswith("noniid_") and stage["id"] != "noniid_baseline":
            seed_overrides = [key for key in stage["matrix"] if key.endswith("_seed")]
            assert len(seed_overrides) == 1
