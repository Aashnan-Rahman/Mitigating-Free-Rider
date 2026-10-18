import copy
import torch
import pytest
from server.preliminary_signals import PreliminarySignals


def test_exact_leave_one_out_cosine_and_two_traps():
    d = PreliminarySignals()
    for trap in [0, 1]:
        for client, delta in enumerate([torch.tensor([1., 0.]), torch.tensor([0., 1.]), torch.zeros(2)]):
            d.observe(client, trap, delta, delta, 11 + trap)
    restored = PreliminarySignals()
    restored.load_state_dict(copy.deepcopy(d.state_dict()))
    assert restored.complete() == d.complete()
    rows = d.complete()
    assert len(rows) == 6
    assert rows[0]["cosine_similarity"] == 0
    assert rows[2]["cosine_similarity"] is None
    assert all(row["enforced"] == 0 for row in rows)


def test_preliminary_plan_has_eight_runs_no_shadow():
    import json
    from pathlib import Path
    from config import ExperimentConfig
    from run_experiments import expand_plan
    p = json.loads(Path("configs/v14_1_preli_mnist_plan.json").read_text())
    r = expand_plan(p, False)
    assert len(r) == 8
    for run in r:
        c = ExperimentConfig.from_dict({**p["defaults"], **run["config"]})
        c.validate()
        assert c.num_rounds == 20 and c.warmup_rounds == 10 and c.seed == 42
        assert c.dataset == "mnist" and not c.paired_shadow_calibration
