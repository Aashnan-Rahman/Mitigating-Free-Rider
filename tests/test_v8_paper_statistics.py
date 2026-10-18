import pytest
from build_paper_v4_v8_statistics import summarize


def test_all_run_statistics_do_not_select_best_or_hide_failed_timing():
    records = []
    for seed, tp, fp, completion in [(42, 0, 1, None), (44, 40, 0, 83)]:
        records.append({"dataset": "mnist", "distribution": "noniid", "share_pct": 40,
                        "attack": "FR4", "seed": seed, "tp": tp, "fp": fp,
                        "fn": 40 - tp, "honest": 60, "recall_pct": 100 * tp / 40,
                        "f1_pct": 200 * tp / (2 * tp + fp + 40 - tp),
                        "final_accuracy_pct": 99, "full_detection_round": completion})
    result = summarize(records, [])
    assert result["recall_mean_pct"] == 50
    assert result["recall_sd_pct"] == pytest.approx(70.710678)
    assert result["pooled_precision_pct"] == pytest.approx(4000 / 41)
    assert result["pooled_f1_pct"] == pytest.approx(8000 / 121)
    assert result["full_detection_runs"] == 1
    assert result["full_detection_median_round"] == 83
    assert result["honest_removed_mean"] == .5
    assert result["audit_attacker_norm_z_median"] is None
