import copy
import csv
import json
from pathlib import Path

import pytest

from server import v15_strict_norm as strict
from server.v15_certificate_memory import CycleState, policy, screen


def apply(state, cycle, label, channels=""):
    return state.apply([dict(client_id=0, state=label, strong_channels=channels)], cycle, 20 + cycle * 10)


def removed(events):
    return [event for event in events if event["event"] == "remove"]


def test_candidate_pauses_confirmation_and_second_fresh_certificate_removes():
    state = CycleState([0])
    assert not removed(apply(state, 0, "S", "norm_low"))
    for cycle in (1, 2, 3):
        assert not removed(apply(state, cycle, "C"))
    assert not state.quarantined and not state.monitored
    assert state.records[0]["fresh_certificate_counts"] == {"norm_low": 1}
    events = removed(apply(state, 4, "S", "norm_low"))
    assert len(events) == 1 and events[0]["reason"] == "repeated_fresh_component_certificates"
    assert not state.active


def test_different_components_do_not_combine():
    state = CycleState([0])
    apply(state, 0, "S", "norm_low")
    assert not removed(apply(state, 1, "S", "profile_high"))
    assert state.records[0]["fresh_certificate_counts"] == {"norm_low": 1, "profile_high": 1}
    assert len(removed(apply(state, 2, "S", "norm_low"))) == 1


def test_two_clean_cycles_clear_memory_but_one_does_not():
    state = CycleState([0])
    apply(state, 0, "S", "norm_low")
    apply(state, 1, "R")
    assert state.records[0]["fresh_certificate_counts"] == {"norm_low": 1}
    events = apply(state, 2, "R")
    assert any(e["event"] == "clear_certificate_memory" for e in events)
    assert state.records[0]["fresh_certificate_counts"] == {}
    assert not removed(apply(state, 3, "S", "norm_low"))


def test_candidate_between_clean_cycles_interrupts_clearance():
    state = CycleState([0])
    apply(state, 0, "S", "norm_low")
    apply(state, 1, "R")
    apply(state, 2, "C")
    apply(state, 3, "R")
    assert state.records[0]["certificate_clean_cycles"] == 1
    assert state.records[0]["fresh_certificate_counts"] == {"norm_low": 1}


def test_missing_cycle_cannot_certify_consecutive_clearance():
    state = CycleState([0])
    apply(state, 0, "S", "norm_low")
    apply(state, 1, "R")
    apply(state, 3, "R")
    assert state.records[0]["certificate_clean_cycles"] == 1
    assert state.records[0]["fresh_certificate_counts"] == {"norm_low": 1}


def test_duplicate_cycle_cannot_count_as_a_second_certificate():
    state = CycleState([0])
    apply(state, 0, "S", "norm_low")
    before = state.state_dict()
    with pytest.raises(ValueError, match="distinct, newer"):
        apply(state, 0, "S", "norm_low")
    assert state.state_dict() == before


def test_single_audit_cannot_confirm_clear_or_renew_quarantine_from_memory():
    state = CycleState([0])
    apply(state, 0, "S", "norm_low")
    apply(state, 1, "C")
    apply(state, 2, "C")
    assert not state.quarantined and not state.monitored
    for _ in range(3):
        state.escalate_audit({0})
    assert state.records[0]["fresh_certificate_counts"] == {"norm_low": 1}
    assert state.active == [0] and not state.quarantined


def test_candidate_cannot_smuggle_a_certificate_or_trigger_removal():
    state = CycleState([0])
    apply(state, 0, "C", "norm_low")
    assert state.records[0]["fresh_certificate_counts"] == {}
    apply(state, 1, "S", "norm_low")
    assert not removed(apply(state, 2, "C", "norm_low"))
    assert state.records[0]["fresh_certificate_counts"] == {"norm_low": 1}


def test_exact_sendback_still_requires_consecutive_cycles():
    state = CycleState([0])
    apply(state, 0, "S", "exact_sendback")
    apply(state, 1, "C")
    assert not removed(apply(state, 2, "S", "exact_sendback"))
    assert len(removed(apply(state, 3, "S", "exact_sendback"))) == 1
    assert state.records[0]["fresh_certificate_counts"] == {}


def test_checkpointed_memory_and_clearance_counters_are_preserved():
    state = CycleState([0])
    apply(state, 0, "S", "norm_low")
    apply(state, 1, "R")
    restored = CycleState([0])
    restored.load_state_dict(state.state_dict())
    assert restored.state_dict() == state.state_dict()
    assert apply(restored, 2, "S", "norm_low") == apply(state, 2, "S", "norm_low")
    assert restored.state_dict() == state.state_dict()


@pytest.mark.parametrize("channel", ["diagonal_high", "history_match", "attack_type"])
def test_noncertificate_components_are_rejected(channel):
    state = CycleState([0])
    with pytest.raises(ValueError, match="diagnostic-only"):
        apply(state, 0, "S", channel)


def test_incomplete_cycle_does_not_mutate_memory():
    state = CycleState([0, 1])
    before = state.state_dict()
    with pytest.raises(ValueError, match="complete active-client"):
        apply(state, 0, "S", "norm_low")
    assert state.state_dict() == before


def test_screening_is_identical_to_v15_3_and_label_blind():
    rows = [dict(client_id=c, trap_id=t, norm_z=-4 if c < 40 else .1,
                 profile_z=None, exact_zero_delta=0, exact_sendback=0,
                 delta_norm=.1 if c < 40 else 2., profile_distance=.1)
            for c in range(100) for t in (0, 1)]
    old, _ = strict.screen(rows, 20)
    new, metadata = screen([{**r, "is_free_rider": 1, "attack_type": "FR3"} for r in rows], 20)
    assert old == new
    assert metadata["revision"] == policy()["revision"]
    assert policy()["round_dependent_thresholds"] is False


def test_plan_is_same_cifar_batch_except_version():
    from config import ExperimentConfig
    from run_experiments import expand_plan
    plan = json.loads(Path("configs/v15_4_cifar10_seed42_fr40_plan.json").read_text())
    old = json.loads(Path("configs/v15_3_cifar10_seed42_fr40_plan.json").read_text())
    assert plan["defaults"] == {**old["defaults"], "methodology_version": "swtcp_v15_4"}
    runs = expand_plan(plan, False)
    assert len(runs) == len({r["id"] for r in runs}) == 8
    assert [r["config"]["distribution"] for r in runs] == ["noniid"] * 4 + ["iid"] * 4
    for run in runs:
        config = ExperimentConfig.from_dict({**plan["defaults"], **run["config"]})
        config.validate()
        assert config.dataset == "cifar10" and config.seed == 42 and config.num_rounds == 100


def test_recorded_fr3_qualifies_at_round60_with_no_honest_removals():
    path = Path("results/v15_3_cifar10_seed42_fr40/v15_3_cifar10_noniid_FR3_seed42/cycle_decisions.csv")
    if not path.exists():
        pytest.skip("Recorded trajectory not available")
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    state = CycleState(range(100))
    removals = []
    for round_index in sorted({int(r["round"]) for r in rows}):
        current = [r for r in rows if int(r["round"]) == round_index and int(r["client_id"]) in state.active]
        # Labels are used only after decisions; never given to the state machine.
        truth = {int(r["client_id"]): int(r["is_free_rider"]) for r in current}
        public = [dict(client_id=int(r["client_id"]), state=r["state"],
                       strong_channels=r["strong_channels"]) for r in current]
        events = state.apply(public, int(current[0]["cycle"]), round_index)
        removals.extend((round_index, truth[e["client_id"]]) for e in removed(events))
    assert len(removals) == 40
    assert all(round_index == 60 and label == 1 for round_index, label in removals)
