import numpy as np
from server.diagonal_decision import classify, policy, evaluation_summary


def population():
    rng = np.random.default_rng(4)
    return [dict(client_id=c, trap_id=t, norm_z=0.,
                 profile_z=float(rng.normal(0 if c < 60 else 20, .2)), exact_zero_delta=0)
            for c in range(100) for t in (0, 1)]


def test_separation_repeatable_and_label_blind():
    rows = population()
    a, metadata = classify(rows)
    b, other = classify([{**r, "is_free_rider": 1, "attack_type": "FR4"} for r in rows])
    assert a == b and metadata == other
    assert [r["state"] for r in a] == ["R"] * 60 + ["S"] * 40
    assert all(r["enforced"] == 0 for r in a)
    assert metadata["bins"] == 10


def test_constant_or_missing_scores_defer_except_exact_zero():
    rows = population()
    for r in rows:
        r["profile_z"] = None
        r["exact_zero_delta"] = int(r["client_id"] == 0)
    a, _ = classify(rows)
    assert a[0]["state"] == "S"
    assert all(r["state"] == "C" for r in a[1:])
    for r in rows:
        r["profile_z"] = 2.
        r["exact_zero_delta"] = 0
    assert all(r["state"] == "C" for r in classify(rows)[0])


def test_majority_gate_and_no_forced_attacker_count():
    rows = population()
    for r in rows:
        r["profile_z"] = r["client_id"] % 3 * .01 if r["client_id"] < 40 else 20 + r["client_id"] * .01
    a, m = classify(rows)
    assert not m["majority_gate"] and all(r["state"] == "C" for r in a)
    assert "free_rider_pct" not in policy()


def test_cifar_plan_is_frozen_eight_runs():
    import json
    from pathlib import Path
    from config import ExperimentConfig
    from run_experiments import expand_plan
    p = json.loads(Path("configs/v14_1_preli_cifar10_diagonal_seed42_plan.json").read_text())
    runs = expand_plan(p, False)
    assert len(runs) == 8
    for run in runs:
        c = ExperimentConfig.from_dict({**p["defaults"], **run["config"]})
        c.validate()
        assert c.dataset == "cifar10" and c.seed == 42 and c.free_rider_pct == .4
        assert c.preliminary_diagonal_decisions and c.num_rounds == 20
    rows, _ = classify(population())
    summary = evaluation_summary([{**r, "is_free_rider": int(r["client_id"] >= 60)} for r in rows])
    assert summary[0]["suspected"] == 40 and summary[1]["safe"] == 60
