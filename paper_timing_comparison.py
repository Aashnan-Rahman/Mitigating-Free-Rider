"""Measured timing comparisons; never invent segments absent from old logs.

Only reporting artifacts are written. Native simulation inputs and frozen detector
code are read-only. STD-DAGMM has component timers; v15.4 has whole-round timers.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import shutil
import statistics
import subprocess
from collections import defaultdict
from pathlib import Path

from atomic_io import atomic_write_json, atomic_write_text

ROOT = Path(__file__).resolve().parent
PAPER = ROOT/'result_check/paper_version_staging/versions/v06_v15_4_full_study'
PHASES = ('warmup', 'probe', 'full_cycle', 'single_audit', 'ordinary')
PHASE_NAMES = ('Warm-up', 'Probe without cycle decision', 'Full-cycle decision', 'Single audit', 'Ordinary')
STD_SEGMENTS = (
    ('honest_training_seconds', 'Client training', 'blue!65!black'),
    ('fabrication_seconds', 'Simulated FR response', 'cyan!65!black'),
    ('aggregation_seconds', 'Server aggregation', 'teal!75!black'),
    ('evaluation_seconds', 'Global evaluation', 'yellow!70!orange'),
    ('preparation_seconds', 'Update preparation', 'violet!70'),
    ('fit_seconds', 'Detector fitting', 'riderorange'),
    ('score_decision_seconds', 'Scoring + flag decision', 'red!70!black'),
    ('unsegmented_seconds', 'Ours: undivided round total', 'black!45'),
)


def rows(path):
    with path.open(newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def csv_text(values, delimiter=','):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(values[0]), delimiter=delimiter, lineterminator='\n')
    writer.writeheader()
    writer.writerows(values)
    return stream.getvalue()


def validate_rounds(values, expected):
    if [int(row['round']) for row in values] != list(range(1, expected+1)):
        raise ValueError('Incomplete, duplicate or out-of-order timing rounds')


def phase_summary(metrics, decision_rounds):
    """Group TOTAL round costs by events, not estimated costs of those events."""
    buckets = defaultdict(list)
    for row in metrics:
        r, phase = int(row['round']), row['phase']
        kind = ('warmup' if phase == 'warmup' else 'full_cycle' if r in decision_rounds
                else 'single_audit' if phase == 'single_audit'
                else 'probe' if phase in ('double_probe', 'confirmation') else 'ordinary')
        value = float(row['round_time_seconds'])
        if not math.isfinite(value) or value < 0:
            raise ValueError('Invalid measured round duration')
        buckets[kind].append(value)
    return [dict(phase=kind, rounds=len(buckets[kind]), total_s=sum(buckets[kind]),
                 mean_within_phase_s=statistics.mean(buckets[kind]) if buckets[kind] else None,
                 amortized_s=sum(buckets[kind])/len(metrics)) for kind in PHASES]


def gather(root):
    data, provenance = {}, {}
    long_paths={d:root/f'results/std_dagmm_100_seed42_fr40/std_dagmm_{d}_noniid_FR3_seed42' for d in ('mnist','cifar10')}
    for dataset in ('mnist', 'cifar10'):
        std = long_paths[dataset]
        ours = root/f'results/v15_4_{dataset}_seed42_fr40/v15_4_{dataset}_noniid_FR3_seed42'
        status = json.loads((std/'status.json').read_text())
        report = json.loads((std/'summary.json').read_text())
        marker = json.loads((ours/'latest_results.json').read_text())
        cfg = report['protocol']['config']
        old_cfg = json.loads((ours/'run_config.json').read_text())
        expected=100
        if status['state'] != 'completed' or report['state'] != 'completed' or report['completed_rounds'] != expected or cfg['num_rounds']!=expected or not marker.get('completed') or marker['latest_round'] != 100:
            raise ValueError('Timing comparison requires completed matching horizons')
        for key, value in dict(dataset=dataset, distribution='noniid', seed=42,
                               num_clients=100, attack_type='FR3', free_rider_pct=.4,
                               local_epochs=3, batch_size=32, learning_rate=.01, momentum=.9,
                               dirichlet_alpha=.5).items():
            if cfg[key] != value or old_cfg[key] != value:
                raise ValueError(f'Unexpected timing-comparison scenario: {key}')
        for source, digest in report['protocol']['source_sha256'].items():
            if hashlib.sha256((root/source).read_bytes()).hexdigest() != digest:
                raise ValueError(f'STD implementation changed: {source}')
        native, historical = rows(std/'round_timings.csv'), rows(ours/'global_metrics.csv')
        validate_rounds(native, expected)
        validate_rounds(historical, 100)
        for row in native:
            if int(row['active_clients']) != 100 or int(row['permanent_removals']) != 0:
                raise ValueError('STD fixed-client workload changed')
            components = sum(float(row[k]) for k in ('honest_training_seconds', 'fabrication_seconds',
                'aggregation_seconds', 'evaluation_seconds', 'preparation_seconds', 'fit_seconds',
                'inference_seconds', 'decision_seconds'))
            if not math.isclose(components, float(row['round_compute_seconds']), rel_tol=1e-9):
                raise ValueError('STD segments do not sum to measured compute')
        decisions = {int(row['round']) for row in rows(ours/'cycle_decisions.csv')}
        phases = phase_summary(historical, decisions)
        if not math.isclose(sum(p['amortized_s'] for p in phases),
                            statistics.mean(float(r['round_time_seconds']) for r in historical)):
            raise ValueError('Amortized phase costs fail to reconcile')
        data[dataset] = dict(std=native, ours=historical, phases=phases, decision_rounds=decisions,
            std_report=report,std_measured_rounds=expected)
        for directory, names in ((std, ('status.json','summary.json','protocol.json','round_timings.csv')),
                                  (ours, ('latest_results.json','run_config.json','global_metrics.csv','cycle_decisions.csv'))):
            for name in names:
                path = directory/name
                provenance[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return data, provenance


def figures_start(columns=2, height='6.2cm', plot_rows=1):
    vertical_sep = '2.3cm' if plot_rows > 1 else '1.6cm'
    return [r'\begin{figure*}[tp]\centering\begin{tikzpicture}',
        rf'\begin{{groupplot}}[group style={{group size={columns} by {plot_rows},horizontal sep=1.6cm,vertical sep={vertical_sep}}},',
        rf'width=0.43\textwidth,height={height},',
        r'grid=major,grid style={black!8},axis line style={black!35},',
        r'tick label style={font=\scriptsize},label style={font=\small},title style={font=\small},',
        r'legend style={font=\scriptsize,draw=none},scaled y ticks=false]']


def finish(lines, caption, label, legend=None):
    return '\n'.join(lines+[r'\end{groupplot}\end{tikzpicture}',
        *([rf'\par\ref{{{legend}}}'] if legend else []),
        rf'\caption{{{caption}}}\label{{{label}}}',r'\end{figure*}'])+'\n'


def phase_panels(name, phases):
    """Separate event cost from event frequency; never label either detector CPU."""
    lines = []
    ticks = ','.join(rf'{{{title}\\$n={item["rounds"]}$}}' for title, item in zip(
        ('Warm-up', 'Probe', 'Cycle', 'Audit', 'Ordinary'), phases))
    colors = ('black!45', 'blue!60!black', 'riderorange', 'violet!65', 'teal!65!black')
    total = sum(item['amortized_s'] for item in phases)
    for key, title, ylabel in (
            ('mean_within_phase_s', f'{name}: cost of one category round', 'Mean seconds within category'),
            ('amortized_s', f'{name}: contribution to {total:.2f} s/round', 'Seconds per full-run round')):
        maximum = max((item[key] or 0.) for item in phases)
        lines.append(r'\nextgroupplot[title={'+title+r'},ybar,bar width=22pt,bar shift=0pt,'
            +rf'ymin=0,ymax={max(maximum * 1.22, 1.):.6f},xmin=0.4,xmax=5.6,'
            +r'ylabel={'+ylabel+r'},xtick={1,2,3,4,5},xticklabels={'+ticks+r'},'
            +r'xticklabel style={align=center,font=\scriptsize},xmajorgrids=false,'
            +r'axis x line*=bottom,axis y line*=left,nodes near coords,'
            +r'every node near coord/.append style={font=\scriptsize,text=black,'
            +r'/pgf/number format/fixed,/pgf/number format/precision=2,/pgf/number format/fixed zerofill}]')
        for index, (item, color) in enumerate(zip(phases, colors), start=1):
            if item[key] is not None:
                lines.append(rf'\addplot[fill={color},draw=none,bar shift=0pt] coordinates {{({index},{item[key]:.9f})}};')
    return lines


def build(root=ROOT, out=PAPER):
    generated = out/'generated'
    full_needed=[root/f'results/std_dagmm_100_seed42_fr40/std_dagmm_{d}_noniid_FR3_seed42/summary.json' for d in ('mnist','cifar10')]
    if not all(path.is_file() for path in full_needed):
        atomic_write_text(generated/'timing_comparison.tex', '% Completed 100-round timing evidence unavailable in this evidence root.\n')
        return None
    data, provenance = gather(root)
    target = generated/'timing'
    all_components, all_phases, totals, timeline = [], [], [], []
    segment_plot, phase_plot, trace_plot = figures_start(), figures_start(height='5.5cm', plot_rows=2), figures_start(height='6.4cm')
    for dataset, group in data.items():
        name = 'MNIST' if dataset == 'mnist' else 'CIFAR-10'
        native, historical = group['std'], group['ours']
        first = dataset == 'mnist'
        mean_std = {k: statistics.mean(float(r[k]) for r in native) for k, _, _ in STD_SEGMENTS[:-2]}
        mean_std['score_decision_seconds'] = statistics.mean(float(r['inference_seconds'])+float(r['decision_seconds']) for r in native)
        mean_std['unsegmented_seconds'] = 0.
        mean_ours100 = statistics.mean(float(r['round_time_seconds']) for r in historical)
        for key, title, _ in STD_SEGMENTS[:-1]:
            all_components.append(dict(dataset=dataset, method='STD-DAGMM', segment=key, description=title,
                mean_s=mean_std[key], measured_rounds=len(native),
                actual_total_s=len(native)*mean_std[key],measurement='100 measured rounds'))
        columns = []
        for x, value, method in ((1,mean_ours100,'ours_100'),(2,None,'std_100')):
            entry = dict(x=x)
            entry.update({k:(mean_std[k] if value is None else value if k=='unsegmented_seconds' else 0.) for k,_,_ in STD_SEGMENTS})
            columns.append(entry)
            totals.append(dict(dataset=dataset, method=method, rounds=100,
                evidence='measured', mean_s=sum(entry[k] for k,_,_ in STD_SEGMENTS),
                summed_s=100*sum(entry[k] for k,_,_ in STD_SEGMENTS)))
        atomic_write_text(target/f'segments_{dataset}.dat', csv_text(columns, ' '))
        segment_plot.append(r'\nextgroupplot[title={'+name+r': 100 measured rounds},ybar stacked,bar width=32pt,ymin=0,ylabel={Mean seconds per round},'
            +r'xtick={1,2},xticklabels={Ours,STD-DAGMM},enlarge x limits=0.7'
            +(r',legend to name=timing-segments-legend,legend columns=3' if first else '')+']')
        for key, title, color in STD_SEGMENTS:
            segment_plot.append(rf'\addplot[fill={color},draw=white] table[x=x,y={key}] {{\TimingDataDir/segments_{dataset}.dat}};')
            if first:
                segment_plot.append(rf'\addlegendentry{{{title}}}')
        phase_values = []
        for index, item in enumerate(group['phases'], start=1):
            all_phases.append(dict(dataset=dataset, **item))
            phase_values.append(dict(x=index, **item))
        atomic_write_text(target/f'phases_{dataset}.dat', csv_text(phase_values, ' '))
        phase_plot.extend(phase_panels(name, group['phases']))
        trace = [dict(round=int(r['round']), seconds=float(r['round_time_seconds']),
                      active_start=int(r['num_active_clients'])+int(r['new_removals'])) for r in historical]
        timeline.extend(dict(dataset=dataset, **row) for row in trace)
        atomic_write_text(target/f'timeline_{dataset}.dat', csv_text(trace,' '))
        atomic_write_text(target/f'std_rounds_{dataset}.dat', csv_text([
            dict(round=int(r['round']),seconds=float(r['round_compute_seconds'])) for r in native],' '))
        atomic_write_text(target/f'cycle_rounds_{dataset}.dat',csv_text([
            row for row in trace if row['round'] in group['decision_rounds']] or [dict(round='nan',seconds='nan',active_start='nan')],' '))
        trace_plot.append(r'\nextgroupplot[title={'+name+r'},xmin=0,xmax=101,ymin=0,xlabel={Round},ylabel={Measured seconds},'
            +r'xtick={1,20,40,60,80,100}'
            +(r',legend to name=timing-trace-legend,legend columns=3' if first else '')+']')
        for style, file, title in ((r'black!65,thick',f'timeline_{dataset}', 'Ours: actual 100 rounds'),
                (r'only marks,mark=*,mark size=2pt,color=riderorange',f'cycle_rounds_{dataset}', 'Full-cycle decision rounds'),
                (r'blue!70!black,thick',f'std_rounds_{dataset}', f'STD: actual rounds 1--{len(native)}')):
            trace_plot.append(rf'\addplot[{style}] table[x=round,y=seconds] {{\TimingDataDir/{file}.dat}};')
            if first:
                trace_plot.append(rf'\addlegendentry{{{title}}}')
    segments = finish(segment_plot,
        r'Mean timing over 100 executed rounds per method and dataset: non-IID FR3, seed 42, 100 initial clients, 40\% free riders. STD-DAGMM has measured task components; our gray bars are undivided whole-round totals, not zero-cost detection. Both means include rounds 1--100. Different trajectories, timer coverage and host load prevent a causal speedup claim.',
        'fig:timing-segments','timing-segments-legend')
    phases = finish(phase_plot,
        r'Where our 100-round runtime is spent (non-IID FR3, seed 42, 40\% free riders). Rows separate MNIST and CIFAR-10. Left: mean duration of a complete round in each category. Right: summed duration for that category divided by 100; the five bars add to the full-run mean printed in the title. Labels give category counts $n$. Probe excludes cycle-decision rounds; Cycle includes the final cycle decision; Audit is a single audit round. Categories are mutually exclusive. A cycle bar includes client training, aggregation and evaluation: it is NOT detector-only time. Axes scale independently; all bars start at zero.',
        'fig:timing-phases')
    traces = finish(trace_plot,
        'Actual per-round durations over 100 executed rounds for both methods. Our trajectories include changing active-client counts and probing schedules; STD-DAGMM retains all 100 clients. Markers indicate full-cycle decisions, not their isolated computational cost. Axis scales differ by dataset.',
        'fig:timing-traces','timing-trace-legend')
    for name, text in (('timing_segments_figure.tex',segments),('timing_phases_figure.tex',phases),('timing_timeline_figure.tex',traces)):
        atomic_write_text(generated/name,text)
    for filename, values in (('segments.csv',all_components),('phases.csv',all_phases),('totals.csv',totals),('ours_rounds.csv',timeline)):
        atomic_write_text(target/filename,csv_text(values))
    tables = make_tables(data,totals,all_phases)
    atomic_write_text(generated/'timing_tables.tex',tables)
    atomic_write_text(generated/'timing_comparison.tex',r'''\providecommand{\TimingDataDir}{generated/timing}
\input{generated/timing_tables.tex}
\input{generated/timing_segments_figure.tex}
\input{generated/timing_phases_figure.tex}
\input{generated/timing_timeline_figure.tex}
''')
    atomic_write_json(target/'provenance.json',dict(inputs=provenance,
        ours_components='not recorded; total only',communication='no network experiment',
        horizon='ours and STD: 100 actual measured rounds',
        formulas=dict(amortized_phase='sum(round durations in phase) / 100',
                      std='sum of actual 100 round durations')))
    return dict(totals=totals,phases=all_phases,data=data)


def make_tables(data, totals, phases):
    lines=[r'\begin{table*}[t]\centering\footnotesize',
        rf'\caption{{Measured STD-DAGMM component times (seconds per round, mean $\pm$ sample SD, {len(data["mnist"]["std"])} rounds per dataset).}}\label{{tab:std-segments}}',
        r'\begin{tabular}{lrr}\toprule Component & MNIST & CIFAR-10 \\ \midrule']
    for key,title in ((k,t) for k,t,_ in STD_SEGMENTS[:-2]):
        cells=[]
        for group in data.values():
            v=[float(r[key]) for r in group['std']]
            cells.append(f'{statistics.mean(v):.3f} $\\pm$ {statistics.stdev(v):.3f}')
        lines.append(title+' & '+' & '.join(cells)+r' \\')
    for key,title in (('inference_seconds','Detector scoring'),('decision_seconds','Flag decision'),('detector_seconds','All detector work'),('round_compute_seconds','Combined compute')):
        cells=[]
        for group in data.values():
            v=[float(r[key]) for r in group['std']]
            cells.append(f'{statistics.mean(v):.3f} $\\pm$ {statistics.stdev(v):.3f}')
        lines.append(title+' & '+' & '.join(cells)+r' \\')
    lines += [r'\bottomrule\end{tabular}',r'\par\smallskip\begin{minipage}{0.96\textwidth}\scriptsize Our historical training, aggregation, detection and trap-generation components: not separately recorded. Network transmission: not measured in either local simulator. STD has no traps. All detector work includes preparation, fitting, scoring and decisions; it overlaps those table rows and must not be added a second time.\end{minipage}\end{table*}',
        r'\begin{table*}[t]\centering\footnotesize',
        r'\caption{Native-workflow timing over 100 executed rounds per method and dataset. All entries are measured; this is not a controlled speedup experiment.}\label{tab:timing-horizons}',
        r'\begin{tabular}{llrrr}\toprule Dataset & Workflow / horizon & Rounds & Mean s/round & Sum (min) \\ \midrule']
    names={'ours_100':'Ours, measured full horizon','std_100':'STD-DAGMM, measured full horizon'}
    for r in totals:
        lines.append(('MNIST' if r['dataset']=='mnist' else 'CIFAR-10')+' & '+names[r['method']]+f" & {r['rounds']} & {r['mean_s']:.2f} & {r['summed_s']/60:.2f}"+r' \\')
    lines += [r'\bottomrule\end{tabular}\end{table*}',r'\begin{table*}[t]\centering\footnotesize',
        r'\caption{Our 100 measured rounds grouped by events. Within-category mean is not detector-only overhead; amortized contribution is category sum / 100.}\label{tab:timing-phases}',
        r'\begin{tabular}{llrrr}\toprule Dataset & Round category & Count & Within-category mean (s) & Contribution (s/round) \\ \midrule']
    for r in phases:
        avg='---' if r['mean_within_phase_s'] is None else f"{r['mean_within_phase_s']:.2f}"
        lines.append(('MNIST' if r['dataset']=='mnist' else 'CIFAR-10')+' & '+PHASE_NAMES[PHASES.index(r['phase'])]+f" & {r['rounds']} & {avg} & {r['amortized_s']:.2f}"+r' \\')
    lines += [r'\bottomrule\end{tabular}\end{table*}']
    return '\n'.join(lines)+'\n'


def standalone(root=ROOT,out=PAPER):
    result=build(root,out)
    if result is None:
        raise ValueError('Missing native timing evidence')
    folder=root/'analysis/timing_breakdown'
    relative=Path(__import__('os').path.relpath(out,folder)).as_posix()
    head=r'''\documentclass[11pt,a4paper]{article}
\usepackage[margin=1.8cm]{geometry}
\usepackage{booktabs,pgfplots,placeins}
\usepackage[hidelinks]{hyperref}
\usepgfplotslibrary{groupplots}
\pgfplotsset{compat=1.18}
\definecolor{riderorange}{HTML}{D66B27}
\title{MNIST and CIFAR-10: native-workflow timing comparison}
\author{}\date{20 October 2026}
\makeatletter\setlength{\@fptop}{0pt}\makeatother
'''
    body=(rf'\newcommand{{\TimingDataDir}}{{{relative}/generated/timing}}'+'\n'+r'\begin{document}\maketitle'+'\n'+
        r'Non-IID, seed 42, 100 initial clients, 40\% FR3. Our v15.4 data: 100 completed rounds per dataset. STD-DAGMM: 100 completed rounds per dataset, five fresh fitting epochs each, no removals. These totals are measured, not projected. Components absent from historical logs are not estimated. Network communication was not measured. Different native trajectories, hardware load, local attacker evaluation and timer boundaries preclude a causal speedup comparison. The CIFAR detector encountered near-zero available RAM, so paging may affect its timings; paging was not measured.'+'\n')
    body+= (out/'generated/timing_tables.tex').read_text().replace('table*','table').replace('[t]','[!ht]')+'\n'+r'\FloatBarrier'+'\n'
    for name in ('timing_segments_figure.tex','timing_phases_figure.tex','timing_timeline_figure.tex'):
        body+=r'\clearpage'+'\n'+(out/'generated'/name).read_text().replace('figure*','figure').replace('[tp]','[!ht]')+'\n'+r'\FloatBarrier'+'\n'
    atomic_write_text(folder/'timing_report.tex',head+body+r'\end{document}'+'\n')
    for filename in ('segments.csv','phases.csv','totals.csv','ours_rounds.csv','provenance.json'):
        atomic_write_text(folder/filename,(out/'generated/timing'/filename).read_text())
    table=['| Dataset | Method/horizon | Mean s/round | Sum min |','|---|---|---:|---:|']
    for r in result['totals']:
        table.append(f"| {r['dataset']} | {r['method']} | {r['mean_s']:.2f} | {r['summed_s']/60:.2f} |")
    atomic_write_text(folder/'README.md','# Timing breakdown\n\n'+'\n'.join(table)+'''

See timing_report.pdf for enlarged vector charts and tables. Component CSVs,
100 actual round records, phase summaries and input hashes are saved alongside
this report and in the paper's generated/timing folder. Our gray totals cannot
be split retrospectively.
The phase figure separates within-category round cost (left) from its weighted
contribution to the full-run average (right); counts explain the difference.
These are whole-round categories, not isolated detector/trap costs.
STD's 100-round figures now use 100 actual measured rounds, not projections.
No network transfer was timed. No new experiment or detector change was made.
This is a native-workflow comparison, not a matched detector-only speedup test.
Removing non-training free riders need not reduce honest SGD jobs; a smaller
active population does not imply proportionally smaller client-training time.
''')
    return folder


def compile_report(folder):
    latex=shutil.which('pdflatex')
    if latex is None:
        raise RuntimeError('pdflatex unavailable; report sources remain saved')
    scratch=folder/'build'
    scratch.mkdir(exist_ok=True)
    command=[latex,'-interaction=nonstopmode','-halt-on-error','-no-shell-escape',
             '-output-directory=build','timing_report.tex']
    for _ in range(2):
        result=subprocess.run(command,cwd=folder,capture_output=True,text=True,errors='replace',timeout=180)
        atomic_write_text(scratch/'compile.txt',result.stdout+result.stderr)
        if result.returncode:
            raise RuntimeError('Timing PDF compilation failed; see build/compile.txt')
    shutil.copyfile(scratch/'timing_report.pdf',folder/'timing_report.pdf')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--standalone',action='store_true')
    parser.add_argument('--compile',action='store_true')
    args=parser.parse_args()
    if args.standalone:
        folder=standalone()
        if args.compile:
            compile_report(folder)
        print(folder)
    else:
        build()
