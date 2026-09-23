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
