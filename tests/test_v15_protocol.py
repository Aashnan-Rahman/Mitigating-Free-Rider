import copy
import json
import random
from collections import Counter
from pathlib import Path

import pytest
import torch

from server.v15_protocol import CycleState, build_schedule, measurements, screen, audit_anomalies
from server.preliminary_signals import PreliminarySignals


@pytest.mark.parametrize("watched", [0, 1, 42, 45, 46, 99, 100])
def test_homogeneous_groups_balanced_coverage_and_all_monitored_rounds(watched):
    active = list(range(100))
    monitored = set(active[:watched])
    schedule = build_schedule(active, monitored, random.Random(73))
    assert len(schedule["groups"]) == 10 and len(schedule["assignments"]) == 10
    assert sorted(c for _, clients in schedule["groups"] for c in clients) == active
    for role, clients in schedule["groups"]:
        assert clients and all((c in monitored) == (role == "monitored") for c in clients)
    if watched in (42, 45, 46):
        assert sum(role == "monitored" for role, _ in schedule["groups"]) == (4 if watched < 46 else 5)
    for c in active:
        counts = Counter(t for t, clients in schedule["assignments"] if c in clients)
        assert counts == ({0: 5, 1: 5} if c in monitored else {0: 1, 1: 1})
        for t, position in schedule["selected"][c].items():
            assert schedule["assignments"][position][0] == t
            assert c in schedule["assignments"][position][1]
    for t, clients in schedule["assignments"]:
        assert len(clients) == len(set(clients))


@pytest.mark.parametrize("n", [0, 1, 2, 5, 9, 12, 100])
def test_shrinking_initial_schedule_always_ten_rounds(n):
    schedule = build_schedule(list(range(n)), set(), random.Random(3), initial=True)
    assert len(schedule["groups"]) == min(10, n)
    assert len(schedule["assignments"]) == 10
    for c in range(n):
        assert Counter(t for t, clients in schedule["assignments"] if c in clients) == {0: 1, 1: 1}


def test_scalar_measurements_match_existing_exact_norm_profile():
    old = PreliminarySignals()
    selected = {}
    for c in range(12):
        for t in (0, 1):
            delta = torch.tensor([float(c + 1), float(t + c % 3)])
            profile = delta.abs() / delta.abs().sum()
            old.observe(c, t, delta, profile, 11 + t)
            selected.setdefault(c, {})[t] = dict(norm=float(delta.norm()), profile=profile.tolist(), round=11+t, sendback=False)
    compact = measurements(selected, list(range(12)), 20)
    baseline = old.complete()
    for a, b in zip(compact, baseline):
        for field in ("client_id", "trap_id", "norm_z", "profile_z", "profile_distance", "norm_median", "norm_mad"):
            assert a[field] == b[field]


def test_median_fallback_label_blind_and_incomplete_defers():
    rows = [dict(client_id=c, trap_id=t, norm_z=-1 if c < 4 else 1,
                 profile_z=None, exact_zero_delta=0, exact_sendback=0) for c in range(10) for t in (0, 1)]
    a, meta = screen(rows, 30)
    b, _ = screen([{**r, "is_free_rider": 1, "attack_type": "FR4"} for r in rows], 30)
    assert a == b and meta["fallback_used"]
    assert [r["state"] for r in a] == ["S"] * 4 + ["R"] * 6
    rows[0]["norm_z"] = None
    assert screen(rows, 30)[0][0]["state"] == "C"


def test_confirmation_reset_and_rehabilitation_probation():
    s = CycleState([0])
    def apply(letter, cycle):
        decision = dict(client_id=0, state=letter)
        events = s.apply([decision], cycle, 20 + cycle * 10)
        return events
    assert not apply("S", 0)
    assert not apply("C", 1)
    assert not apply("S", 2)
    assert not apply("R", 3)
    assert s.monitored == {0}
    assert apply("R", 4)[0]["event"] == "rehabilitate"
    assert s.active == [0] and not s.monitored and s.pending_probation
    apply("R", 5)
    assert not s.pending_probation
    apply("S", 6)
    assert apply("S", 7)[0]["event"] == "remove"
    assert not s.active


def test_audit_never_removes_or_counts_as_confirmation():
    s = CycleState([0, 1])
    s.escalate_audit({0})
    assert s.records[0]["category"] == "C" and s.records[0]["strong"] == 0
    decisions = [dict(client_id=0, state="S"), dict(client_id=1, state="R")]
    assert not s.apply(decisions, 0, 30)
    assert s.active == [0, 1]
    with pytest.raises(ValueError, match="complete"):
        s.apply([dict(client_id=0, state="S")], 1, 40)
    restored = CycleState([0, 1])
    restored.load_state_dict(copy.deepcopy(s.state_dict()))
    assert restored.state_dict() == s.state_dict()


def test_missing_audit_escalates_without_removal():
    rows = measurements({}, [0, 1], 40, traps=(0,))
    assert audit_anomalies(rows)[0] == {0, 1}


def test_seed73_plan_has_non_iid_first_and_eight_runs():
    from config import ExperimentConfig
    from run_experiments import expand_plan
    plan = json.loads(Path("configs/v15_mnist_seed73_fr40_plan.json").read_text())
    runs = expand_plan(plan, False)
    assert len(runs) == 8
    assert [r["config"]["distribution"] for r in runs] == ["noniid"] * 4 + ["iid"] * 4
    for r in runs:
        c = ExperimentConfig.from_dict({**plan["defaults"], **r["config"]})
        c.validate()
        assert c.seed == 73 and c.num_rounds == 100 and c.methodology_version == "swtcp_v15"
