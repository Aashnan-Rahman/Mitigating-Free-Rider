import copy
import json
from pathlib import Path

import numpy as np
import pytest

from server.v15_evidence import CycleState, certificate, screen, audit_anomalies, policy


def separated_rows():
    rng = np.random.default_rng(17)
    return [dict(client_id=c, trap_id=t, norm_z=-4 if c < 40 else .1,
        profile_z=8 if c < 40 else float(rng.normal()), exact_zero_delta=0, exact_sendback=0,
        delta_norm=float(rng.normal(.1 if c < 40 else 2., .005 if c < 40 else .2)),
        profile_distance=float(rng.normal(.8 if c < 40 else .1, .003 if c < 40 else .01)))
        for c in range(100) for t in (0, 1)]


def test_strong_separation_label_blind_and_not_round_gated():
    rows = separated_rows()
    a, m = screen(rows, 20)
    b, _ = screen([{**r, "is_free_rider": 0, "attack_type": "FR1"} for r in rows], 100)
    assert [{k: v for k, v in r.items() if k != "round"} for r in a] == [{k: v for k, v in r.items() if k != "round"} for r in b]
    assert all(r["state"] == "S" and r["strong_channels"] for r in a[:40])
    assert not m["no_strong_evidence"]
    assert policy()["calibration"] == "none"


def test_continuous_tail_and_singletons_do_not_certify():
    rows = [dict(client_id=c, delta_norm=float(c + 1)) for c in range(100)]
    result = certificate(rows, "delta_norm", "low", "identity", set(range(20)))
    assert not result["supported"]
    assert not certificate(rows, "delta_norm", "low", "identity", {0})["supported"]


def test_cohort_outlier_on_wrong_side_does_not_inherit_its_certificate():
    rows = [dict(client_id=c, delta_norm=.1 if c < 40 else 9. if c == 40 else 2. + (c % 3) * .01) for c in range(100)]
    result = certificate(rows, "delta_norm", "low", "identity", set(range(41)))
    assert result["supported"] and len(result["members"]) == 40
    assert 40 not in result["members"]


def test_weak_median_outliers_do_not_authorize_removal():
    rows = [dict(client_id=c, trap_id=t, norm_z=-1 if c < 4 else 1, profile_z=None,
        exact_zero_delta=0, exact_sendback=0, delta_norm=1., profile_distance=.1)
        for c in range(10) for t in (0, 1)]
    decisions, metadata = screen(rows, 20)
    assert all(d["state"] == "C" and not d["strong_channels"] for d in decisions[:4])
    assert metadata["no_strong_evidence"]
    s = CycleState(range(10))
    assert not s.apply(copy.deepcopy(decisions), 0, 20)
    assert not s.apply(copy.deepcopy(decisions), 1, 30)
    assert not s.monitored and not s.quarantined and len(s.active) == 10


def test_same_component_required_and_weak_breaks_streak():
    s = CycleState([0])
    def apply(channels, cycle):
        return s.apply([dict(client_id=0, state="S" if channels else "C", strong_channels=channels)], cycle, 20 + 10 * cycle)
    assert not apply("norm_low", 0)
    assert not apply("profile_high", 1)
    assert not apply("", 2)
    assert not apply("norm_low", 3)
    assert apply("norm_low", 4)[0]["event"] == "remove"


def test_candidate_cannot_smuggle_a_strong_strike():
    s = CycleState([0])
    assert not s.apply([dict(client_id=0, state="C", strong_channels="norm_low")], 0, 20)
    assert s.records[0]["strong"] == 0
    assert not s.apply([dict(client_id=0, state="S", strong_channels="norm_low")], 1, 30)


def test_review_expires_even_when_weak_evidence_repeats_and_cooldown_expires_on_audits():
    s = CycleState([0])
    s.apply([dict(client_id=0, state="S", strong_channels="norm_low")], 0, 20)
    for cycle in (1, 2):
        events = s.apply([dict(client_id=0, state="C", strong_channels="")], cycle, 20 + 10 * cycle)
    assert events[0]["event"] == "release_unconfirmed"
    assert not s.quarantined and not s.monitored
    s.escalate_audit({0})
    assert not s.monitored
    s.escalate_audit({0})
    assert not s.monitored
    s.escalate_audit({0})
    assert s.monitored == {0} and not s.quarantined
    assert s.records[0]["strong"] == 0
    restored = CycleState([0])
    restored.load_state_dict(s.state_dict())
    assert restored.state_dict() == s.state_dict()


def test_exact_sendback_requires_both_traps_and_two_cycles():
    rows = separated_rows()
    for r in rows:
        r.update(norm_z=None, profile_z=None, delta_norm=0., profile_distance=0., exact_zero_delta=1, exact_sendback=1)
    s = CycleState(range(100))
    first, _ = screen(rows, 20)
    assert all(d["strong_channels"] == "exact_sendback" for d in first)
    assert not s.apply(first, 0, 20)
    second, _ = screen(rows, 30)
    assert len(s.apply(second, 1, 30)) == 100


def test_new_plan_preserves_previous_plan_and_has_no_calibration():
    from config import ExperimentConfig
    from run_experiments import expand_plan
    p = json.loads(Path("configs/v15_1_mnist_seed73_fr40_plan.json").read_text())
    runs = expand_plan(p, False)
    assert len(runs) == 8 and [r["config"]["distribution"] for r in runs] == ["noniid"] * 4 + ["iid"] * 4
    for run in runs:
        c = ExperimentConfig.from_dict({**p["defaults"], **run["config"]})
        c.validate()
        assert c.seed == 73 and not c.paired_shadow_calibration and c.methodology_version == "swtcp_v15_1"
    assert json.loads(Path("configs/v15_mnist_seed73_fr40_plan.json").read_text())["batch_name"] == "v15_mnist_seed73_fr40"
