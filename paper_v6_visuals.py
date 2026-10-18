"""Read-only score/resource evidence and vector PGFPlots for the v6 manuscript.

Evaluation labels color plots AFTER observations have been recorded. No score,
boundary, policy or experiment is changed by this reporting module.
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

import build_paper_v5_v15_4 as io
from atomic_io import atomic_write_json, atomic_write_text

BLUE = "honestblue"
ORANGE = "riderorange"
COLORS = (BLUE, ORANGE)
FIELDS = ("delta_norm", "norm_z", "profile_z", "diagonal")


def finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def paired_scores(rows):
    """One point per client/full cycle; do not fill missing scores with zero."""
    pairs = defaultdict(dict)
    for row in rows:
        key = int(row["round"]), int(row["client_id"])
        trap = int(row["trap_id"])
        io.require(trap not in pairs[key], f"Duplicate selected trap response: {key}/{trap}")
        pairs[key][trap] = row
    points = []
    for (round_index, client), traps in sorted(pairs.items()):
        if set(traps) != {0, 1}:
            continue  # single-trap audits are not complete-cycle observations
        labels = {int(row["is_free_rider"]) for row in traps.values()}
        io.require(len(labels) == 1, "Inconsistent evaluation labels across traps")
        point = dict(round=round_index, client_id=client, is_free_rider=labels.pop())
        for field in FIELDS[:-1]:
            values = [finite(traps[t].get(field)) for t in (0, 1)]
            point[field] = sum(values) / 2 if all(v is not None for v in values) else None
        point["diagonal"] = (point["profile_z"] - point["norm_z"]
                             if point["norm_z"] is not None and point["profile_z"] is not None else None)
        points.append(point)
    return points


def summarize(points, metadata):
    result = []
    for round_index in sorted({p["round"] for p in points}):
        for label in (0, 1):
            selected = [p for p in points if p["round"] == round_index and p["is_free_rider"] == label]
            if not selected:
                continue
            for field in FIELDS:
                values = [p[field] for p in selected if p[field] is not None]
                quantiles = np.quantile(values, [.25, .5, .75]) if values else (None,) * 3
                result.append(dict(**metadata, round=round_index, is_free_rider=label, field=field,
                    clients=len(selected), finite=len(values), undefined=len(selected)-len(values),
                    mean=float(np.mean(values)) if values else None,
                    q1=quantiles[0], median=quantiles[1], q3=quantiles[2]))
    return result


def save(out, name, rows):
    atomic_write_text(out / "generated/visuals" / name, io.csv_text(rows, delimiter=" "))


def figure_start(columns, rows, height="4.8cm", width="0.455\\textwidth", vertical="1.2cm"):
    return [r"\begin{figure*}[tp]\centering", r"\begin{tikzpicture}",
        rf"\begin{{groupplot}}[group style={{group size={columns} by {rows},horizontal sep=0.8cm,vertical sep={vertical}}},",
        rf"width={width},height={height},",
        r"axis line style={black!35},grid=major,grid style={black!8},",
        r"tick label style={font=\scriptsize},title style={font=\small},",
        r"label style={font=\scriptsize},legend style={font=\scriptsize,draw=none},",
        r"scaled ticks=false,unbounded coords=jump]"]


def finish(lines, caption, label, legend=None):
    lines += [r"\end{groupplot}\end{tikzpicture}"]
    if legend:
        lines.append(rf"\par\ref{{{legend}}}")
    lines += [rf"\caption{{{caption}}}\label{{{label}}}", r"\end{figure*}"]
    return "\n".join(lines) + "\n"


def scatter_figure(dataset, share, points_by_run, out):
    lines = figure_start(2, 4, height="4.6cm", vertical="1.25cm")
    legend = f"scatter-{dataset}-{share}-legend"
    omitted = 0
    for split in ("iid", "noniid"):
        for attack in ("FR1", "FR2", "FR3", "FR4"):
            key = dataset, share, split, attack
            points = [p for p in points_by_run[key] if p["round"] == 20]
            valid = [p for p in points if p['norm_z'] is not None and p['profile_z'] is not None]
            omitted += len(points) - len(valid)
            first = split == "iid" and attack == "FR1"
            axis_labels = (r",xlabel={$\operatorname{asinh}(\bar z_{\rm norm})$}"
                           if split == 'noniid' and attack in ('FR3','FR4') else '')
            if attack in ('FR1','FR3'):
                axis_labels += r",ylabel={$\operatorname{asinh}(\bar z_{\rm profile})$}"
            lines.append(r"\nextgroupplot[title={" + ("IID" if split == "iid" else "Non-IID") + " " + attack + "},"
                + axis_labels.lstrip(',')
                + (f",legend to name={legend},legend columns=2" if first else "") + "]")
            for label, color in enumerate(COLORS):
                rows = [dict(x=math.asinh(p['norm_z']), y=math.asinh(p['profile_z'])) for p in valid if p['is_free_rider'] == label]
                name = f"scatter_{dataset}_{share}_{split}_{attack}_{label}.dat"
                # NaN yields a genuinely empty series, not a fabricated zero.
                save(out, name, rows or [dict(x="nan", y="nan")])
                marker = "o" if not label else "triangle*"
                lines.append(rf"\addplot[only marks,mark={marker},mark size=1.65pt,color={color},opacity=0.7] table[x=x,y=y] {{generated/visuals/{name}}};")
                if first:
                    lines.append(r"\addlegendentry{" + ("Honest" if not label else "Free rider") + "}")
    name = "MNIST" if dataset == "mnist" else "CIFAR-10"
    return finish(lines,
        f"{name}: round-20 score geometry at {share}\\% free riders (all eight settings). One point is one client, averaging the A/B norm-z and profile-z scores separately. The monotone asinh display compresses extreme tails without clipping; zero remains zero, but distances are transformed. Panels autoscale independently. Labels color evaluation only, never references or decisions. {omitted} points have undefined coordinates and are omitted; coincident points overlap. No plotted line is a removal cutoff.",
        f"fig:scatter-{dataset}-{share}", legend)


def histograms(signals, decisions, out):
    lines = figure_start(2, 3, "4.8cm", "0.455\\textwidth", "1.8cm")
    legend = "norm-hist-legend"
    for share, rounds in ((40, (20, 30, 60)), (30, (20, 40, 80))):
        key = "cifar10", share, "noniid", "FR3"
        for round_index in rounds:
            rows = [r for r in signals[key] if int(r['round']) == round_index and int(r['trap_id']) == 0 and finite(r.get('delta_norm')) is not None]
            raw = [float(r['delta_norm']) for r in rows]
            edges = np.histogram_bin_edges(raw, bins=math.ceil(math.sqrt(len(raw)))) if raw else np.linspace(0, 1, 11)
            current = [r for r in decisions[key] if int(r['round']) == round_index]
            counts = [sum(int(r['is_free_rider']) == label and 'norm_low' in r['strong_channels'].split(',') for r in current) for label in (0, 1)]
            first = share == 40 and round_index == 20
            ticks = ','.join(f'{value:.5f}' for value in np.linspace(edges[0], edges[-1], 4))
            lines.append(r"\nextgroupplot[title={" + f"{share}\\%, round {round_index}" + r"},xlabel={Raw update norm, trap A},ylabel={Clients},ymin=0,"
                + "xtick={" + ticks + r"},xticklabel style={/pgf/number format/fixed,/pgf/number format/precision=1},"
                + r"extra description/.code={\node[anchor=north east,font=\scriptsize,align=right] at (rel axis cs:0.98,0.96) {Paired norm cert.\\H: "
                + str(counts[0]) + ", FR: " + str(counts[1]) + r"};}"
                + (f",legend to name={legend},legend columns=2" if first else "") + "]")
            for label, color in enumerate(COLORS):
                values = [float(r['delta_norm']) for r in rows if int(r['is_free_rider']) == label]
                heights, _ = np.histogram(values, bins=edges)
                name = f"hist_{share}_{round_index}_{label}.dat"
                save(out, name, [dict(x=x, y=int(y)) for x, y in zip(edges, list(heights)+[0])])
                lines.append(rf"\addplot[const plot,fill={color},draw={color},fill opacity=0.24,thick] table[x=x,y=y] {{generated/visuals/{name}}} \closedcycle;")
                if first:
                    lines.append(r"\addlegendentry{" + ("Honest" if not label else "Free rider") + "}")
    return finish(lines,
        "CIFAR-10 non-IID FR3: raw selected trap-A norm distributions. Shared population-derived equal-width bins within each panel, independent axes across panels; colors may overlap. Annotations count FRESH norm certificates on BOTH traps (H: honest, FR: free rider). Confirming cycles are 20/60 at 40\\% and 40/80 at 30\\%; the other panels show ambiguity. A visual gap alone cannot authorize removal.",
        "fig:norm-hist", legend)


def score_trends(summaries, out):
    lines = figure_start(2, 2, "5.2cm", "0.455\\textwidth", "1.8cm")
    legend = "score-trend-legend"
    for field in ("norm_z", "profile_z"):
        for share in (40, 30):
            first = field == "norm_z" and share == 40
            ylabel = r"Mean paired norm-z" if field == "norm_z" else r"Mean paired profile-z"
            lines.append(r"\nextgroupplot[title={" + f"CIFAR-10 non-IID FR3, {share}\\%" + "},"
                + rf"xlabel={{Decision round}},ylabel={{{ylabel}}},xmin=18,xmax=82,xtick={{20,40,60,80}}"
                + (f",legend to name={legend},legend columns=2" if first else "") + "]")
            for label, color in enumerate(COLORS):
                rows = [r for r in summaries if (r['dataset'], r['share'], r['split'], r['attack'], r['field'], r['is_free_rider']) ==
                        ('cifar10', share, 'noniid', 'FR3', field, label) and r['finite'] and r['round'] <= 80]
                name = f"trend_{field}_{share}_{label}.dat"
                save(out, name, [dict(round=r['round'], mean=r['mean'], q1=r['q1'], q3=r['q3']) for r in rows]
                     or [dict(round=20, mean='nan', q1='nan', q3='nan')])
                lines += [rf"\addplot[name path=lower{label},draw=none,forget plot] table[x=round,y=q1] {{generated/visuals/{name}}};",
                          rf"\addplot[name path=upper{label},draw=none,forget plot] table[x=round,y=q3] {{generated/visuals/{name}}};",
                          rf"\addplot[fill={color},fill opacity=0.13,draw=none,forget plot] fill between[of=lower{label} and upper{label}];",
                          rf"\addplot[color={color},thick,mark={'o' if not label else 'triangle*'},mark size=2pt] table[x=round,y=mean] {{generated/visuals/{name}}};"]
                if first:
                    lines.append(r"\addlegendentry{" + ("Honest mean" if not label else "Free-rider mean") + "}")
    return finish(lines,
        "CIFAR-10 non-IID FR3: mean paired scores over complete evidence cycles through round 80 (lines), with client interquartile intervals shaded. Scores are first averaged over A/B per client. Bands show client dispersion, NOT mean uncertainty. References/MAD scales change each cycle; z-score changes need not match raw-norm changes. Free-rider curves stop at removal, never zero-filled. Class colors are for evaluation only.",
        "fig:score-trends", legend)


def resource_comparison(root, records, out):
    """Matched-setting historical observations, explicitly not causal profiling."""
    rows, provenance = [], []
    for attack in ('FR2', 'FR3', 'FR4'):
        run = root / f'results/v15_3_cifar10_seed42_fr40/v15_3_cifar10_noniid_{attack}_seed42'
        if not (run / 'latest_results.json').is_file():
            continue
        marker = io.read_json(run / 'latest_results.json')
        if not marker.get('completed') or marker.get('latest_round') != 100:
            continue
        old = io.read_json(run / 'run_config.json')
        new = next(r for r in records if (r['dataset'], r['share'], r['split'], r['attack']) == ('cifar10', 40, 'noniid', attack))
        # Reject a misleading comparison if any named study setting differs.
        for key, expected in {**io.SETTING_VALUES, 'methodology_version': 'swtcp_v15_3',
                              'distribution': 'noniid', 'attack_type': attack, 'free_rider_pct': .4}.items():
            io.require(old.get(key) == expected, f'Historical comparison configuration mismatch: {run}/{key}')
        metrics = io.read_csv(run / 'global_metrics.csv')
        io.require(old.get('device_resolved') == 'cpu', 'Historical comparison is not CPU')
        io.require(len(metrics) == 100 and [int(r['round']) for r in metrics] == list(range(1, 101)), 'Incomplete historical timings')
        rows.append(dict(attack=attack, old_round=float(np.mean([float(r['round_time_seconds']) for r in metrics])),
            new_round=new['mean_round_seconds'], old_peak=old['peak_process_rss_mb']/1024,
            new_peak=new['peak_process_mib']/1024, old_minutes=old['total_wall_clock_seconds']/60,
            new_minutes=new['wall_seconds']/60))
        provenance.append({str((run/name).relative_to(root)): io.digest(run/name)
                           for name in ('latest_results.json', 'run_config.json', 'global_metrics.csv')})
    body = [r'\begin{table*}[t]\centering\footnotesize',
        r'\caption{Historical whole-process comparison: CIFAR-10, non-IID, 40\%, seed 42, CPU, 100 rounds. Only completed matching v15.3 runs are included.}\label{tab:historical-cost}',
        r'\begin{tabular}{lrrrrrr}\toprule',
        r' & \multicolumn{2}{c}{Mean s/round} & \multicolumn{2}{c}{Peak RSS (GiB)} & \multicolumn{2}{c}{Execution (min)} \\',
        r'Attack & v15.3 & v15.4 & v15.3 & v15.4 & v15.3 & v15.4 \\ \midrule']
    for row in rows:
        body.append(row['attack'] + ' & ' + ' & '.join(f'{row[k]:.2f}' for k in
            ('old_round','new_round','old_peak','new_peak','old_minutes','new_minutes')) + r' \\')
    if not rows:
        body.append(r'\multicolumn{7}{c}{No completed matching historical runs available.} \\')
    body += [r'\bottomrule\end{tabular}',
        r'\par\smallskip\begin{minipage}{0.96\textwidth}\scriptsize The unfinished v15.3 FR1 is not reconstructed. Different trajectories, machine load and restarts confound causal overhead claims. These are not isolated detector benchmarks.\end{minipage}\end{table*}']
    atomic_write_text(out/'generated/historical_cost.tex', '\n'.join(body)+'\n')
    if rows:
        atomic_write_text(out/'generated/historical_cost.csv', io.csv_text(rows))
    return provenance


def model_resources(out):
    from models.architectures import get_model
    values = []
    for dataset in ('mnist', 'cifar10'):
        model = get_model(dataset)
        floats = [tensor for tensor in model.state_dict().values() if tensor.is_floating_point()]
        p, layers, n, b = sum(t.numel() for t in floats), len(floats), 100, 1000
        values.append(dict(dataset=dataset, parameters=sum(t.numel() for t in model.parameters()),
            float_coordinates=p, profile_tensors=layers, two_trap_mib=2*4*p/2**20,
            compact_pair_kib=2*n*(layers+3)*4/1024,
            bootstrap_index_mib=b*n*8/2**20, bootstrap_counts_mib=b*math.ceil(math.sqrt(n))*8/2**20,
            loo_profile_coordinate_visits=2*n*(n-1)*layers))
    lines = [r'\begin{table*}[t]\centering\footnotesize',
        r'\caption{Calculated detector payload sizes at $N=100$, two traps, $B=1000$: architecture-derived estimates, NOT measured heap usage.}\label{tab:payload}',
        r'\begin{tabular}{lrrrrrrr}\toprule',
        r'Model & Parameters & $P$ & $L$ & Two traps (MiB) & Pair payload (KiB) & Index array (MiB) & Counts (MiB) \\ \midrule']
    for r in values:
        lines.append(('MNIST' if r['dataset']=='mnist' else 'CIFAR-10') + ' & ' +
            ' & '.join(str(r[k]) for k in ('parameters','float_coordinates','profile_tensors')) + ' & ' +
            ' & '.join(f'{r[k]:.3f}' for k in ('two_trap_mib','compact_pair_kib','bootstrap_index_mib','bootstrap_counts_mib')) + r' \\')
    lines += [r'\bottomrule\end{tabular}',
        r'\par\smallskip\begin{minipage}{0.96\textwidth}\scriptsize $P$ includes floating BatchNorm buffers; $L$ counts floating tensors. Pair payload assumes packed float32 profiles plus three scalar slots per trap/client. Bootstrap columns show two principal arrays, not peak scratch or an upper bound. No detector-only RSS was recorded.\end{minipage}\end{table*}']
    atomic_write_text(out/'generated/model_payload.tex', '\n'.join(lines)+'\n')
    atomic_write_text(out/'generated/model_payload.csv', io.csv_text(values))


def resource_figure(records, out):
    lines = figure_start(2, 2, '5.2cm', '0.455\\textwidth', '1.4cm')
    legend = 'resource-bars-legend'
    for field, ylabel, factor in (('mean_round_seconds', 'Mean seconds / round', 1),
                                  ('peak_process_mib', 'Peak process RSS (GiB)', 1/1024)):
        for dataset in ('mnist', 'cifar10'):
            first = field == 'mean_round_seconds' and dataset == 'mnist'
            lines.append(r'\nextgroupplot[title={' + ('MNIST' if dataset == 'mnist' else 'CIFAR-10') + r'},'
                + f'ylabel={{{ylabel}}},ymin=0,ybar,bar width=5pt,'
                + r'xtick={1,2,3,4},xticklabels={FR1,FR2,FR3,FR4},enlarge x limits=0.18'
                + (f',legend to name={legend},legend columns=4' if first else '') + ']')
            for (share, split), color in zip(((30,'iid'),(30,'noniid'),(40,'iid'),(40,'noniid')),
                                             ('honestblue','violet!75!black','teal!75!black','riderorange')):
                rows = [dict(attack=i, value=next(r[field]*factor for r in records if
                    (r['dataset'],r['share'],r['split'],r['attack']) == (dataset,share,split,attack)))
                    for i, attack in enumerate(('FR1','FR2','FR3','FR4'), 1)]
                name = f'resource_{field}_{dataset}_{share}_{split}.dat'
                save(out, name, rows)
                lines.append(rf'\addplot[fill={color},fill opacity=0.8,draw={color}] table[x=attack,y=value] {{generated/visuals/{name}}};')
                if first:
                    lines.append(r'\addlegendentry{' + f'{share}\\% ' + ('IID' if split=='iid' else 'Non-IID') + '}')
    return finish(lines,
        'Attack-specific whole-simulator resource profiles for all 32 runs: mean logged round time (top) and peak process RSS (bottom). Four bars per attack distinguish partition and free-rider share. Dataset panels use independent numeric scales. FR3/FR4 memory includes simulated history storage; these bars do not measure detector-only overhead.',
        'fig:resources', legend)


def build(paths, records, out):
    signals, decisions, points, summaries = {}, {}, {}, []
    for key, run in paths.items():
        signals[key] = io.read_csv(run/'cycle_signals.csv')
        decisions[key] = io.read_csv(run/'cycle_decisions.csv')
        points[key] = paired_scores(signals[key])
        metadata = dict(zip(('dataset','share','split','attack'), key))
        summaries.extend(summarize(points[key], metadata))
    for share in (30, 40):
        for dataset in ('mnist','cifar10'):
            atomic_write_text(out/f'generated/scatter_{dataset}_{share}.tex', scatter_figure(dataset, share, points, out))
    atomic_write_text(out/'generated/norm_histograms.tex', histograms(signals, decisions, out))
    atomic_write_text(out/'generated/score_trends.tex', score_trends(summaries, out))
    atomic_write_text(out/'generated/resource_figure.tex', resource_figure(records, out))
    atomic_write_text(out/'generated/score_statistics.csv', io.csv_text(summaries))
    # Keep source coordinates so every point can be inspected without inverse transforms.
    coordinates = [dict(zip(('dataset','share','split','attack'), key), **point)
                   for key, values in points.items() for point in values]
    atomic_write_text(out/'generated/paired_score_coordinates.csv', io.csv_text(coordinates))
    root = next(iter(paths.values())).parents[2]
    provenance = resource_comparison(root, records, out)
    model_resources(out)
    atomic_write_json(out/'generated/visual_provenance.json', dict(
        paired_scores='arithmetic mean of selected A/B scores, complete pairs only',
        scatter_transform='asinh, visualization only; no clipping or jitter',
        histograms='raw trap-A norms, shared population bins ceil(sqrt(N)) per panel',
        labels='evaluation color/group summaries only; never used for decisions',
        historical_inputs=provenance,
        architecture_sha256=io.digest(io.ROOT/'models/architectures.py')))
