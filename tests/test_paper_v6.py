import json
import shutil
from pathlib import Path

import pytest

import build_paper_v6_full_study as paper
from test_paper_v5 import completed_grid, write_csv, write_json


@pytest.fixture
def full_grid(completed_grid):
    root, _ = completed_grid
    for share in paper.SHARES:
        cifar = root / "results" / f"v15_4_cifar10_seed42_fr{share}"
        mnist = root / "results" / f"v15_4_mnist_seed42_fr{share}"
        shutil.copytree(cifar, mnist)
        for path in list(mnist.iterdir()):
            if path.is_dir():
                path.rename(path.with_name(path.name.replace("cifar10", "mnist")))
        for metadata in ("experiment_manifest.json", "experiment_status.json"):
            content = json.loads((mnist / metadata).read_text())
            for entry in content["experiments"]:
                entry["id"] = entry["id"].replace("cifar10", "mnist")
            write_json(mnist / metadata, content)
        for dataset, batch in (("mnist", mnist), ("cifar10", cifar)):
            for run in (p for p in batch.iterdir() if p.is_dir()):
                config = paper.read_json(run / "run_config.json")
                config.update(dataset=dataset, honest_trap_client_rounds=0, device_resolved="cpu")
                write_json(run / "run_config.json", config)
                clients = paper.read_csv(run / "client_metrics.csv")
                for row in clients:
                    row["was_trapped"] = 0
                write_csv(run / "client_metrics.csv", clients)
                metrics = paper.read_csv(run / "global_metrics.csv")
                for row in metrics:
                    row["num_candidate_clients"] = 0
                write_csv(run / "global_metrics.csv", metrics)
                write_csv(run / "cycle_decisions.csv", [dict(round=20, is_free_rider=0,
                    strong_channels="", state="R", category_after="R", quarantined=0)])
                write_csv(run / "cycle_policy.csv", [dict(round=20, policy="{}")])
    return root, root / "new_paper"


def test_all_32_runs_validate_without_modifying_inputs(full_grid):
    root, out = full_grid
    inputs = {p: paper.validated.digest(p) for p in (root / "results").rglob("*") if p.is_file()}
    records, groups = paper.build(root, out)
    assert len(records) == 32 and len(groups) == 8
    assert sum(r["tp"] for r in records) == 1120
    assert sum(r["honest"] for r in records) == 2080
    assert {r["dataset"] for r in records} == {"mnist", "cifar10"}
    assert paper.read_json(out / "generated/paper_status.json")["validated_runs"] == 32
    assert len(paper.read_csv(out / "generated/per_run_statistics.csv")) == 32
    assert len(list((out / "generated").glob("*.dat"))) == 32
    assert all(paper.validated.digest(path) == checksum for path, checksum in inputs.items())


def test_unfinished_batch_cannot_be_published(full_grid):
    root, out = full_grid
    status = root / "results/v15_4_mnist_seed42_fr30/experiment_status.json"
    value = paper.read_json(status)
    value["state"] = "running"
    write_json(status, value)
    with pytest.raises(ValueError, match="Unfinished batch"):
        paper.build(root, out)
    assert not (out / "generated/paper_status.json").exists()


def test_mnist_run_cannot_silently_use_cifar_configuration(full_grid):
    root, out = full_grid
    config_path = root / "results/v15_4_mnist_seed42_fr30/v15_4_mnist_iid_FR1_seed42/run_config.json"
    config = paper.read_json(config_path)
    config["dataset"] = "cifar10"
    write_json(config_path, config)
    with pytest.raises(ValueError, match="Unexpected dataset"):
        paper.build(root, out)


def test_false_honest_candidate_summary_is_rejected(full_grid):
    root, out = full_grid
    config_path = root / "results/v15_4_mnist_seed42_fr30/v15_4_mnist_iid_FR1_seed42/run_config.json"
    config = paper.read_json(config_path)
    config["final_honest_candidate_clients"] = 3
    write_json(config_path, config)
    with pytest.raises(ValueError, match="candidate count differs"):
        paper.build(root, out)


def test_completed_detection_failure_is_retained_not_dropped(full_grid):
    root, out = full_grid
    run = root / "results/v15_4_mnist_seed42_fr30/v15_4_mnist_iid_FR2_seed42"
    config = paper.read_json(run / "run_config.json")
    config.update(removed_free_riders=0, removed_honest_clients=0, missed_free_riders=30)
    write_json(run / "run_config.json", config)
    (run / "removals.csv").write_text("round,client_id,is_free_rider\n", encoding="utf-8")
    write_csv(run / "detection_summary.csv", [dict(removed_free_riders=0, removed_honest_clients=0, missed_free_riders=30)])
    metrics = paper.read_csv(run / "global_metrics.csv")
    for metric in metrics:
        metric["num_active_clients"] = 100
    write_csv(run / "global_metrics.csv", metrics)
    write_csv(run / "client_metrics.csv", [dict(round=t, client_id=c, is_free_rider=int(c < 30),
        was_quarantined=0, was_trapped=0, was_aggregated=1) for t in range(1, 101) for c in range(100)])
    records, _ = paper.build(root, out)
    failed = next(r for r in records if (r["dataset"], r["share"], r["split"], r["attack"]) == ("mnist", 30, "iid", "FR2"))
    assert failed["recall"] == 0 and failed["precision"] is None and failed["completion_round"] is None
    assert "NR" in (out / "generated/details.tex").read_text()
    assert paper.read_json(out / "generated/paper_status.json")["totals"]["fn"] == 30


def test_manuscript_has_requested_separate_sections():
    source = (paper.OUT / "paper_v6.tex").read_text(encoding="utf-8")
    sections = ["Introduction", "Literature Review", "Threat Model", "Proposed Methodology", "Results",
                "Result Analysis", "Security Analysis", "Conclusion"]
    positions = [source.index(r"\section{" + title + "}") for title in sections]
    assert positions == sorted(positions)
    assert r"\begin{abstract}" in source and r"\appendices" in source
    assert "zero false positives" not in source.lower()


def test_compact_group_statistics_do_not_hide_incomplete_removal():
    records = []
    for dataset in paper.DATASETS:
        for share in paper.SHARES:
            for split in paper.SPLITS:
                for attack in paper.ATTACKS:
                    records.append(dict(dataset=dataset, share=share, split=split, attack=attack,
                        tp=0, fp=0, fn=share, honest=100-share, final_accuracy=.5, completion_round=None,
                        final_honest_candidates=0, honest_ever_quarantined=0,
                        honest_quarantine_rounds=0, honest_trap_rounds=0,
                        honest_excluded_active_rounds=0, honest_active_rounds=100*(100-share),
                        mean_round_seconds=1, peak_process_mib=100, wall_seconds=100,
                        final_quarantined=0))
    groups = paper.aggregate(records)
    assert all(g["completed_detection"] == 0 and g["precision"] is None and g["recall"] == 0 for g in groups)
    assert "NR" in paper.make_tables(records, groups)["details.tex"]
