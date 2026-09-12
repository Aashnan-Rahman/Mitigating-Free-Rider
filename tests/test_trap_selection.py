import random
from collections import Counter

from config import ExperimentConfig
from server.trap_selection import TrapSelector


def test_coverage_probes_two_groups_and_every_client_twice() -> None:
    config = ExperimentConfig(num_clients=100, warmup_rounds=10, trap_fraction=0.10)
    selector = TrapSelector(config, random.Random(42))
    active_clients = list(range(config.num_clients))
    penalties = {client_id: 0 for client_id in active_clients}
    flags = {client_id: 0 for client_id in active_clients}

    selections = []
    round_idx = config.warmup_rounds + 1
    while True:
        selection = selector.select(round_idx, active_clients, penalties, flags)
        selections.append(selection)
        if selection.coverage_complete:
            break
        round_idx += 1

    assert len(selections) == 10
    assert all(len(selection.trapped_clients) == 20 for selection in selections)
    assert len({frozenset(selection.trapped_clients) for selection in selections}) == 10
    assert Counter(selection.coverage_trap_id for selection in selections) == {0: 5, 1: 5}
    probe_counts = Counter(
        client_id
        for selection in selections
        for client_id in selection.trapped_clients
    )
    assert set(probe_counts) == set(active_clients)
    assert set(probe_counts.values()) == {2}
    per_trap_counts = Counter(
        (client_id, selection.coverage_trap_id)
        for selection in selections
        for client_id in selection.trapped_clients
    )
    assert set(per_trap_counts.values()) == {1}


def test_warmup_has_no_trapped_clients() -> None:
    config = ExperimentConfig(num_clients=100, warmup_rounds=10)
    selector = TrapSelector(config, random.Random(42))
    active_clients = list(range(config.num_clients))
    penalties = {client_id: 0 for client_id in active_clients}
    flags = {client_id: 0 for client_id in active_clients}

    for round_idx in range(1, config.warmup_rounds + 1):
        selection = selector.select(round_idx, active_clients, penalties, flags)
        assert selection.phase == "warmup"
        assert not selection.trapped_clients


def test_post_coverage_uses_four_suspicion_groups_ten_anchors_and_ten_y_groups() -> None:
    config = ExperimentConfig(num_clients=100)
    selector = TrapSelector(config, random.Random(42))
    selector.initial_coverage_done = True
    active_clients = list(range(100))
    suspected = set(range(45))
    penalties = {client_id: int(client_id in suspected) for client_id in active_clients}
    flags = penalties.copy()

    selections = [
        selector.select(round_idx, active_clients, penalties, flags, suspected)
        for round_idx in range(21, 31)
    ]

    assert all(len(selection.suspicion_groups) == 4 for selection in selections)
    assert all(
        set().union(*(suspects for suspects, _, _ in selection.suspicion_groups)) == suspected
        for selection in selections
    )
    assert all(len(selection.anchors) == 10 for selection in selections)
    assert all(
        max(len(anchors) for _, _, anchors in selection.suspicion_groups) <= 3
        for selection in selections
    )
    assert sum(len(selection.surveillance_clients) for selection in selections) == 45
    assert selections[-1].surveillance_complete


def test_released_anchors_join_an_unfinished_y_sweep_without_duplicate_checks() -> None:
    config = ExperimentConfig(num_clients=100)
    selector = TrapSelector(config, random.Random(7))
    selector.initial_coverage_done = True
    active_clients = list(range(100))
    penalties = {client_id: 0 for client_id in active_clients}
    flags = penalties.copy()

    first = selector.select(21, active_clients, penalties, flags, set(range(45)))
    observed = set(first.surveillance_clients)
    for round_idx in range(22, 31):
        selection = selector.select(
            round_idx, active_clients, penalties, flags, set(range(15))
        )
        assert observed.isdisjoint(selection.surveillance_clients)
        observed.update(selection.surveillance_clients)

    assert len(observed) == 82
    assert selection.surveillance_complete


def test_empty_suspicion_pool_still_runs_exactly_ten_y_groups() -> None:
    config = ExperimentConfig(num_clients=100)
    selector = TrapSelector(config, random.Random(11))
    selector.initial_coverage_done = True
    active_clients = list(range(100))
    penalties = {client_id: 0 for client_id in active_clients}
    flags = penalties.copy()

    selections = [
        selector.select(round_idx, active_clients, penalties, flags, set())
        for round_idx in range(21, 31)
    ]

    assert all(selection.phase == "surveillance" for selection in selections)
    assert all(not selection.suspicion_groups for selection in selections)
    assert sum(len(selection.surveillance_clients) for selection in selections) == 100
    assert selections[-1].surveillance_complete


def test_anchors_rejoin_unfinished_y_sweep_when_suspicion_ends() -> None:
    config = ExperimentConfig(num_clients=100)
    selector = TrapSelector(config, random.Random(19))
    selector.initial_coverage_done = True
    all_clients = list(range(100))
    penalties = {client_id: 0 for client_id in all_clients}
    flags = penalties.copy()

    first = selector.select(21, all_clients, penalties, flags, set(range(45)))
    former_anchors = set(first.anchors)
    active_after_removal = list(set(all_clients) - set(range(45)))
    later = [
        selector.select(round_idx, active_after_removal, penalties, flags, set())
        for round_idx in range(22, 31)
    ]
    later_surveillance = set().union(
        *(selection.surveillance_clients for selection in later)
    )

    assert former_anchors <= later_surveillance
    assert later[-1].surveillance_complete


def test_later_surveillance_cycles_probe_each_client_once_not_twice() -> None:
    config = ExperimentConfig(num_clients=100)
    selector = TrapSelector(config, random.Random(23))
    selector.initial_coverage_done = True
    active_clients = list(range(100))
    penalties = {client_id: 0 for client_id in active_clients}
    flags = penalties.copy()

    selections = [
        selector.select(round_idx, active_clients, penalties, flags, set())
        for round_idx in range(21, 31)
    ]
    counts = Counter(
        client_id
        for selection in selections
        for client_id in selection.surveillance_clients
    )

    assert set(counts) == set(active_clients)
    assert set(counts.values()) == {1}
    assert selector.initial_coverage_done


def test_candidates_are_confirmed_with_anchors_and_never_used_as_anchors() -> None:
    config = ExperimentConfig(num_clients=100)
    selector = TrapSelector(config, random.Random(29))
    selector.initial_coverage_done = True
    active_clients = list(range(100))
    penalties = {client_id: 0 for client_id in active_clients}
    flags = {client_id: 0 for client_id in active_clients}
    candidates = {4, 17}
    flags.update({client_id: 1 for client_id in candidates})

    selection = selector.select(
        21, active_clients, penalties, flags, set(), candidates
    )

    grouped_candidates = set().union(
        *(group_candidates for _, group_candidates, _ in selection.suspicion_groups)
    )
    assert selection.phase == "confirmation"
    assert grouped_candidates == candidates
    assert candidates <= selection.trapped_clients
    assert candidates.isdisjoint(selection.anchors)
    assert len(selection.suspicion_groups) == 1
    assert len(selection.anchors) == 3


def test_any_previously_flagged_client_is_ineligible_as_an_anchor() -> None:
    config = ExperimentConfig(num_clients=100)
    selector = TrapSelector(config, random.Random(31))
    selector.initial_coverage_done = True
    active_clients = list(range(100))
    suspected = set(range(10))
    penalties = {client_id: int(client_id in suspected) for client_id in active_clients}
    flags = penalties.copy()
    previously_flagged = 50
    flags[previously_flagged] = 1

    selection = selector.select(
        21, active_clients, penalties, flags, suspected, set()
    )

    assert previously_flagged not in selection.anchors
