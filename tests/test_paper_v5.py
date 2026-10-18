import csv
import hashlib
import io
import json
import shutil
from pathlib import Path

import pytest

import build_paper_v5_v15_4 as paper


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def write_csv(path, rows, fields=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def completed_grid(tmp_path):
    root, out = tmp_path / "repo", tmp_path / "paper"
    out.mkdir()
    for name in ("paper_v5.tex", "paper_body.tex", "refs.bib"):
        (out / name).write_text("Author-written source: do not replace\n")
    source_hashes = {}
    for name in paper.SOURCE_FILES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"frozen test source\n")
        source_hashes[name] = paper.digest(path)
    protocol = dict(policy=dict(revision=paper.REVISION, certificate_revision="v15_3_strict_norm_v1",
                                round_dependent_thresholds=False), implementation_sha256=source_hashes)
    for share in paper.SHARES:
        batch = paper.batch_path(root, share)
        experiments = []
        for split in paper.SPLITS:
            for attack in paper.ATTACKS:
                name = paper.run_id(split, attack)
                run = batch / name
                config = dict(paper.SETTING_VALUES, distribution=split, attack_type=attack,
                    free_rider_pct=share / 100, completed_rounds=100, protocol=protocol,
                    removed_free_riders=share, removed_honest_clients=0, missed_free_riders=0,
                    honest_clients_ever_quarantined=0, honest_quarantine_client_rounds=0,
                    honest_excluded_active_client_rounds=0, final_global_accuracy=.75,
                    final_honest_candidate_clients=0, quarantined_clients=0,
                    peak_process_rss_mb=1000, total_wall_clock_seconds=1000)
                write_json(run / "run_config.json", config)
                write_json(run / "protocol.json", protocol)
                write_json(run / "latest_results.json", dict(completed=True, latest_round=100))
                write_csv(run / "global_metrics.csv", [dict(round=t, global_accuracy=.75,
                    round_time_seconds=1, num_active_clients=100 if t < 30 else 100 - share)
                    for t in range(1, 101)])
                write_csv(run / "removals.csv", [dict(round=30, client_id=c, is_free_rider=1) for c in range(share)])
                write_csv(run / "detection_summary.csv", [dict(removed_free_riders=share,
                    removed_honest_clients=0, missed_free_riders=0)])
                write_csv(run / "cycle_signals.csv", [dict(round=20, client_id=c, trap_id=t,
                    is_free_rider=int(c < share)) for c in range(100) for t in (0, 1)])
                write_csv(run / "client_metrics.csv", [dict(round=t, client_id=c,
                    is_free_rider=int(c < share), was_quarantined=0, was_aggregated=1)
                    for c in range(100) for t in range(1, 31 if c < share else 101)])
                experiments.append(dict(id=name, state="completed"))
        write_json(batch / "experiment_manifest.json", dict(experiments=experiments))
        write_json(batch / "experiment_status.json", dict(state="completed", failed_experiments=0,
                                                           experiments=experiments))
    return root, out


def test_partial_batch_keeps_every_result_blank(completed_grid):
    root, out = completed_grid
    path = paper.batch_path(root, 30) / "experiment_status.json"
    status = paper.read_json(path)
    status["state"] = "running"
    write_json(path, status)
    assert paper.refresh(root, out) == "waiting"
    assert "--" in (out / "generated/tables.tex").read_text()
    assert not (out / "generated/per_run_statistics.csv").exists()
    assert paper.read_json(out / "generated/paper_status.json")["final_results_populated"] is False


def test_complete_grid_populates_without_changing_sources(completed_grid):
    root, out = completed_grid
    paths, _ = paper.discover(root)
    before = {str(path): paper.digest(path) for run in paths.values() for path in run.iterdir()}
    author = (out / "paper_body.tex").read_bytes()
    assert paper.refresh(root, out) == "ready"
    status = paper.read_json(out / "generated/paper_status.json")
    assert status["totals"] == dict(tp=560, fp=0, fn=0, honest=1040)
    assert len(paper.read_csv(out / "generated/per_run_statistics.csv")) == 16
    assert all(paper.digest(Path(path)) == digest for path, digest in before.items())
    assert (out / "paper_body.tex").read_bytes() == author
    assert "--" in (out / "templates/blank_tables.tex").read_text()
    assert "100.00" in (out / "generated/tables.tex").read_text()
    assert paper.refresh(root, out) == "unchanged"


def test_completed_detection_failure_is_not_omitted(completed_grid):
    root, _ = completed_grid
    run = paper.batch_path(root, 30) / paper.run_id("noniid", "FR3")
    config = paper.read_json(run / "run_config.json")
    config.update(removed_free_riders=0, missed_free_riders=30)
    write_json(run / "run_config.json", config)
    write_csv(run / "removals.csv", [], fields=["round", "client_id", "is_free_rider"])
    write_csv(run / "detection_summary.csv", [dict(removed_free_riders=0, removed_honest_clients=0, missed_free_riders=30)])
    metrics = paper.read_csv(run / "global_metrics.csv")
    for row in metrics:
        row["num_active_clients"] = 100
    write_csv(run / "global_metrics.csv", metrics)
    write_csv(run / "client_metrics.csv", [dict(round=t, client_id=c, is_free_rider=int(c < 30),
        was_quarantined=0, was_aggregated=1) for c in range(100) for t in range(1, 101)])
    record, _, _ = paper.extract(run, (30, "noniid", "FR3"))
    assert record["tp"] == 0 and record["fn"] == 30
    assert record["precision"] is None and record["completion_round"] is None
    assert "NR" in paper.tables([record])


@pytest.mark.parametrize("fault", ["duplicate_removal", "missing_round", "wrong_method", "changing_truth", "missing_client_round"])
def test_invalid_logs_are_rejected(completed_grid, fault):
    root, _ = completed_grid
    run = paper.batch_path(root, 40) / paper.run_id("iid", "FR1")
    if fault == "duplicate_removal":
        rows = paper.read_csv(run / "removals.csv")
        write_csv(run / "removals.csv", rows + rows[:1])
    elif fault == "missing_round":
        write_csv(run / "global_metrics.csv", paper.read_csv(run / "global_metrics.csv")[:-1])
    elif fault == "wrong_method":
        config = paper.read_json(run / "run_config.json")
        config["methodology_version"] = "swtcp_v15_3"
        write_json(run / "run_config.json", config)
    elif fault == "changing_truth":
        rows = paper.read_csv(run / "cycle_signals.csv")
        rows[0]["is_free_rider"] = 0
        write_csv(run / "cycle_signals.csv", rows)
    else:
        write_csv(run / "client_metrics.csv", paper.read_csv(run / "client_metrics.csv")[:-1])
    with pytest.raises(ValueError):
        paper.extract(run, (40, "iid", "FR1"))


def test_failed_batch_cannot_publish(completed_grid):
    root, out = completed_grid
    path = paper.batch_path(root, 30) / "experiment_status.json"
    status = paper.read_json(path)
    status["failed_experiments"] = 1
    write_json(path, status)
    with pytest.raises(ValueError, match="Failed executions"):
        paper.refresh(root, out)
    assert not (out / "generated/per_run_statistics.csv").exists()


def test_compile_is_not_skipped_after_source_only_population(completed_grid, monkeypatch):
    root, out = completed_grid
    paper.refresh(root, out)
    calls = []
    def compile_fake(folder, stem):
        calls.append(stem)
        (folder / (stem + ".pdf")).write_bytes(b"test compiled output")
    monkeypatch.setattr(paper, "compile_pdf", compile_fake)
    assert paper.refresh(root, out, compile_output=True) == "ready"
    assert calls == ["paper_v5"]
    assert paper.refresh(root, out, compile_output=True) == "unchanged"


def test_actual_completed_fr40_run_is_consistent():
    run = paper.batch_path(paper.ROOT, 40) / paper.run_id("noniid", "FR3")
    if not run.exists():
        pytest.skip("Local completed batch unavailable")
    record, curves, _ = paper.extract(run, (40, "noniid", "FR3"))
    assert record["tp"] == 40 and record["fp"] == 0 and record["completion_round"] == 60
    assert record["honest_ever_quarantined"] == 9
    assert record["honest_quarantine_rounds"] == 180
    assert len(curves) == 100 and curves[58]["recall"] == 0 and curves[59]["recall"] == 1


@pytest.mark.skipif(not shutil.which("pdflatex") or not shutil.which("bibtex"), reason="Local LaTeX unavailable")
def test_complete_tables_and_plot_pipeline_compiles_in_temporary_folder(completed_grid):
    root, out = completed_grid
    for name in ("paper_v5.tex", "paper_v5_template.tex", "paper_body.tex", "refs.bib"):
        shutil.copyfile(paper.OUT / name, out / name)
    assert paper.refresh(root, out, compile_output=True) == "ready"
    assert (out / "paper_v5.pdf").stat().st_size > 0
    assert "\\begin{groupplot}" in (out / "generated/figures.tex").read_text()
    # This is a synthetic fixture under pytest's temporary directory, never
    # the real draft or a source experiment directory.
    assert out != paper.OUT
