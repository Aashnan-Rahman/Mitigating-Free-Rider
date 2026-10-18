"""Reproducible all-run v8 analysis; never overwrite archived v2/v3 or results."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import shutil
from collections import defaultdict
from pathlib import Path
from statistics import mean, median, stdev, quantiles

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "result_check/results_v8_organized/organized"
BASE = ROOT / "result_check/paper_version_staging/versions/v02_introduction_draft"
OUT = ROOT / "result_check/paper_version_staging/versions/v04_v8_behavior_statistics"


def rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def number(value):
    if value in (None, "", "None"):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_csv(path, records):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def extract(run):
    cfg = json.loads((run / "run_config.json").read_text())
    metrics = rows(run / "global_metrics.csv")
    if sorted(int(row["round"]) for row in metrics) != list(range(1, 101)):
        raise ValueError(f"Not a complete 100-round execution: {run}")
    metrics.sort(key=lambda row: int(row["round"]))
    summary = rows(run / "detection_summary.csv")[0]
    removals = rows(run / "removals.csv")
    assert len({row["client_id"] for row in removals}) == len(removals), run
    tp = sum(int(row["is_free_rider"]) for row in removals)
    fp = len(removals) - tp
    attackers = int(cfg["num_free_riders"])
    honest = int(cfg["num_clients"]) - attackers
    assert tp == int(summary["removed_free_riders"]) and fp == int(summary["removed_honest_clients"]), run
    attack_rounds = [int(row["round"]) for row in removals if row["is_free_rider"] == "1"]
    record = {"dataset": cfg["dataset"], "distribution": cfg["distribution"],
              "share_pct": round(100 * cfg["free_rider_pct"]), "attack": cfg["attack_type"],
              "seed": cfg["seed"], "attackers": attackers, "honest": honest,
              "tp": tp, "fp": fp, "fn": attackers - tp,
              "recall_pct": 100 * tp / attackers,
              "precision_pct": 100 * tp / (tp + fp) if tp + fp else None,
              "f1_pct": 200 * tp / (2 * tp + fp + attackers - tp),
              "final_accuracy_pct": 100 * float(metrics[-1]["global_accuracy"]),
              "first_attacker_removal": min(attack_rounds) if attack_rounds else None,
              "full_detection_round": max(attack_rounds) if tp == attackers else None,
              "source": str(run.relative_to(ROOT))}
    # Initial double-coverage decision only. Rows are client-level combined
    # summaries, not independent probes; do not use was_trapped to select them.
    audit = []
    with (run / "client_metrics.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if int(row["round"]) != 20 or not row.get("coverage_checks"):
                continue
            audit.append({"is_free_rider": int(row["is_free_rider"]),
                          "norm_z": number(row["norm_z_score"]),
                          "profile_z": number(row["profile_z_score"]),
                          "norm_flag": int(row["magnitude_flag"]),
                          "profile_flag": int(row["profile_flag"]),
                          "checks": int(row["coverage_checks"]),
                          "joint_checks": int(row["coverage_joint_flags"] or 0)})
    proof = {"source": record["source"], "config_sha256": digest(run / "run_config.json"),
             "removals_sha256": digest(run / "removals.csv"),
             "client_metrics_sha256": digest(run / "client_metrics.csv")}
    return record, audit, cfg, proof


def summarize(records, audit):
    tp, fp, fn = (sum(row[key] for row in records) for key in ("tp", "fp", "fn"))
    recall = [row["recall_pct"] for row in records]
    accuracy = [row["final_accuracy_pct"] for row in records]
    full = [row["full_detection_round"] for row in records if row["full_detection_round"] is not None]
    out = {"dataset": records[0]["dataset"], "distribution": records[0]["distribution"],
           "share_pct": records[0]["share_pct"], "attack": records[0]["attack"],
           "runs": len(records), "seeds": ";".join(str(row["seed"]) for row in records),
           "tp": tp, "fp": fp, "fn": fn,
           "recall_mean_pct": mean(recall), "recall_sd_pct": stdev(recall),
           "recall_min_pct": min(recall), "recall_max_pct": max(recall),
           "pooled_precision_pct": 100 * tp / (tp + fp) if tp + fp else None,
           "pooled_f1_pct": 200 * tp / (2 * tp + fp + fn),
           "macro_f1_mean_pct": mean(row["f1_pct"] for row in records),
           "honest_removed_mean": fp / len(records),
           "honest_removal_rate_pct": 100 * fp / sum(row["honest"] for row in records),
           "full_detection_runs": len(full),
           "full_detection_median_round": median(full) if full else None,
           "full_detection_min_round": min(full) if full else None,
           "full_detection_max_round": max(full) if full else None,
           "final_accuracy_mean_pct": mean(accuracy), "final_accuracy_sd_pct": stdev(accuracy)}
    for label, name in ((1, "attacker"), (0, "honest")):
        selected = [row for row in audit if row["is_free_rider"] == label]
        out[f"audit_{name}_clients"] = len(selected)
        for component in ("norm_z", "profile_z"):
            values = [row[component] for row in selected if row[component] is not None]
            quart = quantiles(values, n=4, method="inclusive") if len(values) > 1 else [None] * 3
            out[f"audit_{name}_{component}_median"] = median(values) if values else None
            out[f"audit_{name}_{component}_q25"] = quart[0]
            out[f"audit_{name}_{component}_q75"] = quart[2]
        for flag in ("norm_flag", "profile_flag"):
            out[f"audit_{name}_{flag}_pct"] = 100 * mean(row[flag] for row in selected) if selected else None
        checks = sum(row["checks"] for row in selected)
        out[f"audit_{name}_joint_probe_pct"] = 100 * sum(row["joint_checks"] for row in selected) / checks if checks else None
    return out


def fmt(value, places=1):
    return "--" if value is None else f"{value:.{places}f}"


def tables(summary, behavior=False):
    output = []
    for dataset in ("mnist", "cifar10"):
        for distribution in ("iid", "noniid"):
            title = ("MNIST" if dataset == "mnist" else "CIFAR-10") + (" IID" if distribution == "iid" else " non-IID")
            subset = [row for row in summary if row["dataset"] == dataset and row["distribution"] == distribution]
            output += [r"\begin{table*}[t]\centering\scriptsize",
                       r"\setlength{\tabcolsep}{3.5pt}"]
            if not behavior:
                output += [r"\caption{All-run outcomes for " + title + r". Recall and model accuracy are mean $\pm$ sample SD across runs. P/F1 pool removal counts; H-FP is mean honest removals per run. Full is successful executions/total; $T_{all}$ is median completion round among successful executions only.}",
                           r"\begin{tabular}{llrllllllll}\toprule",
                           r"Share & Attack & $n$ & Recall (\%) & Range & P (\%) & F1 (\%) & H-FP & Full & $T_{all}$ & Model acc. (\%) \\\midrule"]
                for row in subset:
                    cells = [str(row["share_pct"]) + r"\%", row["attack"], str(row["runs"]),
                             f'{fmt(row["recall_mean_pct"])} $\\pm$ {fmt(row["recall_sd_pct"])}',
                             f'{fmt(row["recall_min_pct"],0)}--{fmt(row["recall_max_pct"],0)}',
                             fmt(row["pooled_precision_pct"]), fmt(row["pooled_f1_pct"]),
                             fmt(row["honest_removed_mean"]), f'{row["full_detection_runs"]}/{row["runs"]}',
                             fmt(row["full_detection_median_round"],1),
                             f'{fmt(row["final_accuracy_mean_pct"])} $\\pm$ {fmt(row["final_accuracy_sd_pct"])}']
                    output.append(" & ".join(cells) + r" \\")
            else:
                output += [r"\caption{Initial double-coverage evidence at round 20 for " + title + r". Scores pool descriptive client summaries across runs (not independent samples). A/H denotes attackers/honest clients. Flag rates refer to combined logged client summaries; Joint refers to the fraction of recorded probes failing both tests. Undefined scores are --.}",
                           r"\begin{tabular}{llrrrrrrrr}\toprule",
                           r"Share & Attack & A norm-z & A profile-z & H norm-z & H profile-z & A norm flag (\%) & A profile flag (\%) & A joint (\%) & H joint (\%) \\\midrule"]
                for row in subset:
                    cells = [str(row["share_pct"]) + r"\%", row["attack"]]
                    cells += [fmt(row[f"audit_{name}_{component}_median"],2)
                              for name in ("attacker", "honest") for component in ("norm_z", "profile_z")]
                    cells += [fmt(row[f"audit_attacker_{flag}_pct"])
                              for flag in ("norm_flag", "profile_flag")]
                    cells += [fmt(row[f"audit_{name}_joint_probe_pct"]) for name in ("attacker", "honest")]
                    output.append(" & ".join(cells) + r" \\")
            output += [r"\bottomrule\end{tabular}\end{table*}"]
    return "\n".join(output)


def main():
    (OUT / "data").mkdir(parents=True, exist_ok=True)
    grouped, audits = defaultdict(list), defaultdict(list)
    records, proof, configs = [], [], []
    for config_path in sorted(SOURCE.rglob("run_config.json")):
        cfg = json.loads(config_path.read_text())
        if cfg["methodology_version"] != "swtcp_v8":
            continue
        record, audit, cfg, provenance = extract(config_path.parent)
        key = (record["dataset"], record["distribution"], record["share_pct"], record["attack"])
        grouped[key].append(record)
        audits[key].extend(audit)
        records.append(record)
        proof.append(provenance)
        configs.append(cfg)
    assert len(records) == 67 and len(grouped) == 32
    assert len({(r["dataset"], r["distribution"], r["share_pct"], r["attack"], r["seed"]) for r in records}) == 67
    summary = [summarize(grouped[key], audits[key]) for key in sorted(grouped)]
    write_csv(OUT / "data/run_statistics.csv", records)
    write_csv(OUT / "data/attack_statistics.csv", summary)
    (OUT / "provenance.json").write_text(json.dumps(proof, indent=2) + "\n")
    recipe_keys = ["num_clients", "num_rounds", "local_epochs", "batch_size", "learning_rate",
                   "momentum", "warmup_rounds", "magnitude_z_threshold", "profile_z_threshold",
                   "mad_floor", "profile_mad_floor", "coverage_checks_per_client",
                   "anchors_per_suspicion_group", "removal_threshold_points", "dodge_min_probes",
                   "fr3_window", "fr4_history_size", "fr4_noise_fraction"]
    recipe_keys += ["fr2_update_range", "trap_noise_scale", "trap_noise_floor",
                    "dirichlet_alpha", "optimizer", "penalty_zero_update",
                    "penalty_trap_flag", "penalty_suspicion_flag"]
    variants = {key: sorted({str(cfg.get(key)) for cfg in configs}) for key in recipe_keys}
    (OUT / "data/configuration_values.json").write_text(json.dumps(variants, indent=2) + "\n")
    old = (BASE / "masters_paper.tex").read_text(encoding="utf-8")
    prefix = old.split(r"\section{Experimental Design}")[0]
    prefix = prefix.replace("Last updated on 24 September 2026", "Paper v4: v8 archive analysis, 8 October 2026")
    abstract = r"""This revision analyzes all 67 archived completed executions of detector v8, rather than selecting each attack's best seed. The evaluation covers FR1--FR4 on MNIST and CIFAR-10 with IID and Dirichlet non-IID partitions at 30\% and 40\% free riders. We report seed variability, pooled precision and F1, honest removals, detection completion, final model accuracy, and initial norm/profile evidence separately. Most configurations contain two seeds; MNIST non-IID FR4 at 40\% contains five. The results expose both attack-dependent behavior and heterogeneous honest-client false removals. In particular, successful trajectory-imitation detection under some seeds does not imply reliable removal under every seed. These descriptive archival statistics do not establish statistical guarantees, causal effects, or generalization to adaptive attacks. The detector uses server-observable updates; client labels are used only for evaluation."""
    prefix = re.sub(r"\\begin\{abstract\}.*?\\end\{abstract\}", lambda _: "\\begin{abstract}\n" + abstract + "\n\\end{abstract}", prefix, flags=re.S)
    total_tp, total_fp, total_fn = (sum(row[key] for row in records) for key in ("tp", "fp", "fn"))
    text = prefix + r"""
\section{Experimental Design and Statistical Reporting}
This revision retains the v8 methodology described above and reanalyzes its archived logs. It does not report v11--v13 or the later paired/shadow protocol. The archive contains 67 distinct completed 100-round executions across 32 dataset, partition, attacker-share, and attack combinations. Each uses 100 fully participating clients. Most cells contain seeds 42 and 43; MNIST non-IID FR4 at 40\% also includes seeds 44--46. Baseline detector executions are excluded. No unsuccessful completed v8 run is discarded.

The common training recipe is three local epochs, batch size 32, SGD with learning rate 0.01 and momentum 0.9, and a ten-round warm-up. Non-IID partitions use Dirichlet concentration 0.5. The accompanying configuration-values file records archived settings; hardware and seed-dependent data, initialization, attacker selection and challenge trajectories are not controlled causal interventions.

A positive outcome is permanent removal: $TP$ counts removed attackers, $FP$ removed honest clients, and $FN$ remaining attackers. Recall is summarized across runs as mean and sample standard deviation, with its minimum and maximum. Pooled precision is $\sum TP/(\sum TP+\sum FP)$ and pooled F1 is $2\sum TP/(2\sum TP+\sum FP+\sum FN)$. These are not averages of per-run precision/F1. Model accuracy refers to final test classification accuracy, not detector accuracy. Honest removal counts are reported per run, and machine-readable data also include the honest removal rate.

Full-detection counts explicitly expose failures. Completion rounds are conditional on complete removal; incomplete runs are censored beyond the 100-round horizon rather than assigned a fictitious completion time. Seed counts are small, unequal across cells, and sometimes unpaired across attacks. We therefore report descriptive variation, not confidence intervals or claims of statistical superiority. Client observations within a run share a training trajectory and are not independent replicates.

\section{Results}
\subsection{All-Run Attack-Specific Outcomes}
The following four tables separate attacks and attacker shares within each dataset/partition combination. They replace the earlier best-observed tables. Precision, recall and false removal must be considered jointly: high model accuracy is not evidence that free riders were detected, and no honest removals can coexist with complete detection failure.
""" + tables(summary) + r"""
\FloatBarrier
\subsection{Initial Evidence and Attack Behavior}
The next tables describe the round-20 double-coverage decision, before later anchor-based suspicion changes the reference population. Signed norm-z distinguishes smaller from larger updates; profile-z describes upper-tail deviation in the layer-norm profile. Norm/profile flags and joint-probe rates expose whether evidence was one-sided or jointly sufficient for the historical penalty rule. These rates are descriptive logs, not calibrated p-values or independent error estimates. Per-client combined log rows can report a representative response; the recorded joint-probe count preserves the actual number of jointly failing checks. Missing/undefined scores, especially for exact-zero responses, are not replaced by zero.
""" + tables(summary, behavior=True) + r"""
\FloatBarrier
\section{Discussion and Limitations}
Playback (FR1), bounded independent noise (FR2), historical averaging (FR3), and noisy trajectory imitation (FR4) generate different response geometries. Magnitude alone is not a proof of computation: a fabricated update can be nonzero, and genuine non-IID training can be atypical. Joint norm/profile evidence may improve specificity but can miss an attack that deviates in only one component. Initial evidence and eventual removal should therefore not be treated as equivalent outcomes.

The evidence tables expose a concrete distinction at 40\% non-IID MNIST: FR2 has median norm-z $-1.23$ and profile-z $7.70$. Every logged attacker summary has a profile flag, but none has a norm flag and the initial joint-probe rate is zero. FR4 has median norm-z $-1.65$ and profile-z $1.66$, with only 11\% profile-flagged summaries and zero initial joint-probe failures. Thus FR2 produces pronounced single-component evidence, while FR4 often produces neither removal-strength component in the initial population comparison. Later anchor-based decisions can differ substantially from this first audit. Initial honest joint-probe rates are zero on MNIST, yet honest removals later occur; first-audit specificity does not establish whole-run specificity.

The strongest seed sensitivity occurs for MNIST non-IID FR4 at 40\%: seeds 42, 43 and 46 remove none of the 40 attackers, while seeds 44 and 45 remove all 40. Recall is thus 40\% on average with a 0--100\% range. Complete detection in those two successful runs occurs by rounds 83 and 81 respectively; the other three do not complete within 100 rounds. The successful cases demonstrate capability, not robustness. Later removals rely on repeated anchor-based evidence and are affected by reference composition and candidate progression.

Non-IID false removals show that legitimate data heterogeneity can accumulate removal-strength evidence. Failed attacker removal and honest false removal must be reported together. Neither fixed robust-z thresholds nor MAD scaling supply a distribution-free false-positive guarantee under dependent, contaminated and changing populations. Increasing attacker share also changes the training population and peer distribution; the observed 30\%/40\% differences cannot be attributed to attacker share alone because seeds and trajectories are not fully controlled.

Temporary quarantine and withheld probe updates have costs not captured by permanent-removal precision. The archived client logs do not uniformly expose a reliable per-round aggregation/quarantine indicator, so this revision does not fabricate those counts. Runtime and hardware differences are likewise not interpreted as causal speed comparisons. Complete source paths, hashes, seeds, removal counts, conditional timing and score quartiles are supplied with the paper for reproducibility.

\section{Assumptions and Future Work}
The experiments assume fixed attacker identities, full participation, an honest server with individually attributable updates, an honest majority, and one attack implementation per run. The detector does not receive attack labels or client-local loss/accuracy as decision inputs. Dropout, partial computation, on-off behavior, mixed strategies, collusion, defense-aware imitation and ordinary secure aggregation remain outside the demonstrated scope. Future evaluations should separate random streams, use matched multi-seed controls, qualify reference uncertainty, report temporary exclusion, and test related challenge responses without attack-window-specific reconstruction. Any new decision rule requires fresh validation rather than thresholds selected from these archived outcomes.

\section{Conclusion}
All-run statistics reveal limitations hidden by best-observed selection. V8 supplies useful challenge evidence for the evaluated attacks, but its reliability depends on attack behavior, data heterogeneity, and seed-dependent reference trajectories. The attack-specific tables distinguish detection sensitivity, honest-removal cost, completion failures, and model accuracy. They support methodological improvement, not a universal or zero-false-positive detection claim.
\bibliographystyle{IEEEtran}
\bibliography{refs}
\end{document}
"""
    (OUT / "paper_v4.tex").write_text(text, encoding="utf-8")
    shutil.copy2(BASE / "refs.bib", OUT / "refs.bib")
    markdown = ["# V8 all-run attack statistics", "", "Source: 67 completed v8 executions; no best-seed selection.", "",
                "| Dataset / partition | Share | Attack | n | Recall mean ± SD (%) | Range | Honest removed/run | Pooled P/F1 (%) | Full runs | Full-round median | Model accuracy (%) |",
                "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in summary:
        markdown.append(f'| {row["dataset"]} {row["distribution"]} | {row["share_pct"]}% | {row["attack"]} | {row["runs"]} | {fmt(row["recall_mean_pct"])} ± {fmt(row["recall_sd_pct"])} | {fmt(row["recall_min_pct"],0)}–{fmt(row["recall_max_pct"],0)} | {fmt(row["honest_removed_mean"])} | {fmt(row["pooled_precision_pct"])} / {fmt(row["pooled_f1_pct"])} | {row["full_detection_runs"]}/{row["runs"]} | {fmt(row["full_detection_median_round"],1)} | {fmt(row["final_accuracy_mean_pct"])} |')
    markdown += ["", "SD is sample SD across seeds. Full-round median conditions on full detection; -- means no successful completion. Undefined precision is --. Raw CSVs include per-run values, score quartiles and honest-removal rates.", "",
                 "## Provenance", "", f"Totals across executions: {total_tp} removed attackers, {total_fp} removed honest clients, {total_fn} missed attackers. These repeated-run counts are not a unique-client population.", "",
                 "Original v2/v3 and all archived results remain unchanged. Build: python build_paper_v4_v8_statistics.py; compile paper_v4.tex with pdflatex/bibtex in this directory."]
    (OUT / "README.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    print(json.dumps({"runs": len(records), "cells": len(summary), "tp": total_tp, "fp": total_fp, "fn": total_fn,
                      "configuration_variants": {key: value for key, value in variants.items() if len(value) > 1}, "output": str(OUT)}))


if __name__ == "__main__":
    main()
