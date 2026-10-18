"""Build paper v5 without modifying experiments or presenting partial runs as final.

Only the explicitly named v15.4 CIFAR-10 seed-42 batches are accepted. Generated
results stay blank until all sixteen executions pass consistency checks. The
blank-template PDF remains separate from the automatically populated paper.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from atomic_io import atomic_write_json, atomic_write_text, replace_with_retry

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "result_check/paper_version_staging/versions/v05_v15_4_cifar10"
REVISION = "v15_4_fresh_certificate_memory_v1"
SHARES = (30, 40)
SPLITS = ("iid", "noniid")
ATTACKS = ("FR1", "FR2", "FR3", "FR4")
KEYS = [(p, s, a) for p in SHARES for s in SPLITS for a in ATTACKS]
INPUTS = ("latest_results.json", "run_config.json", "protocol.json", "global_metrics.csv",
          "removals.csv", "detection_summary.csv", "cycle_signals.csv", "client_metrics.csv")
SOURCE_FILES = {"server/v15_protocol.py", "server/diagonal_decision.py", "server/v15_evidence.py",
                "server/v15_strict_norm.py", "server/v15_certificate_memory.py", "train_v15_4.py"}
SETTING_VALUES = dict(methodology_version="swtcp_v15_4", dataset="cifar10", seed=42,
    num_clients=100, num_rounds=100, warmup_rounds=10, surveillance_groups=10,
    v15_cycle_rounds=10, cycle_strong_cycles_for_removal=2, cycle_suspect_clean_cycles=2,
    cycle_candidate_clean_cycles=2, v15_candidate_review_cycles=2,
    v15_candidate_cooldown_audits=2, cycle_reference_probation_cycles=1,
    v15_audit_interval_rounds=10, local_epochs=3, batch_size=32, optimizer="sgd",
    learning_rate=.01, momentum=.9, dirichlet_alpha=.5, trap_noise_scale=.01,
    trap_noise_floor=.0001, zero_update_epsilon=.000001, fr2_update_range=.001,
    fr3_window=5, fr4_history_size=5, fr4_noise_fraction=.1, fr4_cold_start_scale=.0001)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value):
    result = float(value)
    require(math.isfinite(result), f"Non-finite measurement: {value}")
    return result


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def batch_path(root, share):
    return root / "results" / f"v15_4_cifar10_seed42_fr{share}"


def run_id(split, attack):
    return f"v15_4_cifar10_{split}_{attack}_seed42"


def discover(root):
    """Read only completion markers, never train or resume an experiment."""
    paths, waiting = {}, []
    for share in SHARES:
        batch = batch_path(root, share)
        if not (batch / "experiment_status.json").exists():
            waiting.append(f"{batch.name}: not started")
            continue
        status = read_json(batch / "experiment_status.json")
        if status.get("state") != "completed":
            waiting.append(f"{batch.name}: {status.get('state', 'unknown')}")
            continue
        require(status.get("failed_experiments") == 0, f"Failed executions in {batch}")
        manifest = read_json(batch / "experiment_manifest.json")
        expected = {run_id(s, a) for s in SPLITS for a in ATTACKS}
        require(len(manifest["experiments"]) == 8 and
                {e["id"] for e in manifest["experiments"]} == expected,
                f"Unexpected or duplicate experiment grid in {batch}")
        require(len(status["experiments"]) == 8 and
                {e["id"] for e in status["experiments"]} == expected and
                all(e["state"] == "completed" for e in status["experiments"]),
                f"Inconsistent completed batch marker: {batch}")
        for split in SPLITS:
            for attack in ATTACKS:
                run = batch / run_id(split, attack)
                marker = read_json(run / "latest_results.json")
                require(marker.get("completed") is True and marker.get("latest_round") == 100,
                        f"Incomplete completed-run marker: {run}")
                paths[(share, split, attack)] = run
    return paths, waiting


def extract(run, key, expected_dataset="cifar10"):
    share, split, attack = key
    config = read_json(run / "run_config.json")
    for field, expected in {**SETTING_VALUES, "dataset": expected_dataset}.items():
        require(config.get(field) == expected, f"Unexpected {field} in {run}")
    require(config.get("distribution") == split and config.get("attack_type") == attack and
            config.get("free_rider_pct") == share / 100 and config.get("completed_rounds") == 100,
            f"Configuration/grid mismatch: {run}")
    protocol = read_json(run / "protocol.json")
    require(protocol["policy"]["revision"] == REVISION and config.get("protocol") == protocol,
            f"Wrong or inconsistent detector provenance: {run}")
    require(SOURCE_FILES <= set(protocol["implementation_sha256"]) and
            protocol["policy"].get("certificate_revision") == "v15_3_strict_norm_v1" and
            protocol["policy"].get("round_dependent_thresholds") is False,
            f"Missing frozen implementation/policy evidence: {run}")
    metrics = read_csv(run / "global_metrics.csv")
    require([int(row["round"]) for row in metrics] == list(range(1, 101)),
            f"Missing, repeated or unsorted training rounds: {run}")
    for row in metrics:
        require(0 <= number(row["global_accuracy"]) <= 1 and number(row["round_time_seconds"]) >= 0,
                f"Invalid utility/timing measurement: {run}")
    truth = {}
    coverage = set()
    for row in read_csv(run / "cycle_signals.csv"):
        client, label = int(row["client_id"]), int(row["is_free_rider"])
        require(0 <= client < 100 and label in (0, 1), f"Invalid evaluation identity: {run}")
        require(client not in truth or truth[client] == label, f"Changing ground truth: {run}")
        truth[client] = label
        if int(row["round"]) == 20:
            pair = (client, int(row["trap_id"]))
            require(pair not in coverage, f"Duplicate initial probe: {run}")
            coverage.add(pair)
    require(coverage == {(c, t) for c in range(100) for t in (0, 1)} and
            len(truth) == 100 and sum(truth.values()) == share,
            f"Missing initial coverage or incorrect evaluation prevalence: {run}")
    removals = read_csv(run / "removals.csv")
    seen = set()
    for row in removals:
        client = int(row["client_id"])
        require(client not in seen and client in truth and
                int(row["is_free_rider"]) == truth[client] and 30 <= int(row["round"]) <= 100,
                f"Duplicate, mislabelled or invalid removal: {run}")
        seen.add(client)
    tp = sum(int(r["is_free_rider"]) for r in removals)
    fp = len(removals) - tp
    fn, honest = share - tp, 100 - share
    summary = read_csv(run / "detection_summary.csv")
    require(len(summary) == 1, f"Invalid detection summary: {run}")
    for field, expected in (("removed_free_riders", tp), ("removed_honest_clients", fp), ("missed_free_riders", fn)):
        require(int(summary[0][field]) == expected and int(config[field]) == expected,
                f"Confusion-count mismatch ({field}): {run}")
    quarantined, quarantine_rounds, excluded, observed = set(), 0, 0, set()
    for row in read_csv(run / "client_metrics.csv"):
        client, round_index = int(row["client_id"]), int(row["round"])
        require((round_index, client) not in observed and client in truth and 1 <= round_index <= 100,
                f"Invalid client-round logs: {run}")
        observed.add((round_index, client))
        require(int(row["is_free_rider"]) == truth[client], f"Client evaluation label mismatch: {run}")
        if truth[client] == 0:
            if int(row["was_quarantined"]):
                quarantined.add(client)
                quarantine_rounds += 1
            excluded += int(row["was_aggregated"]) == 0
    removal_rounds = {int(r["client_id"]): int(r["round"]) for r in removals}
    require(observed == {(t, c) for c in truth for t in range(1, 101) if t <= removal_rounds.get(c, 100)},
            f"Missing or unexpected active client-round observations: {run}")
    for field, expected in (("honest_clients_ever_quarantined", len(quarantined)),
                            ("honest_quarantine_client_rounds", quarantine_rounds),
                            ("honest_excluded_active_client_rounds", excluded)):
        require(config.get(field) == expected, f"Honest-exclusion summary mismatch ({field}): {run}")
    final = metrics[-1]
    require(int(final["num_active_clients"]) == 100 - tp - fp, f"Active-population mismatch: {run}")
    require(abs(number(config["final_global_accuracy"]) - number(final["global_accuracy"])) < 1e-10,
            f"Final utility mismatch: {run}")
    candidates = int(config["final_honest_candidate_clients"])
    require(0 <= candidates <= honest - fp, f"Invalid final honest-candidate count: {run}")
    fr_rounds = [int(row["round"]) for row in removals if int(row["is_free_rider"])]
    record = dict(share=share, split=split, attack=attack, seed=42, attackers=share, honest=honest,
        tp=tp, fp=fp, fn=fn, recall=tp / share, precision=tp / (tp + fp) if tp + fp else None,
        f1=2 * tp / (2 * tp + fp + fn), fpr=fp / honest,
        completion_round=max(fr_rounds) if tp == share else None,
        final_accuracy=number(final["global_accuracy"]), final_honest_candidates=candidates,
        honest_ever_quarantined=len(quarantined), honest_quarantine_rounds=quarantine_rounds,
        honest_excluded_active_rounds=excluded, final_quarantined=int(config["quarantined_clients"]),
        mean_round_seconds=sum(number(r["round_time_seconds"]) for r in metrics) / 100,
        peak_process_mib=number(config["peak_process_rss_mb"]),
        wall_seconds=number(config["total_wall_clock_seconds"]))
    curves = []
    for row in metrics:
        round_index = int(row["round"])
        current = [r for r in removals if int(r["round"]) <= round_index]
        curves.append(dict(round=round_index,
            recall=sum(int(r["is_free_rider"]) for r in current) / share,
            fpr=sum(1 - int(r["is_free_rider"]) for r in current) / honest,
            accuracy=number(row["global_accuracy"])))
    return record, curves, protocol


def csv_text(records, delimiter=","):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(records[0]), delimiter=delimiter, lineterminator="\n")
    writer.writeheader()
    writer.writerows(records)
    return buffer.getvalue()


def tables(records=None):
    lookup = {(r["share"], r["split"], r["attack"]): r for r in records or []}
    definitions = [
        ("Removal performance. NR means complete removal was not achieved by round 100; -- denotes pending/undefined evidence.",
         "tab:detection", "rllrrrrrrr",
         r"FR (\%) & Split & Attack & TP & FP & FN & Recall (\%) & Precision (\%) & F1 (\%) & $t_{\rm all}$",
         ("tp", "fp", "fn", "recall", "precision", "f1", "completion_round")),
        ("Utility and honest-client safety. $C_H$ is final honest-candidate count, $Q_H$ unique honest clients ever quarantined, $E_H$ honest quarantine client-rounds, and $Q_T$ all clients quarantined at completion.",
         "tab:safety", "rllrrrrr",
         r"FR (\%) & Split & Attack & Accuracy (\%) & $C_H$ & $Q_H$ & $E_H$ & $Q_T$",
         ("final_accuracy", "final_honest_candidates", "honest_ever_quarantined", "honest_quarantine_rounds", "final_quarantined")),
        ("Whole-simulator resources, not isolated detector overhead. Mean logged round time excludes subsequent checkpoint/log publication; wall time includes initialization and publication. RSS includes training, aggregation and simulated attacker histories.",
         "tab:resources", "rllrrr",
         r"FR (\%) & Split & Attack & Mean round (s) & Peak RSS (MiB) & Wall time (min)",
         ("mean_round_seconds", "peak_process_mib", "wall_seconds")),
    ]
    output = []
    percentages = {"recall", "precision", "f1", "final_accuracy"}
    for caption, label, alignment, header, fields in definitions:
        output += [r"\begin{table*}[t]", r"\centering\footnotesize\setlength{\tabcolsep}{4pt}",
                   rf"\caption{{{caption}}}\label{{{label}}}", rf"\begin{{tabular}}{{{alignment}}}",
                   r"\toprule", header + (" " + chr(92) * 2), r"\midrule"]
        for share, split, attack in KEYS:
            record = lookup.get((share, split, attack))
            values = []
            for field in fields:
                value = record[field] if record else None
                if value is None:
                    values.append("NR" if record and field == "completion_round" else "--")
                elif field in percentages:
                    values.append(f"{100 * value:.2f}")
                elif field == "wall_seconds":
                    values.append(f"{value / 60:.1f}")
                elif field in {"mean_round_seconds", "peak_process_mib"}:
                    values.append(f"{value:.2f}")
                else:
                    values.append(str(value))
            output.append(" & ".join([str(share), "IID" if split == "iid" else "Non-IID", attack, *values]) + r" \\")
        output += [r"\bottomrule", r"\end{tabular}", r"\end{table*}", ""]
    return "\n".join(output)


def blank_figures():
    return "\n".join(r"\begin{figure*}[t]\centering" + "\n" +
        r"\fbox{\parbox[c][5.7cm][c]{0.94\textwidth}{\centering " + title +
        r"\\[8pt]Blank template: populate only after all sixteen runs validate.}}" + "\n" +
        rf"\caption{{{title}. Panels: 30\%/40\% free riders and IID/non-IID.}}" + "\n" +
        r"\end{figure*}" for title in ("Cumulative removal recall", "Honest false-removal rate", "Global test accuracy"))


def figures():
    output = []
    for field, title in (("recall", "Cumulative removal recall"), ("fpr", "Honest false-removal rate"), ("accuracy", "Global test accuracy")):
        output += [r"\begin{figure*}[t]\centering", r"\begin{tikzpicture}",
            r"\begin{groupplot}[group style={group size=2 by 2,horizontal sep=1.15cm,vertical sep=1.35cm},",
            r"width=0.44\textwidth,height=3.5cm,xmin=0,xmax=100,ymin=0,ymax=1,",
            r"xlabel={Round},ylabel={" + title + r"},grid=major,legend style={font=\scriptsize},",
            r"tick label style={font=\scriptsize},title style={font=\small}]" ]
        for share in SHARES:
            for split in SPLITS:
                output.append(r"\nextgroupplot[title={" + f"{share}" + r"\% " + ("IID" if split == "iid" else "Non-IID") + r"}]")
                for attack, color, style in zip(ATTACKS, ("blue", "red", "teal", "orange"), ("solid", "dashed", "dotted", "dashdotted")):
                    path = f"generated/{split}_{attack}_p{share}.dat"
                    output += [rf"\addplot[{color},{style},thick] table[x=round,y={field}] {{{path}}};",
                               rf"\addlegendentry{{{attack}}}"]
        output += [r"\end{groupplot}\end{tikzpicture}",
                   rf"\caption{{{title}, seed 42. All attacks are retained, including misses; coincident curves may overlap.}}",
                   r"\end{figure*}", ""]
    return "\n".join(output)


def initialize(out):
    files = {
        "templates/blank_tables.tex": tables(), "templates/blank_figures.tex": blank_figures(),
        "generated/tables.tex": tables(), "generated/figures.tex": blank_figures(),
        "generated/summary.tex": r"\textit{Results pending. No final quantitative claim is made until both eight-run batches validate.}",
        "generated/banner.tex": r"DRAFT: results pending",
    }
    for name, content in files.items():
        if not (out / name).exists():
            atomic_write_text(out / name, content + "\n")


def compile_pdf(out, stem):
    pdflatex, bibtex = shutil.which("pdflatex"), shutil.which("bibtex")
    require(pdflatex and bibtex, "pdflatex/bibtex not found; generated sources are retained")
    build = out / "build"
    build.mkdir(exist_ok=True)
    latex = [pdflatex, "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape",
             "-output-directory=build", stem + ".tex"]
    commands = [latex, [bibtex, "build/" + stem], latex, latex]
    for command in commands:
        result = subprocess.run(command, cwd=out, capture_output=True, text=True, errors="replace", timeout=240)
        atomic_write_text(build / (stem + ".compile.txt"), result.stdout + result.stderr)
        require(result.returncode == 0, f"Compilation failed for {stem}; see build/{stem}.compile.txt")
    pdf = build / (stem + ".pdf")
    require(pdf.is_file() and pdf.stat().st_size > 0, f"Missing compiled PDF: {stem}")
    temporary = out / ("." + stem + ".pdf.tmp")
    shutil.copyfile(pdf, temporary)
    replace_with_retry(temporary, out / (stem + ".pdf"))


def refresh(root=ROOT, out=OUT, compile_output=False, template_only=False):
    out.mkdir(parents=True, exist_ok=True)
    initialize(out)
    status_file = out / "generated/paper_status.json"
    if template_only:
        if compile_output:
            compile_pdf(out, "paper_v5_template")
            compile_pdf(out, "paper_v5")
        atomic_write_json(status_file, dict(state="template", expected_runs=16, final_results_populated=False))
        return "template"
    paths, waiting = discover(root)
    if waiting:
        atomic_write_json(status_file, dict(state="waiting", expected_runs=16, ready_runs=len(paths),
            final_results_populated=False, waiting=waiting))
        return "waiting"
    require(set(paths) == set(KEYS), "Incomplete result grid")
    sources = [path / name for path in paths.values() for name in INPUTS]
    for share in SHARES:
        sources += [batch_path(root, share) / name for name in ("experiment_manifest.json", "experiment_status.json")]
    sources += [out / name for name in ("paper_v5.tex", "paper_body.tex", "refs.bib")]
    fingerprints = {str(path.resolve()): [path.stat().st_size, path.stat().st_mtime_ns] for path in sources}
    previous = read_json(status_file) if status_file.exists() else {}
    if previous.get("state") == "ready" and previous.get("fingerprints") == fingerprints and (
            not compile_output or (previous.get("compiled") and (out / "paper_v5.pdf").exists())):
        return "unchanged"
    records, provenance, expected_policy, expected_implementation = [], [], None, None
    curves_by_key = {}
    for key in KEYS:
        record, curves, protocol = extract(paths[key], key)
        encoded_policy = json.dumps(protocol["policy"], sort_keys=True)
        if expected_policy is None:
            expected_policy = encoded_policy
            expected_implementation = protocol["implementation_sha256"]
        require(encoded_policy == expected_policy and protocol["implementation_sha256"] == expected_implementation,
                "Detector policy/source hashes differ across executions")
        records.append(record)
        curves_by_key[key] = curves
        provenance.append(dict(key=list(key), files={str((paths[key] / name).relative_to(root)): digest(paths[key] / name)
                                                   for name in INPUTS}))
    for name, expected in expected_implementation.items():
        snapshot = out / "evidence/source" / name
        source = snapshot if snapshot.exists() else root / name
        require(digest(source) == expected, f"Frozen implementation does not match: {name}")
        if not snapshot.exists():
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            temporary = snapshot.with_name("." + snapshot.name + ".tmp")
            shutil.copyfile(source, temporary)
            replace_with_retry(temporary, snapshot)
    tp, fp, fn = (sum(r[k] for r in records) for k in ("tp", "fp", "fn"))
    honest = sum(r["honest"] for r in records)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn)
    f1 = 2 * tp / (2 * tp + fp + fn)
    precision_text = f"{100 * precision:.2f}\\%" if precision is not None else "undefined"
    summary = (f"Across sixteen completed seed-42 executions, {tp}/{tp+fn} free-rider cases and "
               f"{fp}/{honest} honest-client cases were permanently removed. Pooled removal recall is "
               f"{100*recall:.2f}\\%, precision is {precision_text}, and F1 is {100*f1:.2f}\\%. "
               f"There are {sum(r['honest_ever_quarantined'] for r in records)} honest-client cases ever quarantined "
               f"and {sum(r['final_honest_candidates'] for r in records)} final honest-candidate cases. "
               "These are repeated simulation cases, not independent clients or held-out seeds. "
               "See the per-condition tables; incomplete removal remains a failure rather than a missing result.")
    atomic_write_text(out / "generated/tables.tex", tables(records))
    atomic_write_text(out / "generated/summary.tex", summary + "\n")
    atomic_write_text(out / "generated/banner.tex", "Single-seed development evaluation; author review required\n")
    for (share, split, attack), curves in curves_by_key.items():
        atomic_write_text(out / f"generated/{split}_{attack}_p{share}.dat", csv_text(curves, delimiter=" "))
    atomic_write_text(out / "generated/figures.tex", figures())
    atomic_write_text(out / "generated/per_run_statistics.csv", csv_text(records))
    atomic_write_json(out / "generated/provenance.json", dict(revision=REVISION, runs=provenance,
        implementation_sha256=expected_implementation, policy=json.loads(expected_policy)))
    if compile_output:
        compile_pdf(out, "paper_v5")
    atomic_write_json(status_file, dict(state="ready", final_results_populated=True, expected_runs=16,
        validated_runs=16, compiled=compile_output, generated_at_utc=datetime.now(timezone.utc).isoformat(),
        fingerprints=fingerprints, totals=dict(tp=tp, fp=fp, fn=fn, honest=honest)))
    return "ready"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compile", action="store_true")
    parser.add_argument("--template-only", action="store_true")
    parser.add_argument("--update-if-ready", action="store_true", help="Safe completion hook; incomplete batches remain blank")
    args = parser.parse_args()
    try:
        print("Paper v5:", refresh(compile_output=args.compile, template_only=args.template_only))
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
        atomic_write_json(OUT / "generated/paper_status.json", dict(state="blocked", final_results_populated=False,
            reason=str(error)))
        raise


if __name__ == "__main__":
    main()
