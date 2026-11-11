"""Format validated evidence without changing results or detector parameters."""
import csv
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
OUT=HERE/'generated/revision'


def read(path):
    with path.open(newline='',encoding='utf-8-sig') as handle: return list(csv.DictReader(handle))


def write(name,text): (OUT/name).write_text(text.strip()+'\n')


def main():
    study=read(HERE/'generated/multiseed/per_run.csv')
    table=[r'\begin{table*}[t]\centering\footnotesize',
        r'\caption{Honest-client costs in the main study.}\label{tab:safety}',
        r'\begin{tabular}{llrrrrr}\toprule',
        r'Dataset & Partition & FR (\%) & Honest cases & Removals & Ever quarantined & Withheld (\%) \\ \midrule']
    for d in ['mnist','cifar10']:
        if d=='cifar10': table.append(r'\midrule')
        for split in ['iid','noniid']:
            for share in [30,40]:
                group=[r for r in study if r['dataset']==d and r['split']==split and int(r['share'])==share]
                if len(group)!=12: raise ValueError('Incomplete main honest-cost cell')
                cases=sum(int(r['honest']) for r in group)
                fp=sum(int(r['fp']) for r in group)
                quarantined=sum(int(r['honest_ever_quarantined']) for r in group)
                fraction=100*sum(float(r['honest_excluded_rounds']) for r in group)/sum(float(r['honest_active_rounds']) for r in group)
                table.append(f'{"MNIST" if d=="mnist" else "CIFAR-10"} & {"IID" if split=="iid" else "Non-IID"} & {share} & {cases} & {fp} & {quarantined} & {fraction:.2f} '+r'\\')
    table += [r'\bottomrule\end{tabular}',r'\par\smallskip\parbox{.96\textwidth}{\scriptsize Counts pool completed client-cases across FR1--FR4 and study replications. A client can recur across runs. Withholding is the fraction of active honest client-rounds affected by traps or quarantine, counted once. Full attack-level means and ranges are in Supplementary Table S2.}',r'\end{table*}']
    write('honest_cost.tex','\n'.join(table))

    completed=read(OUT/'completed_review_runs.csv')
    table=[r'\begin{table}[t]\centering\footnotesize\setlength{\tabcolsep}{3.5pt}',
        r'\caption{Completed non-IID lower-prevalence checks.}\label{tab:low-share}',
        r'\begin{tabular}{lrrrrr}\toprule',r'Dataset & FR (\%) & FR1 & FR2 & FR3 & FR4 \\ \midrule']
    for d in ['mnist','cifar10']:
        if d=='cifar10': table.append(r'\midrule')
        for share in [5,10,20]:
            cells=[]
            for attack in ['FR1','FR2','FR3','FR4']:
                group=[r for r in completed if r['dataset']==d and r['split']=='noniid' and int(r['share'])==share and r['attack']==attack]
                if len(group)!=1: raise ValueError('Incomplete non-IID low-prevalence grid')
                r=group[0]; cell=f'{r["tp"]}/{share}'
                if int(r['fp']): cell+=r'$^{\dagger}$'
                cells.append(cell)
            table.append(' & '.join([('MNIST' if d=='mnist' else 'CIFAR-10'),str(share)]+cells)+r' \\')
    table += [r'\bottomrule\end{tabular}',r'\par\smallskip\parbox{\columnwidth}{\scriptsize Entries are free riders permanently removed / present by round 100. One frozen seed, 100 clients per run. $\dagger$ One honest removal; all other displayed runs have none.}',r'\end{table}']
    write('low_share_table.tex','\n'.join(table))

    summary=read(OUT/'norm_matching_summary.csv')
    table=[r'\begin{table*}[t]\centering\footnotesize\setlength{\tabcolsep}{4pt}',
        r'\caption{Round-20 statistical certificates under oracle norm matching.}\label{tab:norm-matching}',
        r'\begin{tabular}{lrrrrrr}\toprule']
    table += [r'& \multicolumn{3}{c}{Stored responses: attacker certificates (\%)} & \multicolumn{3}{c}{Norm matched} \\',
        r'\cmidrule(lr){2-4}\cmidrule(lr){5-7}',
        r'Attack & Norm & Profile & Either & Norm (\%) & Profile/either (\%) & Honest certificates \\ \midrule']
    for r in summary:
        values=[100*float(r[f'stored_{channel}_recall']) for channel in ['norm_low','profile_high','either']]
        values += [100*float(r['norm_matched_norm_low_recall']),100*float(r['norm_matched_profile_high_recall'])]
        table.append(r['attack']+' & '+' & '.join(f'{v:.1f}' for v in values)+' & '+r['norm_matched_either_honest_certificates']+r' \\')
    table += [r'\bottomrule\end{tabular}',r'\par\smallskip\parbox{.96\textwidth}{\scriptsize Each attack row covers 24 federations, 840 attacker client-cases and 1,560 honest client-cases across both datasets, partitions, 30\%/40\% and three seeds. Rates pool attacker certificates; honest entries are counts. Norm matching uses an oracle honest median and keeps scale-free profiles fixed. The endpoint is one paired statistical certificate, not removal.}',r'\end{table*}']
    write('norm_matching_table.tex','\n'.join(table))

    figure=[r'\begin{figure*}[t]\centering\begin{tikzpicture}',
        r'\begin{groupplot}[group style={group size=2 by 1,horizontal sep=1.7cm},width=.39\textwidth,height=5cm,grid=major,grid style={black!8},xlabel={$\operatorname{asinh}(\bar z_{\rm norm})$},ylabel={$\operatorname{asinh}(\bar z_{\rm profile})$},tick label style={font=\footnotesize},label style={font=\footnotesize},title style={font=\small},unbounded coords=jump]']
    for t in [20,30]:
        points=read(OUT/f'honest_error_round{t}.csv')
        for name,condition in [('honest',lambda r:r['free_rider']=='0' and r['honest_removed']=='0'),('rider',lambda r:r['free_rider']=='1'),('error',lambda r:r['honest_removed']=='1')]:
            selected=[r for r in points if condition(r)]
            with (OUT/f'error_{name}_{t}.dat').open('w') as handle:
                handle.write('x y\n'); handle.writelines(f'{r["x"]} {r["y"]}\n' for r in selected)
        figure.append(r'\nextgroupplot[title={Round '+str(t)+'}]')
        for name,style in [('honest','mark=o,mark size=1.6pt,draw=honestblue'),('rider','mark=triangle*,mark size=2pt,draw=riderorange,fill=riderorange'),('error','mark=x,mark size=3.4pt,line width=1pt,draw=honestblue')]:
            figure.append(r'\addplot[only marks,'+style+r'] table[x=x,y=y] {generated/revision/error_'+name+'_'+str(t)+'.dat};')
    figure += [r'\end{groupplot}\end{tikzpicture}',r'\par\smallskip{\footnotesize\textcolor{honestblue}{$\circ$} Honest\quad\textcolor{riderorange}{$\blacktriangle$} Free rider\quad\textcolor{honestblue}{$\times$} Honest client removed at round 30}',
        r'\caption{A recorded honest-client error case. MNIST non-IID FR3, 40\% free riders, study seed 43. Each point averages selected A/B scores. Crosses mark the two honest clients removed by repeated profile certificates. Points can coincide.}\label{fig:honest-error}',r'\end{figure*}']
    write('honest_error_figure.tex','\n'.join(figure))


if __name__=='__main__': main()
