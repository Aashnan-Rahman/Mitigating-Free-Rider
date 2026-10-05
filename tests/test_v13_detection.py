import copy
import inspect
import json
from dataclasses import fields

import torch

from config import ExperimentConfig
from run_experiments import expand_plan
from server.v13_detection import V13Detector, V13Settings, settings_from_config


def detector(**overrides):
    return V13Detector(settings_from_config(ExperimentConfig(
        methodology_version="swtcp_v13", **overrides)))


def responses(count=25):
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


def test_norm_only_outlier_never_becomes_removal_evidence():
    d = detector()
    batch = responses()
    batch["coverage_norms"][24] = [100, 100]
    result = d.evaluate_cycle(**batch)
    assert result["flags"][24] == 2
    assert not result["coherent_strong"][24]


def test_joint_pair_requires_same_norm_direction_and_fresh_cycles():
    d = detector()
    batch = responses()
    batch["coverage_profiles"][24] = [torch.tensor([1., 0.])] * 2
    batch["coverage_norms"][24] = [100, .001]
    mixed = d.evaluate_cycle(**batch)
    assert not mixed["coherent_strong"][24]
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


def test_leave_one_out_calibration_and_no_current_cycle_feedback():
    d = detector()
    d.calibration = [{0: 100, 1: 4, 2: 5}]
    assert d.cutoff(0, 2) == 5
    assert d.cutoff(1, 2) == 100
    first = detector()
    batch = responses()
    batch["coverage_norms"][24] = [100, 100]
    before = first.cutoff(24, 2)
    first.evaluate_cycle(**batch)
    assert first.last_cutoffs[24] == before


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
