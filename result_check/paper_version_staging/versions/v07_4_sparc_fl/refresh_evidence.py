"""Refresh the completed-only review snapshot for v7.4 without editing prose.

Unlike prepare_revision.py, this never writes the manuscript. It re-reads the
registered review queue, keeps only completed 100-round runs, and regenerates
generated/saudi/{completed_runs.csv,snapshot.json,low_share_table.tex,
passive_table.tex}. No detector setting, plan, queue or checkpoint is changed.
"""
from pathlib import Path
import csv, hashlib, json
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = HERE / 'generated/saudi'


def read(p): return p.read_text(encoding='utf-8-sig')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p):
    with p.open(encoding='utf-8-sig', newline='') as h: return list(csv.DictReader(h))


provenance = []; inventory = []; queue = []
for pp in json.loads(read(ROOT / 'configs/review2_priority_queue.json'))['plans']:
    plan = json.loads(read(ROOT / pp)); batch = plan.get('batch_name', Path(pp).stem)
    sp = ROOT / 'results' / batch / 'experiment_status.json'
    status = json.loads(read(sp)) if sp.exists() else {}
    queue.append(dict(plan=pp, batch=batch, total=len(plan['experiments']),
                      completed=status.get('completed_experiments', 0),
                      state=status.get('state', 'queued'), current=status.get('current_experiment')))
    if sp.exists(): provenance.append(dict(path=str(sp.relative_to(ROOT)), sha256=sha(sp)))
    if not batch.startswith('review2_'): continue
    for e in status.get('experiments', []):
        if e['state'] != 'completed': continue
        d = sp.parent / e['id']; rp = d / 'run_config.json'; gp = d / 'global_metrics.csv'
        r = json.loads(read(rp)); metrics = rows(gp)
        assert len(metrics) == 100 and [int(x['round']) for x in metrics] == list(range(1, 101)), e['id']
        assert r['completed_rounds'] == 100
        c = e['config']
        inventory.append(dict(batch=batch, id=e['id'], dataset=c['dataset'], partition=c['distribution'],
            share=int(round(c['free_rider_pct'] * 100)), attack=c['attack_type'],
            removed=r['removed_free_riders'], honest_removed=r['removed_honest_clients'],
            missed=r['missed_free_riders'], accuracy=r['final_global_accuracy']))
        for f in [rp, gp]: provenance.append(dict(path=str(f.relative_to(ROOT)), sha256=sha(f)))

OUT.mkdir(exist_ok=True)
with (OUT / 'completed_runs.csv').open('w', newline='', encoding='utf-8') as h:
    w = csv.DictWriter(h, fieldnames=list(inventory[0])); w.writeheader(); w.writerows(inventory)
snapshot = dict(cutoff_utc=datetime.now(timezone.utc).isoformat(), queue=queue,
                completed_review_runs=len(inventory), inputs=provenance)
(OUT / 'snapshot.json').write_text(json.dumps(snapshot, indent=2) + '\n', encoding='utf-8')

# Lower-prevalence table: every completed cell; dashes only for incomplete runs.
low = [x for x in inventory if x['batch'] == 'review2_02_low_share_seed42']
L = [r'\begin{table}[t]\centering\footnotesize\setlength{\tabcolsep}{3pt}',
     r'\caption{Completed lower-prevalence checks.}\label{tab:low-share}',
     r'\begin{tabular}{llrrrrr}\toprule', r'Dataset & Split & FR (\%) & FR1 & FR2 & FR3 & FR4 \\ \midrule']
for ds in ['mnist', 'cifar10']:
    for split in ['noniid', 'iid']:
        for pct in [5, 10, 20]:
            cells = []
            for attack in ['FR1', 'FR2', 'FR3', 'FR4']:
                rs = [x for x in low if (x['dataset'], x['partition'], x['share'], x['attack']) == (ds, split, pct, attack)]
                cells.append((f"{rs[0]['removed']}/{pct}" + (r'$^{\dagger}$' if rs[0]['honest_removed'] else '')) if rs else '--')
            L.append(('MNIST' if ds == 'mnist' else 'CIFAR-10') + ' & ' + ('Non-IID' if split == 'noniid' else 'IID')
                     + f' & {pct} & ' + ' & '.join(cells) + r' \\')
        L.append(r'\midrule' if (ds, split) != ('cifar10', 'iid') else r'\bottomrule')
note = ('Dashes: incomplete or pending, not zero detections. ' if len(low) < 48 else '')
L += [r'\end{tabular}', r'\par\smallskip\parbox{\columnwidth}{\scriptsize Completed 100-round runs only, seed 42, 100 clients. '
      r'Entries: free riders removed / present. ' + note + r'$\dagger$ One honest removal; all other runs have none.}', r'\end{table}']
(OUT / 'low_share_table.tex').write_text('\n'.join(L) + '\n', encoding='utf-8')

# Passive ablation versus the matched seed-42, 40% runs of the main grid.
passive_dir = ROOT / 'results/review2_03_passive_seed42'
summary = json.loads(read(passive_dir / 'review_summary.json'))
mad = {m['id']: m for m in summary['mad_diagnostics']}
main = {(r['dataset'], r['split'], r['attack']): r for r in rows(HERE / 'generated/multiseed/per_run.csv')
        if r['share'] == '40' and r['seed'] == '42'}
P = [r'\begin{table*}[t]\centering\footnotesize\setlength{\tabcolsep}{4.5pt}',
     r'\caption{Ordinary versus challenge dispatch: matched seed-42 runs with 40\% free riders.}\label{tab:passive}',
     r'\begin{tabular}{llcccccc@{\hspace{10pt}}c}\toprule',
     r'& & \multicolumn{2}{c}{Completion round} & \multicolumn{2}{c}{Honest withheld (\%)} & \multicolumn{2}{c}{Final accuracy (\%)} & One-round \\',
     r'\cmidrule(lr){3-4}\cmidrule(lr){5-6}\cmidrule(lr){7-8}',
     r'Setting & Attack & Ordinary & Challenge & Ordinary & Challenge & Ordinary & Challenge & MAD screen \\ \midrule']
records = []
for ds in ['mnist', 'cifar10']:
    for split in ['iid', 'noniid']:
        for i, attack in enumerate(['FR1', 'FR2', 'FR3', 'FR4']):
            rid = f'passive_{ds}_{split}_{attack}_fr40_seed42'; d = passive_dir / rid
            r = json.loads(read(d / 'run_config.json'))
            assert r['completed_rounds'] == 100
            removal = rows(d / 'removals.csv')
            honest = [x for x in rows(d / 'client_metrics.csv') if x['is_free_rider'] == '0']
            withheld = 100 * sum(x['was_aggregated'] == '0' for x in honest) / len(honest)
            m = main[(ds, split, attack)]
            rec = dict(id=rid, dataset=ds, split=split, attack=attack,
                       passive_removed=r['removed_free_riders'], passive_honest_removed=r['removed_honest_clients'],
                       passive_completion=max(int(x['round']) for x in removal) if r['missed_free_riders'] == 0 else '',
                       passive_withheld_pct=round(withheld, 2), passive_accuracy=r['final_global_accuracy'],
                       trap_removed=int(m['tp']), trap_honest_removed=int(m['fp']),
                       trap_completion=int(m['completion_round']), trap_withheld_pct=round(float(m['honest_excluded_pct']), 2),
                       trap_accuracy=float(m['final_accuracy']), mad_tp=mad[rid]['tp'], mad_fp=mad[rid]['fp'],
                       trap_source=m['source'])
            records.append(rec)
            for f in ['run_config.json', 'removals.csv', 'client_metrics.csv']:
                provenance.append(dict(path=str((d / f).relative_to(ROOT)), sha256=sha(d / f)))
            label = ('MNIST' if ds == 'mnist' else 'CIFAR-10') + (' IID' if split == 'iid' else ' non-IID') if i == 0 else ''
            P.append(f"{label} & {attack} & {rec['passive_completion']} & {rec['trap_completion']} & "
                     f"{rec['passive_withheld_pct']:.1f} & {rec['trap_withheld_pct']:.1f} & "
                     f"{100*rec['passive_accuracy']:.2f} & {100*rec['trap_accuracy']:.2f} & {rec['mad_tp']}/40 " + r'\\')
        P.append(r'\midrule' if (ds, split) != ('cifar10', 'noniid') else r'\bottomrule')
assert all(r['passive_removed'] == r['trap_removed'] == 40 for r in records)
assert all(r['passive_honest_removed'] == r['trap_honest_removed'] == 0 for r in records)
P += [r'\end{tabular}', r'\par\smallskip\parbox{.96\textwidth}{\scriptsize Both dispatch modes remove all 40 free riders and no honest '
      r'client in every row. Ordinary dispatch keeps the audit schedule, response slots, statistics and confirmation rule, sends the '
      r'current global model and aggregates every non-quarantined response; it uses the engine with the corrected audit clock. Challenge '
      r'dispatch is the matched run of the main study. Withheld: active honest client-rounds not aggregated. One-round MAD screen: free '
      r'riders flagged by a lower-tail robust norm threshold ($\alpha=0.01$) on all ordinary round-20 responses; it flags no honest '
      r'client in any row.}', r'\end{table*}']
(OUT / 'passive_table.tex').write_text('\n'.join(P) + '\n', encoding='utf-8')
with (OUT / 'passive_comparison.csv').open('w', newline='', encoding='utf-8') as h:
    w = csv.DictWriter(h, fieldnames=list(records[0])); w.writeheader(); w.writerows(records)
snapshot['inputs'] = provenance
(OUT / 'snapshot.json').write_text(json.dumps(snapshot, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(cutoff=snapshot['cutoff_utc'], completed_review_runs=len(inventory), low_share=len(low),
                      passive=len(records), queue=[(q['batch'], q['completed'], q['total'], q['state']) for q in queue]), indent=1))

# Figure: honest withholding by dispatch mode (mean over FR1-FR4, range as whiskers).
F = [r'\begin{figure}[t]\centering\begin{tikzpicture}',
     r'\begin{axis}[ybar,width=\columnwidth,height=5cm,bar width=12pt,enlarge x limits=0.16,ymin=0,ymax=15,',
     r' ylabel={Honest client-rounds withheld (\%)},ylabel style={font=\footnotesize},',
     r' symbolic x coords={MI,MN,CI,CN},xtick=data,',
     r' xticklabels={{MNIST\\IID},{MNIST\\non-IID},{CIFAR-10\\IID},{CIFAR-10\\non-IID}},',
     r' xticklabel style={align=center,font=\footnotesize},yticklabel style={font=\footnotesize},',
     r' ymajorgrids,grid style={black!10},axis line style={black!40},tick style={black!40},',
     r' nodes near coords,nodes near coords style={font=\scriptsize,text=black!80,/pgf/number format/.cd,fixed,precision=1,zerofill},',
     r' legend style={at={(0.5,1.03)},anchor=south,font=\footnotesize,draw=none,/tikz/every even column/.append style={column sep=10pt}},',
     r' legend columns=2,legend cell align=left]']
keys = {('mnist', 'iid'): 'MI', ('mnist', 'noniid'): 'MN', ('cifar10', 'iid'): 'CI', ('cifar10', 'noniid'): 'CN'}
for mode, colour, field in [('Ordinary dispatch', 'ordinaryblue', 'passive_withheld_pct'),
                            ('Challenge dispatch', 'challengeaqua', 'trap_withheld_pct')]:
    pts = []
    for (ds, split), key in keys.items():
        v = [float(r[field]) for r in records if r['dataset'] == ds and r['split'] == split]
        mean = sum(v) / len(v)
        pts.append(f'({key},{mean:.3f})')
    F.append(r'\addplot[draw=' + colour + ',fill=' + colour + r',line width=0pt] coordinates {' + ' '.join(pts) + '};')
    F.append(r'\addlegendentry{' + mode + '}')
F += [r'\end{axis}\end{tikzpicture}',
      r'\caption{Honest responses withheld under ordinary and challenge dispatch (seed 42, 40\% free riders). '
      r'Bars show the mean over FR1--FR4; Table~\ref{tab:passive} gives each attack. Both modes remove all 640 free riders and no honest client.}',
      r'\label{fig:dispatch-withheld}', r'\end{figure}']
(OUT / 'dispatch_withheld_figure.tex').write_text('\n'.join(F) + '\n', encoding='utf-8')
