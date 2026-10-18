"""Validate all 32 v15.4 runs and regenerate the v2-style full-study paper.

Experiments and older paper folders are read-only inputs. No partial grid,
best-seed selection, or substituted historical method is permitted.
"""
from __future__ import annotations

import argparse
import json
import shutil
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import build_paper_v5_v15_4 as validated
import paper_v6_visuals as visuals
import paper_timing_comparison as timing
from atomic_io import atomic_write_json, atomic_write_text

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "result_check/paper_version_staging/versions/v06_v15_4_full_study"
DATASETS = ("mnist", "cifar10")
SHARES = (30, 40)
SPLITS = ("iid", "noniid")
ATTACKS = ("FR1", "FR2", "FR3", "FR4")
INPUTS = (*validated.INPUTS, "cycle_decisions.csv", "cycle_policy.csv")
read_json, read_csv, require = validated.read_json, validated.read_csv, validated.require


def dataset_name(dataset):
    return "MNIST" if dataset == "mnist" else "CIFAR-10"


def split_name(split):
    return "IID" if split == "iid" else "Non-IID"


def run_id(dataset, split, attack):
    return f"v15_4_{dataset}_{split}_{attack}_seed42"


def discover(root):
    paths = {}
    for dataset in DATASETS:
        for share in SHARES:
            batch = root / "results" / f"v15_4_{dataset}_seed42_fr{share}"
            status = read_json(batch / "experiment_status.json")
            manifest = read_json(batch / "experiment_manifest.json")
            expected = {run_id(dataset, s, a) for s in SPLITS for a in ATTACKS}
            require(status.get("state") == "completed" and status.get("failed_experiments") == 0,
                    f"Unfinished batch: {batch}")
            for entries in (manifest["experiments"], status["experiments"]):
                require(len(entries) == 8 and {e["id"] for e in entries} == expected,
                        f"Incorrect grid: {batch}")
            require(all(e["state"] == "completed" for e in status["experiments"]),
                    f"Unfinished run state: {batch}")
            for split in SPLITS:
                for attack in ATTACKS:
                    path = batch / run_id(dataset, split, attack)
                    marker = read_json(path / "latest_results.json")
                    require(marker.get("completed") is True and marker.get("latest_round") == 100,
                            f"Unfinished run: {path}")
                    paths[(dataset, share, split, attack)] = path
    return paths


def extract(run, key):
    dataset, share, split, attack = key
    record, curves, protocol = validated.extract(run, (share, split, attack), expected_dataset=dataset)
    config = read_json(run / "run_config.json")
    clients = read_csv(run / "client_metrics.csv")
    honest = [r for r in clients if int(r["is_free_rider"]) == 0]
    trap_rounds = sum(int(r["was_trapped"]) for r in honest)
    require(trap_rounds == config["honest_trap_client_rounds"], f"Trap cost mismatch: {run}")
    require(config["device_resolved"] == "cpu", f"Device differs from reported CPU study: {run}")
    record = dict(dataset=dataset, **record, device="CPU", honest_trap_rounds=trap_rounds,
                  honest_active_rounds=len(honest))
    by_round = defaultdict(list)
    for row in clients:
        by_round[int(row["round"])].append(row)
    metrics = read_csv(run / "global_metrics.csv")
    if record["fn"] == 0:
        require(int(metrics[-1]["num_candidate_clients"]) == record["final_honest_candidates"],
                f"Final honest-candidate count differs from active-population logs: {run}")
    for curve, metric in zip(curves, metrics):
        current_honest = [r for r in by_round[curve["round"]] if int(r["is_free_rider"]) == 0]
        curve.update(candidates=int(metric["num_candidate_clients"]),
                     honest_quarantined=sum(int(r["was_quarantined"]) for r in current_honest),
                     honest_excluded=sum(not int(r["was_aggregated"]) for r in current_honest))
    decisions = read_csv(run / "cycle_decisions.csv")
    history = []
    for round_index in sorted({int(r["round"]) for r in decisions}):
        current = [r for r in decisions if int(r["round"]) == round_index]
        fr = [r for r in current if int(r["is_free_rider"])]
        h = [r for r in current if not int(r["is_free_rider"])]
        history.append(dict(dataset=dataset, share=share, split=split, attack=attack, round=round_index,
            fr_norm=sum("norm_low" in r["strong_channels"].split(",") for r in fr),
            fr_profile=sum("profile_high" in r["strong_channels"].split(",") for r in fr),
            honest_strong=sum(r["state"] == "S" for r in h),
            honest_candidates=sum(r["category_after"] == "C" for r in h),
            honest_quarantined=sum(int(r["quarantined"]) for r in h)))
    return record, curves, protocol, history


def aggregate(records):
    groups = []
    for dataset in DATASETS:
        for share in SHARES:
            for split in SPLITS:
                runs = [r for r in records if (r["dataset"], r["share"], r["split"]) == (dataset, share, split)]
                require(len(runs) == 4 and {r["attack"] for r in runs} == set(ATTACKS), "Incomplete attack group")
                tp, fp, fn = (sum(r[f] for r in runs) for f in ("tp", "fp", "fn"))
                groups.append(dict(dataset=dataset, share=share, split=split, tp=tp, fp=fp, fn=fn,
                    precision=tp / (tp + fp) if tp + fp else None, recall=tp / (tp + fn),
                    f1=2 * tp / (2 * tp + fp + fn), accuracy_min=min(r["final_accuracy"] for r in runs),
                    accuracy_max=max(r["final_accuracy"] for r in runs),
                    completion_min=min((r["completion_round"] for r in runs if r["completion_round"] is not None), default=None),
                    completion_max=max((r["completion_round"] for r in runs if r["completion_round"] is not None), default=None),
                    completed_detection=sum(r["completion_round"] is not None for r in runs),
                    candidates=sum(r["final_honest_candidates"] for r in runs),
                    honest_quarantined=sum(r["honest_ever_quarantined"] for r in runs),
                    quarantine_rounds=sum(r["honest_quarantine_rounds"] for r in runs),
                    trap_rounds=sum(r["honest_trap_rounds"] for r in runs),
                    excluded_rounds=sum(r["honest_excluded_active_rounds"] for r in runs),
                    active_honest_rounds=sum(r["honest_active_rounds"] for r in runs),
                    mean_round_seconds=statistics.mean(r["mean_round_seconds"] for r in runs),
                    mean_peak_gib=statistics.mean(r["peak_process_mib"] for r in runs) / 1024,
                    mean_execution_minutes=statistics.mean(r["wall_seconds"] for r in runs) / 60))
    return groups


def table(caption, label, alignment, header, rows, wide=True, note=None):
    environment = "table*" if wide else "table"
    return "\n".join([rf"\begin{{{environment}}}[t]", r"\centering\footnotesize\setlength{\tabcolsep}{4pt}",
        rf"\caption{{{caption}}}\label{{{label}}}", rf"\begin{{tabular}}{{{alignment}}}",
        r"\toprule", header + r" \\", r"\midrule", *[" & ".join(row) + r" \\" for row in rows],
        r"\bottomrule", r"\end{tabular}",
        (r"\par\smallskip\begin{minipage}{0.96\textwidth}\scriptsize " + note + r"\end{minipage}" if note else ""),
        rf"\end{{{environment}}}", ""])


def fmt(value, percent=False):
    return "--" if value is None else f"{value * 100 if percent else value:.2f}"


def range_text(low, high, percent=False):
    if low is None or high is None:
        return "NR"
    if percent:
        return f"{100*low:.2f}--{100*high:.2f}"
    return str(low) if low == high else f"{low}--{high}"


def make_tables(records, groups):
    prefix = lambda g: [dataset_name(g["dataset"]), split_name(g["split"]), str(g["share"])]
    performance = table(
        "Detection quality, attack-specific final test accuracy (\\%), and mean round time. Each row groups four attacks; seed 42, 100 rounds.",
        "tab:performance", "llrrrrrrrr", r"Dataset & Partition & FR (\%) & Precision (\%) & Recall (\%) & FR1 acc. & FR2 acc. & FR3 acc. & FR4 acc. & s/round",
        [prefix(g) + [fmt(g[k], True) for k in ("precision", "recall")] +
         [fmt(next(r['final_accuracy'] for r in records if (r['dataset'], r['share'], r['split'], r['attack']) ==
              (g['dataset'], g['share'], g['split'], attack)), True) for attack in ATTACKS] +
         [fmt(g['mean_round_seconds'])] for g in groups],
        note="Precision/recall pool permanent removals over FR1--FR4; accuracy measures the global model, not the detector. Time averages the four logged mean round times. Detailed counts and completion rounds are retained in Appendix A.")
    impact_rows = []
    for r in records:
        if r['honest_ever_quarantined'] or r['attack'] == 'FR3':
            impact_rows.append([dataset_name(r['dataset']), split_name(r['split']), str(r['share']), r['attack'],
                f"{r['final_honest_candidates']}/{r['honest']}", str(r['honest_ever_quarantined']),
                str(r['honest_quarantine_rounds']), str(r['honest_trap_rounds']),
                str(r['honest_excluded_active_rounds'] - r['honest_trap_rounds']),
                f"{100*r['honest_excluded_active_rounds']/r['honest_active_rounds']:.2f}"])
    safety = table(
        "Honest-client burden by individual FR3 run, plus any other run with honest quarantine. All runs end with zero permanent honest removals and zero quarantined clients.",
        "tab:safety", "llrlrrrrrr", r"Dataset & Partition & FR (\%) & Attack & \shortstack{Final honest\\candidates} & \shortstack{Ever\\quarantined} & \shortstack{Quarantine\\client-rounds} & \shortstack{Trap\\client-rounds} & \shortstack{Non-trap\\excluded} & \shortstack{All excluded\\(\%)}",
        impact_rows,
        note="Candidate entries are unresolved honest clients / honest population. Quarantine client-rounds count clients times rounds, and can overlap trap client-rounds. Non-trap excluded counts only withheld honest responses not already explained by traps; the last column divides all withheld honest responses by active honest client-rounds. The complete per-run appendix retains the other attacks.")
    costs = table(
        "Measured whole-simulator resource comparison on CPU: mean [minimum--maximum] across FR1--FR4; execution is mean minutes per run.",
        "tab:cost", "llrrrr", r"Dataset & Partition & FR (\%) & s/round: mean [range] & Peak RSS GiB: mean [range] & min/run",
        [prefix(g) + [f"{g['mean_round_seconds']:.1f} [{min(r['mean_round_seconds'] for r in records if (r['dataset'],r['share'],r['split']) == (g['dataset'],g['share'],g['split'])):.1f}--{max(r['mean_round_seconds'] for r in records if (r['dataset'],r['share'],r['split']) == (g['dataset'],g['share'],g['split'])):.1f}]",
         f"{g['mean_peak_gib']:.2f} [{min(r['peak_process_mib']/1024 for r in records if (r['dataset'],r['share'],r['split']) == (g['dataset'],g['share'],g['split'])):.2f}--{max(r['peak_process_mib']/1024 for r in records if (r['dataset'],r['share'],r['split']) == (g['dataset'],g['share'],g['split'])):.2f}]",
         f"{g['mean_execution_minutes']:.1f}"] for g in groups],
        note="Peak RSS includes local training, aggregation, logged evidence and simulated attacker histories. Round timing ends before checkpoint/log publication. Neither column isolates detector overhead or controls machine load.")
    details = []
    for dataset in DATASETS:
        rows = [[str(r["share"]), split_name(r["split"]), r["attack"], *[str(r[k]) for k in ("tp", "fp", "fn")],
                 str(r["completion_round"]) if r["completion_round"] is not None else "NR", fmt(r["final_accuracy"], True),
                 *[str(r[k]) for k in ("final_honest_candidates", "honest_ever_quarantined", "honest_quarantine_rounds")]]
                for r in records if r["dataset"] == dataset]
        details.append(table(f"Complete per-run {dataset_name(dataset)} outcomes. Every run has 100 rounds and seed 42. Definitions match Tables~\\ref{{tab:performance}} and~\\ref{{tab:safety}}; all outcomes, including failures if present, are retained.",
            "tab:detail-" + dataset, "rllrrrrrrrr",
            r"FR (\%) & Partition & Attack & TP & FP & FN & $t_{\rm all}$ & Accuracy (\%) & $C_H$ & $Q_H$ & $q_H$", rows))
    return {"performance.tex": performance, "safety.tex": safety, "cost.tex": costs, "details.tex": "\n".join(details)}


def make_figure(field, caption, label, ymin, ymax, curves=None):
    lines = [r"\begin{figure*}[tp]\centering", r"\begin{tikzpicture}",
        r"\begin{groupplot}[group style={group size=2 by 4,horizontal sep=0.9cm,vertical sep=1.25cm},",
        rf"width=0.455\textwidth,height=4.6cm,xmin={'60' if curves else '0'},xmax=100,",
        (rf"ymin={ymin},ymax={ymax}," if not curves else ""),
        r"grid=major,xtick={0,30,60,100},tick label style={font=\scriptsize},",
        r"title style={font=\small},label style={font=\scriptsize},legend style={font=\scriptsize,draw=none},",
        r"legend columns=4]"]
    for dataset in DATASETS:
        for attack in ATTACKS:
            ylabel = (r",ylabel={Removal recall}" if field == "recall" else
                      r",ylabel={Test accuracy (\%)}" if curves else r",ylabel={Test accuracy}") if attack == "FR1" else ""
            legend = rf",legend to name={label}-legend" if dataset == "mnist" and attack == "FR1" else ""
            xlabel = r",xlabel={Round}" if dataset == 'cifar10' and attack in ('FR3','FR4') else ''
            zoom = ""
            if curves:
                values = [100*r['accuracy'] for key, rows in curves.items() if key[0] == dataset and key[3] == attack for r in rows if r['round'] >= 60]
                zoom = f",ymin={min(values)-.12:.3f},ymax={max(values)+.12:.3f},xtick={{60,80,100}},scaled y ticks=false,yticklabel style={{/pgf/number format/fixed,/pgf/number format/precision=1}}"
            lines.append(r"\nextgroupplot[title={" + dataset_name(dataset) + " " + attack + "}" + ylabel + xlabel + legend + zoom + "]")
            for (share, split), color, style in zip(((30, "iid"), (30, "noniid"), (40, "iid"), (40, "noniid")),
                                                    ("blue", "red!80!black", "teal!70!black", "orange!90!black"),
                                                    ("solid", "dashed", "dotted", "dashdotted")):
                plot_style = ",const plot" if field == "recall" else ""
                column = "y expr=100*\\thisrow{accuracy}" if curves else f"y={field}"
                lines.append(rf"\addplot[{color},{style},thick{plot_style}] table[x=round,{column}] {{generated/{dataset}_{split}_{attack}_p{share}.dat}};")
                if dataset == "mnist" and attack == "FR1":
                    lines.append(rf"\addlegendentry{{{share}\% {split_name(split)}}}")
    lines += [r"\end{groupplot}\end{tikzpicture}", rf"\par\ref{{{label}-legend}}", rf"\caption{{{caption}}}\label{{{label}}}", r"\end{figure*}"]
    return "\n".join(line for line in lines if line) + "\n"


def build(root=ROOT, out=OUT, compile_output=False):
    paths = discover(root)
    records, provenance, histories, all_curves = [], [], [], {}
    expected_policy = expected_sources = None
    for key, run in paths.items():
        record, curves, protocol, history = extract(run, key)
        policy = json.dumps(protocol["policy"], sort_keys=True)
        if expected_policy is None:
            expected_policy, expected_sources = policy, protocol["implementation_sha256"]
        require(policy == expected_policy and protocol["implementation_sha256"] == expected_sources,
                "Detector policy/source hashes differ across the 32 runs")
        records.append(record)
        all_curves[key] = curves
        histories.extend(history)
        provenance.append(dict(key=list(key), files={str((run / name).relative_to(root)): validated.digest(run / name) for name in INPUTS}))
        dataset, share, split, attack = key
        atomic_write_text(out / f"generated/{dataset}_{split}_{attack}_p{share}.dat", validated.csv_text(curves, delimiter=" "))
    for name, expected in expected_sources.items():
        source = root / name
        require(validated.digest(source) == expected, f"Frozen source mismatch: {name}")
        target = out / "evidence/source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    groups = aggregate(records)
    for name, text in make_tables(records, groups).items():
        atomic_write_text(out / "generated" / name, text)
    atomic_write_text(out / "generated/recall_figure.tex", make_figure("recall",
        "Cumulative free-rider removal recall in all 32 runs. Enlarged two-column panels identify dataset and attack in each title; the four lines distinguish partition and attacker share. Coincident curves overlap. Complete outcomes are retained, including incomplete detection if present.", "fig:recall", 0, 1.05))
    atomic_write_text(out / "generated/accuracy_figure.tex", make_figure("accuracy",
        "Late-training global test accuracy (rounds 60--100; all 32 runs). Each panel uses its OWN data-derived vertical range in percentage points to expose differences hidden by a 0--100 percent scale. Compare numeric ticks, not apparent slope across panels. Full trajectories appear in the appendix; no smoothing or runs are omitted.", "fig:accuracy", 0, 1.02, all_curves))
    atomic_write_text(out / "generated/accuracy_overview_figure.tex", make_figure("accuracy",
        "Full, unzoomed global test-accuracy trajectories for all 32 runs, providing context for the late-training detail in the main text.", "fig:accuracy-overview", 0, 1.02))
    visuals.build(paths, records, out)
    timing.build(root, out)
    totals = {k: sum(r[k] for r in records) for k in ("tp", "fp", "fn", "honest", "honest_ever_quarantined", "honest_quarantine_rounds", "final_honest_candidates")}
    macros = {"StudyRuns": len(records), "StudyTP": totals["tp"], "StudyFP": totals["fp"], "StudyFN": totals["fn"],
              "StudyHonest": totals["honest"], "StudyQuarantined": totals["honest_ever_quarantined"],
              "StudyQuarantineRounds": totals["honest_quarantine_rounds"], "StudyCandidates": totals["final_honest_candidates"]}
    atomic_write_text(out / "generated/numbers.tex", "\n".join(rf"\newcommand{{\{k}}}{{{v}}}" for k, v in macros.items()) + "\n")
    atomic_write_text(out / "generated/per_run_statistics.csv", validated.csv_text(records))
    atomic_write_text(out / "generated/group_statistics.csv", validated.csv_text(groups))
    atomic_write_text(out / "generated/certificate_history.csv", validated.csv_text(histories))
    atomic_write_json(out / "generated/provenance.json", dict(revision=validated.REVISION,
        generated_at_utc=datetime.now(timezone.utc).isoformat(), runs=provenance,
        implementation_sha256=expected_sources, policy=json.loads(expected_policy)))
    if compile_output:
        validated.compile_pdf(out, "paper_v6")
    atomic_write_json(out / "generated/paper_status.json", dict(state="ready", validated_runs=len(records),
        compiled=compile_output, totals=totals, generated_at_utc=datetime.now(timezone.utc).isoformat()))
    return records, groups


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compile", action="store_true")
    args = parser.parse_args()
    records, _ = build(compile_output=args.compile)
    print(f"Paper v6: validated {len(records)} complete runs; compiled={args.compile}")
