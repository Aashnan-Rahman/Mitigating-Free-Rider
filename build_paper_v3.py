"""Build paper v3 from the v2 structure and the frozen v12 40% results."""
import csv
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'result_check/paper_version_staging/versions/v03_v12_seed42'
BASE = ROOT / 'result_check/paper_version_staging/versions/v02_introduction_draft'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'data').mkdir(exist_ok=True)
    old = (BASE / 'masters_paper.tex').read_text(encoding='utf-8')
    preamble = old.split(r'\begin{abstract}')[0].replace('24 September 2026', '28 September 2026 -- Paper v3')
    intro = old.split(r'\section{Introduction}')[1].split('The principal contributions are:')[0]
    related = old.split(r'\section{Related Work}')[1].split(r'\section{Threat Model and Attacks}')[0]
    # Preserve citations and attribution, but remove unmeasured cost/superiority claims.
    related = related.replace('and greater computational cost', 'and associated computational work')
    related = related.replace('exposes a known canary objective that a capable attacker can deliberately satisfy', 'introduces an additional canary objective whose robustness requires evaluation')
    threat = old.split(r'\section{Threat Model and Attacks}')[1].split(r'\section{Proposed Methodology}')[0]
    threat = threat.replace('anchor identities', 'reference-set membership')
    rows = list(csv.DictReader((ROOT / 'results/analytics_v12_fr40_seed42/summary.csv').open(encoding='utf-8')))
    assert len(rows) == 16
    rows.sort(key=lambda r: (r['dataset'] != 'mnist', r['distribution'], r['attack']))
    provenance = []
    for row in rows:
        run = ROOT / row['run_dir']
        config = json.loads((run / 'run_config.json').read_text())
        assert config['methodology_version'] == 'swtcp_v12'
        assert config['seed'] == 42 and config['free_rider_pct'] == .4
        assert json.loads((run / 'latest_results.json').read_text())['completed']
        metrics = list(csv.DictReader((run / 'global_metrics.csv').open()))
        removals = list(csv.DictReader((run / 'removals.csv').open()))
        assert len(metrics) == 100 and len({r['client_id'] for r in removals}) == len(removals)
        assert sum(int(r['is_free_rider']) for r in removals) == int(row['removed_free_riders'])
        name = f"{row['dataset']}_{row['distribution']}_{row['attack']}"
        with (OUT / 'data' / f'{name}.csv').open('w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['round', 'accuracy', 'recall', 'honest_removed'])
            for metric in metrics:
                t = int(metric['round'])
                past = [r for r in removals if int(r['round']) <= t]
                writer.writerow([t, 100*float(metric['global_accuracy']), 100*sum(int(r['is_free_rider']) for r in past)/40, sum(1-int(r['is_free_rider']) for r in past)])
        provenance.append({'dataset': row['dataset'], 'distribution': row['distribution'], 'attack': row['attack'], 'source': str(run.relative_to(ROOT)), 'device': config.get('device'), 'seed': 42})
    shutil.copy2(ROOT / 'results/analytics_v12_fr40_seed42/summary.csv', OUT / 'data/summary.csv')
    shutil.copy2(BASE / 'refs.bib', OUT / 'refs.bib')
    (OUT / 'provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    text = preamble + r'''
\begin{abstract}
Free riders in federated learning receive a shared model while avoiding local optimization. We present version 12 of Suspicion-Weighted Trap Detection with Cumulative Penalties (SWT-CP), a server-side challenge protocol combining undisclosed model perturbations, robust update statistics, compact history reconstruction, and repeated confirmation. The detector operates on attributable returned updates without client-reported training metrics or an auxiliary learned detector. Relative to the earlier protocol, v12 adds 32-dimensional sketches of sent models and updates, coherent history signatures, cohort confirmation, and reference-based state transitions. We report all 16 completed runs at seed 42 with 100 clients, 100 rounds, and 40\% free riders: four attacks on MNIST and CIFAR-10 under IID and Dirichlet non-IID partitions. All 40 attackers are removed in every run, by round 10 for playback and round 30 for the other attacks. Fifteen runs have no honest removals; CIFAR-10 non-IID historical averaging removes one honest client, yielding 97.56\% precision and 98.77\% F1. Mean final model accuracy is 98.85\%/98.83\% for IID/non-IID MNIST and 76.18\%/74.71\% for CIFAR-10. These single-seed results support feasibility under the evaluated threat model, but do not establish robustness to adaptive attacks or eliminate temporary false suspicion.
\end{abstract}
\begin{IEEEkeywords}
federated learning, free riding, challenge-response, robust statistics, history reconstruction
\end{IEEEkeywords}
\section{Introduction}
''' + intro + r'''
The principal contributions are:
\begin{itemize}[leftmargin=*,nosep]
\item A server-side audit that compares responses to undisclosed perturbations without trusting client-reported training quality or execution telemetry.
\item Compact history reconstruction and coherent cohort evidence augmenting robust update-norm and layer-profile tests.
\item Repeated strong-cycle confirmation, reference probation, and reversible candidate states that separate temporary quarantine from permanent removal.
\item A complete matched-seed evaluation across 16 dataset, partition, and attack combinations, reporting false removals and transient-state limitations rather than selecting best observed executions.
\end{itemize}
Paper v3 describes detector v12; these are distinct version numbers. Historical v8/v9 results from paper v2 are not pooled with the present evaluation.
\section{Related Work}
''' + related + r'''
The comparisons above concern design assumptions. This evaluation does not establish a quantitative accuracy or runtime advantage over these defenses, because no matched baseline experiment is included in the reported matrix.
\section{Threat Model and Attacks}
''' + threat + r'''
\section{Proposed Methodology}
\noindent\textbf{Detection primitives.}
For floating tensor $k$, the server constructs a scale-aware challenge
\begin{equation}
\tau_k=w_{t,k}+0.01\max(\sigma(w_{t,k}),10^{-4})\xi_k,
\quad \xi_k\sim\mathcal N(0,I).
\end{equation}
Returned updates are measured relative to the model actually sent to each client. Their norm and normalized layer profile are
\begin{equation}
r_i=\|\Delta_i\|_2,\qquad
p_{i,k}=\frac{\|\Delta_{i,k}\|_2}{\max(\sum_j\|\Delta_{i,j}\|_2,\epsilon)}.
\end{equation}
Responses to the same challenge form a comparison group. Update norms are tested on both tails; distance from the componentwise median layer profile is tested on the upper tail. Robust scales use the normal-consistency-corrected MAD, a numerical floor, and historical scale stabilization. A nominal false-alarm budget of 0.01 sets cycle cutoffs, with prior reference-cycle calibration for the static tests. This calibration parameter is not a theorem guaranteeing a 1\% false-removal rate under dependent, heterogeneous observations.

\subsection{Phase I: Warm-Up}
The first ten rounds provide ordinary training and passive send-back checks. Near-zero updates and exact replay of recorded sent models contribute to the passive evidence stream. Removal under this rule requires at least five accumulated send-back events and cannot occur before the ten-round warm-up boundary. The passive path remains available after warm-up. Attack labels are needed to simulate attacks and score outcomes, not to choose detector decisions.

\subsection{Phase II: Double Coverage}
After warm-up, the server schedules distinct secret challenges and accumulates paired observations for each client. The initial reference uses the active population; subsequent comparisons use eligible reference clients when available. A trusted comparison requires at least ten reference clients. Here ``trusted'' denotes an operational reference state inferred by the protocol, not known honest ground truth.

Version 12 also stores compact sketches. Let $S$ denote the implementation's deterministic signed linear map of width 32, $s_{t,i}=S(w^{\mathrm{send}}_{t,i})$, and $u_{t,i}=S(\Delta_{t,i})$. Candidate reconstructions use only the client's sent-model history:
\begin{align}
q^{\mathrm{mean}}_{t,i}(m)&=\frac1m\sum_{j=0}^{m-1}s_{t-j,i}-s_{t,i},\\
q^{\mathrm{traj}}_{t,i}&=\operatorname{mean}_j(s_{j,i}-s_{j-1,i}).
\end{align}
The history window is five; mean hypotheses consider available lengths from two through five. Similarity is scored by
\begin{equation}
h(u,q)=-\log\max\left(\frac{\|u-q\|_2}{\max(\|u\|_2+\|q\|_2,\epsilon)},\epsilon\right).
\end{equation}
The mean-history score takes the maximum over eligible windows. High scores indicate explainability from server-sent history rather than establish proof of misconduct. History scores use one-sided robust calibration based on the median and lower-side deviations to limit inflation by a high-scoring minority. Sketches reduce retained history size but still require reading model coordinates; they are not a constant-time detector or cryptographic commitment.

\subsection{Phase III: Surveillance and Candidate Confirmation}
A signature is coherent when it persists across paired challenges. Strong evidence may arise from coherent joint norm/profile anomalies, a coherent static-signature cohort, or a coherent history-signature cohort. The cohort threshold is calculated from the active population and a binomial upper-tail criterion with the configured false-alarm budget. It is not a requested attacker count or a fixed target of 40 removals. When a sufficient mean-replay cohort is present, the broader trajectory signature is suppressed to reduce ambiguous attribution of ordinary training movement.

Clients occupy reference ($R$), candidate ($C$), or suspect ($S$) roles. An isolated weak anomaly can produce a candidate without a score penalty. A previously eligible reference client first enters $C$ when anomalous and must be independently checked again. New strong evidence maintains or restores double probing; sustained clean cycles allow single probing and then dormant intervals. Dormancy retains passive send-back checks and periodically reactivates challenges. The configured relaxation requires two clean cycles at each step and uses a 20-round dormant interval.

\subsection{Phase IV: Suspicion, Penalties, and Rehabilitation}
Strong cycles decrement the score by two; weak v12 candidate evidence contributes zero. A clean cycle restores 0.5 toward a maximum of zero. Statistical removal requires a score at or below $-4$, at least two strong cycles, and at least one strong trusted-reference confirmation after the initial cycle. The separate passive send-back criterion can also remove a client.

Two clean cycles demote $S$ to $C$ or clear $C$ to $R$, with reference probation before renewed eligibility. Candidate and suspect clients, challenged clients, and clients removed in the current round are excluded as prescribed by the aggregation path. Therefore a client may remain active but contribute less often: active-client count and aggregate-contributor count must not be conflated. The method retains client counters, reference/calibration histories, and compact model-history sketches in addition to ordinary training state.

\begin{algorithm}[t]
\caption{SWT-CP v12: operational outline}
\begin{algorithmic}[1]
\State Initialize clients, roles, scores, and history sketches
\For{each communication round}
\State Select ordinary training or secret challenges
\State Receive responses; compute passive and update evidence
\State Update sent-history sketches and reconstruction scores
\If{a comparison cycle completes}
\State Calibrate same-challenge norm/profile/history evidence
\State Identify coherent signatures and qualifying cohorts
\State Update roles, scores, confirmation, and probation
\EndIf
\State Apply statistical and passive removal criteria
\State Aggregate eligible ordinary responses; evaluate model
\State Save event logs and a completed-round checkpoint
\EndFor
\end{algorithmic}
\end{algorithm}

\section{Experimental Design}
MNIST \cite{lecun1998gradient} and CIFAR-10 \cite{krizhevsky2009learning} each use 100 initially participating clients, 100 rounds, three local epochs, batch size 32, and SGD with learning rate 0.01 and momentum 0.9. The MNIST model has two convolutional blocks (16 and 32 channels) and a 128-unit hidden classifier; CIFAR-10 uses three convolutional blocks (32, 64, and 128 channels) with batch normalization and a 256-unit hidden classifier. IID partitions and Dirichlet non-IID partitions with $\alpha=0.5$ are evaluated. Each run contains one attack type and exactly 40 free riders selected at seed 42. All 16 configurations are reported, not best-of-seed selections.

These runs executed with CUDA on the local NVIDIA GeForce GTX 1050 Ti. Per-round timings include training and protocol work and are not isolated detector benchmarks. The source configurations and completed-run markers are retained with the results. The separate 30\% experiments are excluded from this paper's evaluated matrix; the cancelled CPU trial is not used to claim a device speedup.

For final removal, $TP$ counts removed free riders, $FP$ removed honest clients, and $FN$ remaining free riders. Precision is $TP/(TP+FP)$, recall is $TP/(TP+FN)$, and $F_1=2PR/(P+R)$. False-positive removal rate is $FP/60$. Model accuracy is test classification accuracy, distinct from detection accuracy. Counts are cross-checked against unique client IDs in removal logs; progress curves are derived from event rounds rather than inferred from final summaries.

\section{Results}
\subsection{Complete Matched-Seed Performance}
Table~\ref{tab:results} reports every completed configuration. All runs remove all 40 attackers. Fifteen runs remove no honest client; CIFAR-10 non-IID FR3 removes one honest client, producing 40 true positives, one false positive, and zero false negatives. Its precision is 97.56\%, F1 is 98.77\%, and honest-client removal rate is 1.67\%. Summing across runs gives 640 removed attacker instances, not 640 distinct real-world participants.
'''
    text += r'''
\begin{table*}[t]
\centering\small
\caption{All v12 results at 40\% free riders and seed 42. Accuracies and detection metrics are percentages. Last FR denotes the round by which all free riders were removed.}
\label{tab:results}
\begin{tabular}{llcrrrrrrrr}
\toprule
Dataset & Partition & Attack & Final acc. & Best acc. & Precision & Recall & F1 & Honest removed & Last FR\\
\midrule
'''
    for r in rows:
        text += f"{r['dataset'].upper()} & {r['distribution']} & {r['attack']} & " + ' & '.join(f"{100*float(r[k]):.2f}" for k in ['final_accuracy','best_accuracy','precision','recall','f1']) + f" & {r['removed_honest_clients']} & {r['last_free_rider_removal_round']} \\\\\n"
    text += r'\bottomrule\end{tabular}\end{table*}' + '\n'
    text += r'''
\subsection{Detection Progress}
All 40 FR1 clients are removed at round 10 in each dataset/partition setting. All 40 FR2, FR3, and FR4 clients are removed at round 30. These coincident removal rounds reflect batch decision boundaries in this configuration rather than continuous per-response removal. Figure~\ref{fig:recall} reconstructs these curves from the event logs. Timing alone does not identify which signature caused each decision; causal attribution would require ablations.
'''
    for metric, label, caption in [
        ('recall','recall','Cumulative removal recall from event logs. Curves overlap where attacks share removal rounds; FR2--FR4 coincide at round 30 in every panel.'),
        ('accuracy','accuracy','Per-round test accuracy for every completed run. Panels use dataset-specific vertical ranges; compare attack curves within a panel.')]:
        text += '\n'+r'\begin{figure*}[t]\centering\begin{tikzpicture}'+'\n'
        text += r'\begin{groupplot}[group style={group size=2 by 2,horizontal sep=1.3cm,vertical sep=1.25cm},width=0.43\textwidth,height=4.3cm,xlabel={Round},xmin=1,xmax=100,grid=major,tick label style={font=\scriptsize},label style={font=\small},title style={font=\small}]'+'\n'
        for dataset in ['mnist','cifar10']:
            for distribution in ['iid','noniid']:
                limits = 'ymin=0,ymax=105' if metric=='recall' else ('ymin=80,ymax=100' if dataset=='mnist' else 'ymin=0,ymax=85')
                text += f"\\nextgroupplot[title={{{dataset.upper()} {distribution}}},ylabel={{{metric.capitalize()} (\\%) }},{limits}]\n"
                for attack,color,style in [('FR1','blue','solid'),('FR2','red','dashed'),('FR3','green!50!black','dotted'),('FR4','orange','dashdotted')]:
                    text += f"\\addplot[{color},{style},thick] table[x=round,y={metric},col sep=comma] {{data/{dataset}_{distribution}_{attack}.csv}};\n\\addlegendentry{{{attack}}}\n"
        text += f"\\end{{groupplot}}\\end{{tikzpicture}}\n\\caption{{{caption}}}\\label{{fig:{label}}}\\end{{figure*}}\n"
    text += r'''
\subsection{Comparative Result Analysis}
MNIST final accuracy is similar across distributions: 98.85\% averaged over the four IID attacks and 98.83\% over non-IID attacks. The attack-matched non-IID changes are $-0.05$, $-0.02$, $-0.01$, and $-0.01$ percentage points for FR1--FR4. No MNIST run removes an honest client.

CIFAR-10 mean final accuracy falls from 76.18\% under IID to 74.71\% under non-IID, a 1.47-point descriptive difference. Non-IID minus IID differences for FR1--FR4 are $+0.40$, $-1.97$, $-2.08$, and $-2.24$ points. A common seed improves traceability but supplies neither independent repetitions nor a confidence interval. The old paper's best-observed multi-seed results and different methodology cannot support a controlled claim of improvement over v8/v9.

The sole false removal is honest client 32 in CIFAR-10 non-IID FR3 at round 30. Its logged basis is two strong cycles with trusted confirmation, with score $-4$ and zero send-back events. Thus reference confirmation reduces neither the observed error to zero nor the need to inspect non-IID honest outliers. Determining which v12 component caused this false positive requires a separate trace-level or ablation analysis.

\subsection{Utility and Execution Cost}
Figure~\ref{fig:accuracy} shows the learning trajectories. The mean final test accuracies above measure model utility, but no no-attack baseline is available to isolate the loss caused by free riding or by quarantine. Summed round time is 6.37/6.53 hours for the four MNIST IID/non-IID runs and 12.77/10.82 hours for CIFAR-10. These totals exclude setup overhead and are not detector-only costs; they must not be interpreted as a CUDA/CPU comparison.

Permanent removal is not the only operational cost. At termination, honest clients can remain in candidate or suspect states and be excluded from some aggregation rounds. Table~\ref{tab:states} exposes these residual states. Remaining counts do not estimate an unseen attacker population, since all simulated attackers have already been removed.
\begin{table}[t]\centering\small
\caption{Final candidate/suspect counts, ordered FR1, FR2, FR3, FR4.}\label{tab:states}
\begin{tabular}{lll}\toprule Dataset & Partition & C/S by attack\\\midrule
'''
    for dataset in ['mnist','cifar10']:
        for distribution in ['iid','noniid']:
            group = [r for r in rows if r['dataset']==dataset and r['distribution']==distribution]
            text += f"{dataset.upper()} & {distribution} & " + ', '.join(f"{r['final_candidates']}/{r['final_suspected']}" for r in group) + r'\\'+'\n'
    text += r'''
\bottomrule\end{tabular}\end{table}
\section{Discussion and Limitations}
The v12 results show complete final removal recall in the fixed 40\% matrix and only one permanent false removal. They do not demonstrate that all honest participation is preserved: quarantine and probe exclusion can reduce useful contributions even with perfect removal precision. The 32-dimensional sketch limits history storage but does not by itself prove low end-to-end overhead, and a reconstruction match is statistical evidence rather than verification of training.

The nominal false-alarm and binomial cohort calculations are operational heuristics under shared models and correlated observations. Their independence and calibration assumptions need not hold under heterogeneous data. Ground-truth attacker identities are used for simulation and evaluation; the v12 detector interface does not receive them. This separation does not substitute for a comprehensive implementation audit. Repeated seeds, ablations of history evidence and cohort gating, and matched comparisons with baseline defenses are required before broad comparative claims.

\section{Assumptions and Future Work}
The study assumes an honest server, attributable individual updates, full participation of active clients, fixed attack identities, one attack family per run, and honest execution of prescribed local optimization by nonattackers. The simulated attackers do not adapt to inferred audit state. Unmodified secure aggregation hides the individual responses this protocol needs, so deployment with secure aggregation requires additional protocol design.

Future work should evaluate partial training, intermittent participation, mixed and colluding attacks, defense-aware evasion, additional seeds and heterogeneity levels, and matched no-attack and detector baselines. The first diagnostic priority is the non-IID FR3 false removal and residual honest quarantine. The in-progress 30\% matrix should be reported separately after completion, without selecting only favorable outcomes. A controlled device benchmark must hold attacker fraction, attack, model, seed, and execution conditions fixed.

\section{Conclusion}
SWT-CP v12 combines secret model challenges, robust static evidence, compact history reconstruction, and repeated reference-based confirmation. Across all 16 completed seed-42 runs at 40\% free riders, every attacker is removed, with one honest removal in CIFAR-10 non-IID FR3. MNIST accuracy remains near 98.8\%; CIFAR-10 averages 76.18\% IID and 74.71\% non-IID. The evidence supports feasibility in this controlled setting while retaining explicit uncertainty about generalization, adaptive attackers, transient exclusion, and computational overhead.
\bibliographystyle{IEEEtran}
\bibliography{refs}
\end{document}
'''
    (OUT / 'paper_v3.tex').write_text(text, encoding='utf-8')
    keys = set(re.findall(r'@\w+\s*\{\s*([^,]+)', (OUT / 'refs.bib').read_text()))
    cites = {key.strip() for group in re.findall(r'\\cite\{([^}]+)\}', text) for key in group.split(',')}
    assert cites <= keys, cites-keys
    (OUT / 'README.md').write_text('''# Paper v3 — SWT-CP v12

Main file: `paper_v3.tex`. This preserves the IEEE conference format and section order of `v02_introduction_draft/masters_paper.tex`. Paper v2 remains unchanged.

Compile with `latexmk -pdf paper_v3.tex`, or upload this directory to Overleaf and select `paper_v3.tex` as the main document. The figures are native PGFPlots and use the bundled CSV files. Keep the data directory beside the TeX file.

Changes: v12 history sketches, cohort confirmation, reference-state transitions, all 16 matched-seed 40% runs, per-round accuracy and removal figures, explicit honest-client false removal, residual candidate states, and revised limitations. Old best-of-seed v8/v9 results and unfinished 30% results are excluded.

`data/summary.csv` contains per-run analytics; `provenance.json` maps figures to original runs. Run `python analyze_v12_fr40_results.py` then `python build_paper_v3.py` from the repository root to regenerate. The bibliography is inherited from v2; no new external references were added or independently re-reviewed.
''', encoding='utf-8')
    print(OUT)


if __name__ == '__main__':
    main()
