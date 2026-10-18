import copy
import inspect
import json
from dataclasses import fields

import torch

from config import ExperimentConfig
from run_experiments import expand_plan
from server.v13_detection import V13Detector, V13Settings, settings_from_config, upper_quantile


def detector(**overrides):
    return V13Detector(settings_from_config(ExperimentConfig(
        methodology_version="swtcp_v13", **overrides)))


def responses(count=101):
    return dict(
        coverage_norms={i: [1 + (i % 5) * .04] * 2 for i in range(count)},
        coverage_profiles={i: [torch.tensor([.5 + (i % 5) * .01, .5 - (i % 5) * .01])] * 2
                           for i in range(count)},
        coverage_trap_ids={i: [0, 1] for i in range(count)},
        coverage_observation_rounds={i: [11, 12] for i in range(count)},
        active_clients=set(range(count)), checks=2,
    )


def test_generic_interface_cannot_receive_attack_or_telemetry():
    forbidden = {"attack_type", "free_riders", "is_free_rider", "fr3_window",
                 "fr4_history_size", "config", "local_loss", "local_steps"}
    assert forbidden.isdisjoint(inspect.signature(V13Detector.evaluate_cycle).parameters)
    assert forbidden.isdisjoint(field.name for field in fields(V13Settings))
    a = detector()
    b = detector(attack_type="FR3", fr3_window=19, fr4_history_size=37)
    assert a.evaluate_cycle(**responses()) == b.evaluate_cycle(**responses())


def test_three_reference_clients_cannot_make_statistical_decisions():
    d = detector()
    result = d.evaluate_cycle(**responses(4))
    assert not result["reference_valid"]
    assert not any(result["coherent_strong"].values())


def test_persistent_norm_only_outlier_can_be_confirmed_without_profile_failure():
    d = detector()
    d.evaluate_cycle(**responses())
    batch = responses()
    batch["coverage_norms"][24] = [100, 100]
    result = d.evaluate_cycle(**batch)
    assert result["flags"][24] == 2
    assert result["coherent_strong"][24]
    assert not result["results"][24].profile_flag
    first = d.transition(client=24, role="R", failed_probes=2,
                         coherent_strong=True, clean_cycles=0)
    assert not first.remove
    d.evaluate_cycle(**batch)
    second = d.transition(client=24, role="C", failed_probes=2,
                          coherent_strong=True, clean_cycles=0)
    assert second.remove


def test_joint_pair_requires_same_norm_direction_and_fresh_cycles():
    d = detector()
    d.evaluate_cycle(**responses())
    batch = responses()
    batch["coverage_profiles"][24] = [torch.tensor([1., 0.])] * 2
    batch["coverage_norms"][24] = [100, .001]
    mixed = d.evaluate_cycle(**batch)
    assert "norm_high" not in d.last_reasons[24]
    # Profile evidence can independently persist, even if norm directions differ.
    assert mixed["coherent_strong"][24] == mixed["results"][24].profile_flag
    batch["coverage_norms"][24] = [100, 100]
    first = d.evaluate_cycle(**batch)
    assert first["coherent_strong"][24]
    state = d.transition(client=24, role="R", failed_probes=2,
                         coherent_strong=True, clean_cycles=0)
    assert state.role == "C" and not state.remove
    d.evaluate_cycle(**batch)
    state = d.transition(client=24, role="C", failed_probes=2,
                         coherent_strong=True, clean_cycles=0)
    assert state.remove


def test_weak_evidence_expires_and_quarantine_has_a_release_deadline():
    d = detector()
    d.cycle, d.last_reasons = 1, {24: "norm_high"}
    first = d.transition(client=24, role="R", failed_probes=2,
                         coherent_strong=True, clean_cycles=0)
    d.cycle = 2
    weak = d.transition(client=24, role=first.role, failed_probes=1,
                        coherent_strong=False, clean_cycles=0)
    assert weak.role == "R" and weak.rehabilitated
    assert weak.score == 0 and not weak.remove
    assert d.pending[24] and d.evidence[24]
    assert d.has_pending_evidence({24})
    d.cycle = 3
    cooldown = d.transition(client=24, role="R", failed_probes=1,
                            coherent_strong=False, clean_cycles=0)
    assert cooldown.role == "R" and not cooldown.remove
    d.cycle = 4
    fresh = d.transition(client=24, role="R", failed_probes=2,
                         coherent_strong=True, clean_cycles=0)
    assert not fresh.remove


def test_previous_qualified_personal_baseline_can_veto_a_stable_outlier():
    d = detector()
    d.personal[24] = [(4., 4.)] * 3
    assert d.consistent_with_self(24, [(4.1, 4.1)] * 2, 3)
    assert not d.consistent_with_self(24, [(12., 12.)] * 2, 3)
    assert not d.consistent_with_self(23, [(4., 4.)] * 2, 3)


def test_clean_gap_and_changed_direction_cannot_confirm_removal():
    d = detector()
    role, clean = "R", 0
    for cycle, signature, strong in ((1, "norm_low", True), (2, "", False),
                                     (3, "norm_low", True), (4, "norm_high", True)):
        d.cycle, d.last_reasons = cycle, {24: signature}
        state = d.transition(client=24, role=role, failed_probes=2 if strong else 0,
                             coherent_strong=strong, clean_cycles=clean)
        assert not state.remove
        role, clean = state.role, state.clean_cycles
    d.cycle = 4 + d.settings.evidence_window
    assert not d.has_pending_evidence({24})
    assert not d.has_pending_evidence({25})


def test_leave_one_out_calibration_and_no_current_cycle_feedback():
    d = detector()
    d.calibration = [{item: float(item) for item in range(100)}]
    d.calibration_checks = [2]
    assert d.cutoff(99, 2) == 98
    assert d.cutoff(1, 2) == 99
    assert d.cutoff(1, 1) == float("inf")
    first = detector()
    first.evaluate_cycle(**responses())
    batch = responses()
    batch["coverage_norms"][24] = [100, 100]
    before = first.cutoff(24, 2)
    first.evaluate_cycle(**batch)
    assert first.last_cutoffs[24] == before


def test_small_calibration_defers_without_gaussian_bootstrap():
    assert upper_quantile(list(range(98)), .01) == float("inf")
    assert upper_quantile(list(range(99)), .01) == 98
    d = detector()
    first = d.evaluate_cycle(**responses())
    assert not first["reference_valid"]
    assert not d.personal
    assert all(value == float("inf") for value in d.last_cutoffs.values())
    assert d.evaluate_cycle(**responses())["reference_valid"]


def test_risk_budget_changes_rank_by_formula_not_a_z_constant():
    values = list(range(100))
    assert upper_quantile(values, .1) == 90
    assert upper_quantile(values, .05) == 95
    assert upper_quantile(values, .01) == 99
    assert upper_quantile(values, .001) == float("inf")


def test_order_statistic_has_exact_rank_budget_for_exchangeable_scores():
    # Enumeration, not a fitted detection-rate test: each position in a common
    # ordered null sample is equally likely under the rank-test assumptions.
    values = list(range(101))
    rejections = sum(value > upper_quantile(values[:index] + values[index + 1:], .01)
                     for index, value in enumerate(values))
    assert rejections / len(values) <= .01


def test_flagged_norm_only_cycles_never_qualify_personal_history():
    d = detector()
    d.evaluate_cycle(**responses())
    batch = responses()
    batch["coverage_norms"][24] = [100, 100]
    for _ in range(5):
        result = d.evaluate_cycle(**batch)
        assert result["flags"][24] == 2
        assert result["coherent_strong"][24]
    assert 24 not in d.personal


def test_personal_consistency_cannot_erase_unresolved_population_flags():
    d = detector()
    d.evaluate_cycle(**responses())
    batch = responses()
    batch["coverage_norms"][24] = [100, 100]
    d.consistent_with_self = lambda *args: True
    result = d.evaluate_cycle(**batch)
    assert result["flags"][24] == 2
    assert result["results"][24].flagged
    assert not result["coherent_strong"][24]
    assert 24 not in d.personal


def test_calibration_tail_is_not_truncated_to_passing_clients():
    d = detector()
    d.evaluate_cycle(**responses())
    batch = responses()
    batch["coverage_norms"][24] = [100, 100]
    result = d.evaluate_cycle(**batch)
    assert result["flags"][24] == 2
    assert 24 in d.calibration[-1]


def test_old_checkpoint_revision_is_rejected():
    import pytest
    state = detector().state_dict()
    state.pop("revision")
    with pytest.raises(ValueError, match="start a fresh run"):
        detector().load_state_dict(state)


def test_checkpoint_preserves_next_decision_and_expiry():
    d = detector()
    d.evaluate_cycle(**responses())
    restored = detector()
    restored.load_state_dict(copy.deepcopy(d.state_dict()))
    assert d.evaluate_cycle(**responses()) == restored.evaluate_cycle(**responses())
    assert d.state_dict() == restored.state_dict()


def test_three_required_cycles_and_expiring_window_work():
    d = detector(cycle_strong_cycles_for_removal=3,
                 v13_quarantine_max_cycles=3, v13_evidence_window_cycles=3)
    for cycle in (1, 2, 3):
        d.cycle, d.last_reasons = cycle, {24: "norm_high"}
        state = d.transition(client=24, role="R" if cycle == 1 else "C",
                             failed_probes=2, coherent_strong=True, clean_cycles=0)
        assert state.remove == (cycle == 3)


def test_full_plan_prioritizes_all_previously_failed_fr4_seeds():
    from pathlib import Path
    plan = json.loads(Path("configs/v13_mnist_priority_fr40_plan.json").read_text())
    runs = expand_plan(plan, False)
    assert len(runs) == 10
    assert [(run["config"]["distribution"], run["config"]["attack_type"],
             run["config"]["seed"]) for run in runs[:3]] == [
                 ("noniid", "FR4", 42), ("noniid", "FR4", 43), ("noniid", "FR4", 46)]
    assert len({run["id"] for run in runs}) == len(runs)
    for run in runs:
        ExperimentConfig.from_dict({**plan["defaults"], **run["config"]}).validate()
