import copy
import inspect
import math

import pytest

from server.paired_shadow import PairedShadow, fit_artifact, feature_vector, window_vector


def artifact(alpha=.01, n=100):
    return fit_artifact([[float(i), float(i) / 2] for i in range(100)],
                        [[float(i), float(i) / 2] for i in range(n)],
                        context={}, alpha=alpha, provenance={})


def features(gain=0, norm=1, profile=.1):
    return {"directional_gain": gain, "plus_update_norm": norm,
            "minus_update_norm": norm, "profile_difference": profile,
            "layer_gains": [gain]}


def engine():
    a = artifact()
    a["center"], a["scale"] = [0.] * 4, [1.] * 4
    return PairedShadow(a, context={}, alpha=.01)


def test_boundary_is_calibrated_on_whole_maximum_score():
    a = artifact()
    expected = max(max(abs(i - a["center"][0]) / a["scale"][0],
                       abs(i / 2 - a["center"][1]) / a["scale"][1]) for i in range(100))
    assert a["cutoff"] == expected
    assert artifact(n=98)["cutoff"] is None
    with pytest.raises(ValueError, match="Degenerate"):
        fit_artifact([[1.]] * 100, [[1.]] * 100, context={}, alpha=.01, provenance={})


def test_three_cycles_two_sided_signal_and_no_enforcement():
    for sign in (-1, 1):
        d = engine()
        for cycle in range(3):
            r = d.observe(2, cycle, features(gain=sign * 100, profile=1))
            assert r["proposed_remove"] == int(cycle == 2)
            assert r["enforced"] == 0
        assert len(d.proposed) == 1 and not d.histories[2]
        with pytest.raises(ValueError, match="Repeated"):
            d.observe(2, 2, features())


def test_single_spike_does_not_dominate_window_and_norm_can_support_score():
    d = engine()
    for cycle, value in enumerate([0, 100, 0]):
        r = d.observe(0, cycle, features(gain=value, profile=1))
    assert not r["proposed_remove"]
    for cycle in range(3):
        r = d.observe(1, cycle, features(norm=math.exp(10), profile=1))
    assert r["proposed_remove"]


def test_invalid_features_and_gaps_defer_instead_of_certifying_clearance():
    d = engine()
    d.observe(1, 0, features())
    d.observe(1, 2, features())
    assert len(d.histories[1]) == 1
    r = d.observe(1, 3, features(norm=0))
    assert r["reason"] == "invalid_features_deferred"
    assert not d.histories[1]


def test_checkpoint_freezes_calibration_and_partial_windows():
    d = engine()
    d.observe(1, 0, features(gain=10))
    e = engine()
    e.load_state_dict(copy.deepcopy(d.state_dict()))
    for cycle in [1, 2]:
        assert d.observe(1, cycle, features(gain=10)) == e.observe(1, cycle, features(gain=10))
    altered = engine()
    altered.fingerprint = "changed"
    with pytest.raises(ValueError, match="changed"):
        altered.load_state_dict(d.state_dict())


def test_risk_and_context_mismatch_are_not_silently_recalibrated():
    with pytest.raises(ValueError, match="mismatch"):
        PairedShadow(artifact(), context={}, alpha=.05)
    with pytest.raises(ValueError, match="mismatch"):
        PairedShadow(artifact(), context={"distribution": "noniid"}, alpha=.01)


def test_attack_labels_cannot_affect_features():
    f = features()
    assert feature_vector(f) == feature_vector({**f, "is_free_rider": 1, "attack_type": "FR4"})
    assert set(inspect.signature(PairedShadow.observe).parameters) == {"self", "client", "cycle", "features"}
    assert window_vector([[1, 2], [100, 3], [2, 4]]) == [2, 3]


def test_frozen_file_hash_rejects_modified_artifact(tmp_path):
    import hashlib
    import json
    from server.paired_shadow import load_artifact
    path = tmp_path / "calibration.json"
    from atomic_io import atomic_write_json
    atomic_write_json(path, artifact())
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    assert load_artifact(path, expected) == artifact()
    atomic_write_json(path, artifact(alpha=.05))
    with pytest.raises(ValueError, match="changed"):
        load_artifact(path, expected)


def test_factory_rejects_attack_containing_control(tmp_path):
    from atomic_io import atomic_write_json
    from build_paired_shadow_calibration import read_control
    atomic_write_json(tmp_path / "run_config.json", {"free_rider_pct": .4,
                                                    "paired_measurement_only": True})
    atomic_write_json(tmp_path / "latest_results.json", {"completed": True})
    with pytest.raises(ValueError, match="honest-only"):
        read_control(tmp_path)


def test_fresh_plan_has_no_calibration_seed_or_enforcement_mode():
    import json
    from pathlib import Path
    from config import ExperimentConfig
    from run_experiments import expand_plan
    from server.paired_shadow import context_from_config, load_artifact
    plan = json.loads(Path("configs/v13_paired_shadow_fresh_plan.json").read_text())
    runs = expand_plan(plan, False)
    assert len(runs) == len({run["id"] for run in runs}) == 22
    for run in runs:
        cfg = ExperimentConfig.from_dict({**plan["defaults"], **run["config"]})
        cfg.validate()
        assert cfg.seed in {46, 47} and cfg.paired_measurement_only
        a = load_artifact(cfg.paired_shadow_calibration, cfg.paired_shadow_calibration_sha256)
        PairedShadow(a, context=context_from_config(cfg), alpha=cfg.cycle_target_false_alarm_rate)
