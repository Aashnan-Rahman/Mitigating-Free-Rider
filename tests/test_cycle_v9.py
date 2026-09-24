import random

from config import ExperimentConfig
from server.cycle_scoring import (
    cycle_classification,
    score_change,
    score_requires_removal,
    sendbacks_require_removal,
)
from server.cycle_trap_selection import CycleTrapSelector


def test_double_cycle_probes_every_client_once_with_each_trap():
    config = ExperimentConfig(methodology_version="swtcp_v9", num_clients=100)
    selector = CycleTrapSelector(config, random.Random(42))
    clients = list(range(100))
    selections = [selector.select(round_idx, clients, {}, {}) for round_idx in range(11, 21)]

    assert all(item.phase == "double_probe" for item in selections)
    assert selections[-1].coverage_complete
    assert all(len(item.trapped_clients) == 20 for item in selections)
    assert len({frozenset(item.trapped_clients) for item in selections}) == 10
    for client_id in clients:
        trap_ids = [
            item.coverage_trap_id
            for item in selections
            if client_id in item.trapped_clients
        ]
        assert sorted(trap_ids) == [0, 1]


def test_clean_double_cycle_relaxes_and_candidate_restores_double_mode():
    config = ExperimentConfig(methodology_version="swtcp_v9", num_clients=100)
    selector = CycleTrapSelector(config, random.Random(42))
    clients = list(range(100))
    for round_idx in range(11, 21):
        selector.select(round_idx, clients, {}, {})
    selector.finish_cycle(anomaly_found=False)
    assert selector.select(21, clients, {}, {}).phase == "single_probe"
    selector.finish_cycle(anomaly_found=True)
    assert selector.select(22, clients, {}, {}).phase == "double_probe"


def test_v10_uses_two_clean_double_cycles_then_two_clean_single_cycles():
    config = ExperimentConfig(methodology_version="swtcp_v10", num_clients=100)
    selector = CycleTrapSelector(config, random.Random(42))
    clients = list(range(100))

    for round_idx in range(11, 21):
        selector.select(round_idx, clients, {}, {}, set(), set())
    selector.finish_cycle(anomaly_found=False)
    assert selector.mode == "double_probe"

    for round_idx in range(21, 31):
        selector.select(round_idx, clients, {}, {}, set(), set())
    selector.finish_cycle(anomaly_found=False)
    assert selector.mode == "single_probe"

    for round_idx in range(31, 41):
        selector.select(round_idx, clients, {}, {}, set(), set())
    selector.finish_cycle(anomaly_found=False)
    assert selector.mode == "single_probe"

    for round_idx in range(41, 51):
        selector.select(round_idx, clients, {}, {}, set(), set())
    selector.finish_cycle(anomaly_found=False)
    assert selector.mode == "dormant"

    dormant = [selector.select(round_idx, clients, {}, {}, set(), set()) for round_idx in range(51, 71)]
    assert all(item.phase == "dormant" for item in dormant)
    assert selector.select(71, clients, {}, {}, set(), set()).phase == "single_probe"


def test_v10_double_cycle_gives_each_client_both_frozen_traps_once():
    config = ExperimentConfig(methodology_version="swtcp_v10", num_clients=100)
    selector = CycleTrapSelector(config, random.Random(43))
    clients = list(range(100))
    suspects = set(range(35))
    candidates = set(range(35, 50))
    selections = [
        selector.select(round_idx, clients, {}, {}, suspects, candidates)
        for round_idx in range(11, 21)
    ]

    assert selections[-1].coverage_complete
    for client_id in clients:
        assert sorted(
            item.coverage_trap_id
            for item in selections
            if client_id in item.trapped_clients
        ) == [0, 1]


def test_v10_groups_are_state_homogeneous_and_total_ten():
    config = ExperimentConfig(methodology_version="swtcp_v10", num_clients=100)
    selector = CycleTrapSelector(config, random.Random(42))
    suspects = set(range(35))
    candidates = set(range(35, 50))
    groups = selector._build_state_groups(list(range(100)), suspects, candidates)

    assert len(groups) == 10
    assert sorted(len(group) for group in groups) == [7, 8, 10, 10, 10, 10, 10, 11, 12, 12]
    for group in groups:
        states = {
            "S" if client_id in suspects else "C" if client_id in candidates else "R"
            for client_id in group
        }
        assert len(states) == 1


def test_v9_score_and_sendback_boundaries():
    assert cycle_classification(0, 2) == "clear"
    assert cycle_classification(1, 2) == "C"
    assert cycle_classification(2, 2) == "S"
    assert cycle_classification(1, 1) == "C"
    assert score_change("clear") == 0.5
    assert score_change("C") == -1.0
    assert score_change("S") == -2.0
    assert not score_requires_removal(-3.5)
    assert score_requires_removal(-4.0)
    assert not sendbacks_require_removal(5, 9, 10)
    assert sendbacks_require_removal(5, 10, 10)
