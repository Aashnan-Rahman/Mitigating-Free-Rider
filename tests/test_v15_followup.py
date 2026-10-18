import copy
import csv
import json
from pathlib import Path

import numpy as np
import pytest

from server.v15_followup import CycleState, screen, leave_one_out_medians


@pytest.mark.parametrize("values", [[1.], [1., 2.], [1., 2., 3.], [1., 2., 3., 4.],
                                   [1., 1., 2.], [0., 1., 1.], [1., 1., 1., 2., 2.],
                                   [2., 1., 4., 3., 5., 7., 0.]])
def test_leave_one_out_medians_without_score_sorting(values):
    result = leave_one_out_medians(dict(enumerate(values)))
    for i in range(len(values)):
        peers = values[:i] + values[i + 1:]
        assert result[i] == (float(np.median(peers)) if peers else None)


def weak_rows(first=-1., second=-1.):
    return [dict(client_id=c, trap_id=t, norm_z=(first if t == 0 else second) if c == 0 else 1.,
                 profile_z=None, delta_norm=1., profile_distance=.1, exact_zero_delta=0, exact_sendback=0)
            for c in range(10) for t in (0, 1)]


def certified_decisions():
    return [dict(client_id=c, state="S" if c == 0 else "R", strong_channels="norm_low" if c == 0 else "",
                 cohort_certified_channels="norm_low" if c == 0 else "", followup_clean_channels="") for c in range(10)]


def test_prior_certificate_confirms_borderline_candidate_on_both_traps():
    state = CycleState(range(10))
    assert not state.apply(certified_decisions(), 0, 20)
    rows = weak_rows()
    decisions, _ = screen(rows, 30, state.confirmation_context())
    assert decisions[0]["state"] == "S"
    assert screen(rows, 30)[0][0]["state"] == "C"
    assert decisions[0]["cohort_certified_channels"] == ""
    assert decisions[0]["followup_matched_channels"] == "norm_low"
    events = state.apply(decisions, 1, 30)
    assert events == [dict(client_id=0, event="remove", reason="prior_certificate_plus_consecutive_paired_followup")]
    assert 0 not in state.confirmation_context()


def test_weak_screening_cannot_self_enrol_or_remove():
    state = CycleState(range(10))
    for cycle in range(4):
        decisions, _ = screen(weak_rows(), 20 + 10 * cycle, state.confirmation_context())
        assert not state.apply(decisions, cycle, 20 + 10 * cycle)
        assert state.confirmation_context() == {} and not state.monitored
    assert len(state.active) == 10


def test_candidate_cannot_enrol_by_claiming_a_certificate():
    state = CycleState(range(10))
    decisions = certified_decisions()
    decisions[0].update(state="C", strong_channels="norm_low", cohort_certified_channels="norm_low")
    state.apply(decisions, 0, 20)
    assert state.confirmation_context() == {}


def test_mixed_evidence_resets_confirmation_but_watch_outlasts_quarantine():
    state = CycleState(range(10))
    state.apply(certified_decisions(), 0, 20)
    for cycle in (1, 2):
        decisions, _ = screen(weak_rows(-1., 1.), 20 + 10 * cycle, state.confirmation_context())
        state.apply(decisions, cycle, 20 + 10 * cycle)
    assert state.records[0]["strong"] == 0
    assert 0 in state.monitored and 0 not in state.quarantined
    assert state.confirmation_context()[0] == ("norm_low",)
    restored = CycleState(range(10))
    restored.load_state_dict(copy.deepcopy(state.state_dict()))
    assert restored.confirmation_context() == state.confirmation_context()
    assert restored.monitored == state.monitored and not restored.quarantined


def test_two_complete_clean_cycles_clear_watch_and_rehabilitate():
    state = CycleState(range(10))
    state.apply(certified_decisions(), 0, 20)
    for cycle in (1, 2):
        decisions, _ = screen(weak_rows(1., 1.), 20 + 10 * cycle, state.confirmation_context())
        events = state.apply(decisions, cycle, 20 + 10 * cycle)
        if cycle == 1:
            assert 0 in state.monitored
    assert 0 not in state.monitored and state.confirmation_context() == {}
    assert any(e["event"] == "rehabilitate" for e in events)
    assert state.pending_probation


def test_missing_probe_or_nonfinite_measurement_cannot_confirm():
    state = CycleState(range(10))
    state.apply(certified_decisions(), 0, 20)
    for rows in ([r for r in weak_rows() if not (r["client_id"] == 0 and r["trap_id"] == 1)],
                 [{**r, "norm_z": None} if r["client_id"] == 0 and r["trap_id"] == 1 else r for r in weak_rows()]):
        decisions, _ = screen(rows, 30, state.confirmation_context())
        assert decisions[0]["state"] == "C"


def test_followup_is_label_blind_and_not_round_gated():
    context = {0: ("norm_low",)}
    a, _ = screen(weak_rows(), 30, context)
    b, _ = screen([{**r, "is_free_rider": 0, "attack_type": "FR1"} for r in weak_rows()], 80, context)
    assert [{k: v for k, v in d.items() if k != "round"} for d in a] == [{k: v for k, v in d.items() if k != "round"} for d in b]


def test_diagonal_followup_uses_leave_one_out_peer_median():
    rows = [{**r, "norm_z": 0., "profile_z": 4. if r["client_id"] == 0 else 0.} for r in weak_rows()]
    decisions, metadata = screen(rows, 30, {0: ("diagonal_high",)})
    assert decisions[0]["followup_matched_channels"] == "diagonal_high"
    assert metadata["followup_checks"][0]["diagonal_high"]["A_reference"] == 0.


def test_profile_followup_can_confirm_without_combined_score_admission():
    rows = [{**r, "norm_z": 1., "profile_z": 3. if r["client_id"] == 0 else 0.} for r in weak_rows()]
    decisions, _ = screen(rows, 30, {0: ("profile_high",)})
    assert decisions[0]["state"] == "S"
    assert decisions[0]["followup_matched_channels"] == "profile_high"
    assert decisions[0]["cohort_certified_channels"] == ""


def test_saved_client95_confirmed_at30_without_extra_honest_removals():
    folder = Path("results/v15_1_mnist_seed73_fr40/v15_1_mnist_noniid_FR4_seed73")
    with (folder / "cycle_signals.csv").open(newline="", encoding="utf-8") as handle:
        saved = list(csv.DictReader(handle))
    state = CycleState(range(100))
    truth = {int(r["client_id"]): int(r["is_free_rider"]) for r in saved}
    events = []
    for cycle, rd in enumerate((20, 30)):
        public = []
        for r in saved:
            if int(r["round"]) != rd:
                continue
            row = {k: None if r[k] == "" else float(r[k]) for k in ("norm_z", "profile_z", "delta_norm", "profile_distance")}
            row.update(client_id=int(r["client_id"]), trap_id=int(r["trap_id"]),
                exact_zero_delta=int(r["exact_zero_delta"]), exact_sendback=int(r["exact_sendback"]))
            public.append(row)
        decisions, _ = screen(public, rd, state.confirmation_context())
        events = state.apply(decisions, cycle, rd)
    removed = [e["client_id"] for e in events if e["event"] == "remove"]
    assert 95 in removed and sum(truth[c] for c in removed) == 40
    assert sum(not truth[c] for c in removed) == 1


def test_new_plan_matches_prior_settings_and_orders_eight_runs():
    from config import ExperimentConfig
    from run_experiments import expand_plan
    new = json.loads(Path("configs/v15_2_mnist_seed73_fr40_plan.json").read_text())
    old = json.loads(Path("configs/v15_1_mnist_seed73_fr40_plan.json").read_text())
    assert {k: v for k, v in new["defaults"].items() if k != "methodology_version"} == {k: v for k, v in old["defaults"].items() if k != "methodology_version"}
    runs = expand_plan(new, False)
    assert len(runs) == 8 and [r["config"]["distribution"] for r in runs] == ["noniid"] * 4 + ["iid"] * 4
    for run in runs:
        ExperimentConfig.from_dict({**new["defaults"], **run["config"]}).validate()
