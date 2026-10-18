import copy
import csv
import json
from pathlib import Path

import pytest

from server import v15_evidence as baseline
from server.v15_strict_norm import (
    CycleState, audit_anomalies, policy, screen, strict_norm_certificate,
)


def norm_rows(overlap=False):
    return [dict(client_id=c, trap_id=t, norm_z=-4 if c < 40 else .1,
                 profile_z=None, exact_zero_delta=0, exact_sendback=0,
                 delta_norm=.1 + c * .0001 if c < 40 else
                            .095 if overlap and c == 40 else 2. + c * .001,
                 profile_distance=.1)
            for c in range(100) for t in (0, 1)]


def test_overlapping_dense_norm_cohort_is_candidate_without_removal_or_quarantine():
    rows = norm_rows(overlap=True)
    old, _ = baseline.screen(rows, 20)
    assert all(d["strong_channels"] == "norm_low" for d in old[:40])
    new, metadata = screen(rows, 20)
    assert all(d["state"] == "C" and not d["strong_channels"] for d in new[:40])
    assert all(c["reason"] == "overlap_or_insufficient_full_peer_gap"
               for c in metadata["certificates"]["norm_low"])
    state = CycleState(range(100))
    for cycle in range(8):
        assert not state.apply(copy.deepcopy(new), cycle, 20 + 10 * cycle)
    assert len(state.active) == 100 and not state.quarantined and not state.monitored


def test_strict_norm_gap_preserves_two_trap_two_cycle_confirmation():
    rows = norm_rows()
    state = CycleState(range(100))
    first, metadata = screen(rows, 20)
    assert all(c["full_peer_gap"] > c["spread"] for c in metadata["certificates"]["norm_low"])
    assert not state.apply(first, 0, 20)
    second, _ = screen(rows, 30)
    removed = state.apply(second, 1, 30)
    assert {d["client_id"] for d in removed} == set(range(40))


def test_one_overlapping_trap_prevents_norm_confirmation():
    rows = norm_rows()
    rows[2 * 40 + 1]["delta_norm"] = .095
    decisions, metadata = screen(rows, 20)
    assert metadata["certificates"]["norm_low"][0]["supported"]
    assert not metadata["certificates"]["norm_low"][1]["supported"]
    assert all(not d["strong_channels"] for d in decisions)


def test_diagonal_cannot_bypass_rejected_norm_evidence():
    rows = norm_rows(overlap=True)
    for row in rows:
        row["profile_z"] = 8 if row["client_id"] < 40 else 0
    old, _ = baseline.screen(rows, 20)
    assert all("diagonal_high" in d["strong_channels"] for d in old[:40])
    new, _ = screen(rows, 20)
    assert all(not d["strong_channels"] for d in new[:40])
    assert all("diagonal_high" in d["diagnostic_certified_channels"] for d in new[:40])


def test_profile_certificate_remains_available_without_norm():
    rows = norm_rows()
    for row in rows:
        row["delta_norm"] = 1.
        row["profile_z"] = 8 if row["client_id"] < 40 else 0
        row["profile_distance"] = .8 + row["client_id"] * .0001 if row["client_id"] < 40 else .1
    decisions, _ = screen(rows, 20)
    assert all(d["strong_channels"] == "profile_high" for d in decisions[:40])


def test_exact_sendback_does_not_require_statistical_separation():
    rows = norm_rows()
    for row in rows:
        row.update(norm_z=None, profile_z=None, delta_norm=0., exact_zero_delta=1, exact_sendback=1)
    state = CycleState(range(100))
    first, _ = screen(rows, 20)
    assert all(d["strong_channels"] == "exact_sendback" for d in first)
    assert not state.apply(first, 0, 20)
    second, _ = screen(rows, 30)
    assert len(state.apply(second, 1, 30)) == 100


def test_rule_is_label_blind_and_identical_at_early_and_late_rounds():
    rows = norm_rows(overlap=True)
    early, _ = screen(rows, 20)
    late, _ = screen([{**r, "attack_type": "FR4", "is_free_rider": 1,
                       "free_rider_pct": .4} for r in rows], 90)
    assert [{k: v for k, v in d.items() if k != "round"} for d in early] == [
        {k: v for k, v in d.items() if k != "round"} for d in late]
    assert policy()["calibration"] == "none"


def test_gap_is_scale_and_translation_equivariant():
    for overlap in (False, True):
        rows = [r for r in norm_rows(overlap) if r["trap_id"] == 0]
        a = strict_norm_certificate(rows, set(range(40)))
        b = strict_norm_certificate([{**r, "delta_norm": r["delta_norm"] * 73 + 2} for r in rows], set(range(40)))
        assert a["supported"] == b["supported"] and a["members"] == b["members"]


def test_diagonal_strike_cannot_be_smuggled_into_state():
    with pytest.raises(ValueError, match="diagnostic only"):
        CycleState([0]).apply([dict(client_id=0, state="S", strong_channels="diagonal_high")], 0, 20)


def test_audit_uses_strict_norm_and_cannot_remove():
    rows = [r for r in norm_rows(True) if r["trap_id"] == 0]
    for row in rows:
        row["profile_z"] = 0.
    clients, _ = audit_anomalies(rows)
    assert not clients
    clear_rows = [{**r, "profile_z": 0.} for r in norm_rows() if r["trap_id"] == 0]
    clients, _ = audit_anomalies(clear_rows)
    assert clients == set(range(40))
    state = CycleState(range(100))
    state.escalate_audit(clients)
    assert len(state.active) == 100 and not state.quarantined
    assert all(state.records[c]["strong"] == 0 for c in clients)


def test_new_plan_matches_seed42_baseline_and_has_eight_runs():
    from config import ExperimentConfig
    from run_experiments import expand_plan
    path = Path("configs/v15_3_mnist_seed42_fr40_plan.json")
    plan = json.loads(path.read_text())
    old = json.loads(Path("configs/v15_1_mnist_seed42_fr40_plan.json").read_text())
    assert plan["defaults"] == {**old["defaults"], "methodology_version": "swtcp_v15_3"}
    runs = expand_plan(plan, False)
    assert len(runs) == len({r["id"] for r in runs}) == 8
    assert [r["config"]["distribution"] for r in runs] == ["noniid"] * 4 + ["iid"] * 4
    for run in runs:
        config = ExperimentConfig.from_dict({**plan["defaults"], **run["config"]})
        config.validate()
        assert config.seed == 42 and config.num_rounds == 100


@pytest.mark.parametrize("attack,removal_round", [("FR1", 70), ("FR2", 80), ("FR4", 70)])
def test_recorded_seed42_late_norm_removal_evidence_is_blocked(attack, removal_round):
    path = Path(f"results/v15_1_mnist_seed42_fr40/v15_1_mnist_noniid_{attack}_seed42/cycle_signals.csv")
    if not path.exists():
        pytest.skip("Recorded baseline run not available")
    with path.open(newline="") as handle:
        rows = [r for r in csv.DictReader(handle) if int(r["round"]) == removal_round]
    if not rows:
        pytest.skip("Baseline has not reached the removal cycle")
    for row in rows:
        row["client_id"], row["trap_id"] = int(row["client_id"]), int(row["trap_id"])
        for key in ("norm_z", "profile_z", "delta_norm", "profile_distance"):
            row[key] = float(row[key]) if row[key] else None
        for key in ("exact_zero_delta", "exact_sendback"):
            row[key] = int(row[key])
    old, _ = baseline.screen(rows, removal_round)
    assert any(d["strong_channels"] == "norm_low" for d in old)
    new, _ = screen(rows, removal_round)
    assert all("norm_low" not in d["strong_channels"] for d in new)


def test_recorded_seed42_fr4_initial_certificate_still_confirms():
    path = Path("results/v15_1_mnist_seed42_fr40/v15_1_mnist_noniid_FR4_seed42/cycle_signals.csv")
    if not path.exists():
        pytest.skip("Recorded baseline run not available")
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    state = CycleState(range(100))
    for cycle, round_index in enumerate((20, 30)):
        signals = [dict(r) for r in rows if int(r["round"]) == round_index]
        for row in signals:
            row["client_id"], row["trap_id"] = int(row["client_id"]), int(row["trap_id"])
            for key in ("norm_z", "profile_z", "delta_norm", "profile_distance"):
                row[key] = float(row[key]) if row[key] else None
            for key in ("exact_zero_delta", "exact_sendback"):
                row[key] = int(row[key])
        decisions, _ = screen(signals, round_index)
        events = state.apply(decisions, cycle, round_index)
        if cycle == 0:
            assert not events
        else:
            truth = {int(r["client_id"]) for r in signals if r["is_free_rider"] == "1"}
            assert {e["client_id"] for e in events if e["event"] == "remove"} == truth
