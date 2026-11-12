"""Build the v7.3 editorial revision and a completed-only review snapshot.

Does not train, retune, or change any registered experiment source or plan.
Run once when creating the revision; evidence refresh requires prose review.
"""
from pathlib import Path
import csv, hashlib, json, re, zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
BASE=HERE.parent/'v07_2_review_revision'
def read(p): return p.read_text(encoding='utf-8-sig')
def write(p,t): p.write_text(t,encoding='utf-8')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
with zipfile.ZipFile(HERE/'Peer review_Azom.docx') as z:
    xml=ET.fromstring(z.read('word/document.xml'))
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    review=[''.join(p.itertext()) for p in []]
    review=[''.join(t.text or '' for t in p.findall('.//w:t',ns)) for p in xml.findall('.//w:body/w:p',ns)]
write(HERE/'REVIEW_TEXT.txt','\n'.join(review)+'\n')
provenance=[]; inventory=[]; queue=[]
for pp in json.loads(read(ROOT/'configs/review2_priority_queue.json'))['plans']:
    plan=json.loads(read(ROOT/pp)); batch=plan.get('batch_name',Path(pp).stem)
    sp=ROOT/'results'/batch/'experiment_status.json'
    status=json.loads(read(sp)) if sp.exists() else {}
    queue.append(dict(plan=pp,batch=batch,total=len(plan['experiments']),completed=status.get('completed_experiments',0),state=status.get('state','queued'),current=status.get('current_experiment')))
    if sp.exists(): provenance.append(dict(path=str(sp.relative_to(ROOT)),sha256=sha(sp)))
    if not batch.startswith('review2_'): continue
    for e in status.get('experiments',[]):
        if e['state']!='completed': continue
        d=sp.parent/e['id']; rp=d/'run_config.json'; gp=d/'global_metrics.csv'
        r=json.loads(read(rp))
        with gp.open(encoding='utf-8-sig',newline='') as h: metrics=list(csv.DictReader(h))
        assert len(metrics)==100 and [int(x['round']) for x in metrics]==list(range(1,101)),e['id']
        assert r['completed_rounds']==100
        c=e['config']; inventory.append(dict(batch=batch,id=e['id'],dataset=c['dataset'],partition=c['distribution'],share=int(round(c['free_rider_pct']*100)),attack=c['attack_type'],removed=r['removed_free_riders'],honest_removed=r['removed_honest_clients'],missed=r['missed_free_riders'],accuracy=r['final_global_accuracy']))
        for f in [rp,gp]: provenance.append(dict(path=str(f.relative_to(ROOT)),sha256=sha(f)))
out=HERE/'generated/saudi'; out.mkdir(exist_ok=True)
with (out/'completed_runs.csv').open('w',newline='',encoding='utf-8') as h:
    w=csv.DictWriter(h,fieldnames=list(inventory[0]));w.writeheader();w.writerows(inventory)
snapshot=dict(cutoff_utc=datetime.now(timezone.utc).isoformat(),queue=queue,completed_review_runs=len(inventory),inputs=provenance)
write(out/'snapshot.json',json.dumps(snapshot,indent=2)+'\n')
low=[x for x in inventory if x['batch']=='review2_02_low_share_seed42']
lines=[r'\begin{table}[t]\centering\footnotesize\setlength{\tabcolsep}{3pt}',r'\caption{Completed lower-prevalence checks.}\label{tab:low-share}',r'\begin{tabular}{llrrrrr}\toprule',r'Dataset & Split & FR (\%) & FR1 & FR2 & FR3 & FR4 \\ \midrule']
for ds in ['mnist','cifar10']:
    for split in ['noniid','iid']:
        for pct in [5,10,20]:
            cells=[]
            for attack in ['FR1','FR2','FR3','FR4']:
                rs=[x for x in low if (x['dataset'],x['partition'],x['share'],x['attack'])==(ds,split,pct,attack)]
                cells.append((f"{rs[0]['removed']}/{pct}"+(r'$^{\dagger}$' if rs[0]['honest_removed'] else '')) if rs else '--')
            lines.append(('MNIST' if ds=='mnist' else 'CIFAR-10')+' & '+('Non-IID' if split=='noniid' else 'IID')+f' & {pct} & '+' & '.join(cells)+r' \\')
        lines.append(r'\midrule' if (ds,split)!=('cifar10','iid') else r'\bottomrule')
lines += [r'\end{tabular}',r'\par\smallskip\parbox{\columnwidth}{\scriptsize Completed 100-round runs only, seed 42, 100 clients. Entries: free riders removed / present. Dashes: incomplete or pending, not zero detections. $\dagger$ One honest removal.}',r'\end{table}']
write(out/'low_share_table.tex','\n'.join(lines)+'\n')

s=read(BASE/'paper_v7_2.tex')
s=s.replace('Supplementary Figures S1--S2',r'Appendix Figures~\ref{fig:geometry-mnist}--\ref{fig:geometry-cifar10}')
s=s.replace('Supplementary Table S2','Supplementary Table S2')
s=s.replace('generated/revision/low_share_table.tex','generated/saudi/low_share_table.tex')
start=s.index(r'\begin{abstract}');end=s.index(r'\end{abstract}',start)
s=s[:start]+r'''\begin{abstract}
\bfseries
Free riders receive a federated model without contributing local training.
BaitFL combines undisclosed model challenges with update norms, tensor
profiles and repeated fresh evidence before removal. Bounded review limits
temporary exclusion when evidence remains inconclusive. The detector
requires no auxiliary learner, client training loss or attack identities.
The main study comprises 96 runs on MNIST and CIFAR-10 with IID and
non-IID partitions and 30\% or 40\% free riders. All tested attackers are
non-adaptive. This grid achieves 100\% removal recall with three honest
removals in two runs. Statistical certification requires a supported cohort
of at least ten clients at an active population of 100, while exact
sendback follows a separate path. Additional honest-only runs remove no
honest clients, but completed 5\% tests miss FR2--FR4. An oracle
norm-matching feature diagnostic substantially reduces initial
certification and does not establish robustness to adaptive attacks.
Mean checking time is 215 ms per round on MNIST and 791 ms on CIFAR-10
in the instrumented 100-client runs. Checking accounts for about 88\%
and 89\% of checking-plus-aggregation time, respectively.
Even clean IID settings withhold about 11\% of honest responses.
These costs qualify the lightweight claim, which concerns measured
server computation at 100 clients rather than deployment-scale efficiency.
Matched passive ablations and a functioning comparative detection
baseline remain necessary to establish the incremental value of traps.
'''+s[end:]
s=s.replace('Checking\naccounts for less than 1\\% of computation in the instrumented executions.','Mean checking takes 215 ms on MNIST and 791 ms on CIFAR-10 in the\ninstrumented 100-client executions; this is a substantial fraction of\nchecking-plus-aggregation time.')
pos=s.index(r'\subsection',s.index(r'\section{Related')) if r'\section{Related' in s else -1
# Insert positioning immediately before the system/threat section.
marker=r'\section{System'
idx=s.find(marker)
if idx<0: idx=s.index(r'\section{',s.index(r'\section{',s.index(r'\section{Introduction}')+1)+1)
s=s[:idx]+r'''WEF-defense instead requests weight-evolution matrices from clients and
uses them to separate participation behaviors~\cite{chen2022wef}.
The S2-WEF preprint addresses changing behavior using server-simulated
attack patterns and WEF comparisons~\cite{nakamura2026s2wef}. These are
relevant alternatives to an auxiliary autoencoder, rather than methods
that can be dismissed as requiring pretraining. FLET studies test-task
mitigation through a game-theoretic formulation~\cite{guo2026flet}, while
FLoomChecker studies training-integrity verification~\cite{liang2024floom}.
BaitFL's response-only statistics and confirmation policy do not establish
superiority to these approaches. Such a claim would require matched
information access, attack settings and detection endpoints.

'''+s[idx:]
needle='The support condition in~\\eqref{eq:cohort-support}'
idx=s.index(needle)
s=s[:idx]+r'''At $n=100$, this requires at least ten nominated clients. More generally
the integer lower bound is $\lceil n/\lceil\sqrt n\rceil\rceil$, not
identically $\lceil\sqrt n\rceil$ for every population. A pure five-rider
cohort cannot qualify at 100 clients. This is a restriction on the nominated
cohort, not proof that a rider can never enter a larger mixed cohort.
Exact sendback is evaluated separately.
'''+s[idx:]
idx=s.index(r'\subsection{Oracle Norm-Matching')
s=s[:idx]+r'''For an additive fabricated response $w_{\rm sent}+d+\eta$, subtracting
the dispatched model yields $d+\eta$ whether the model was ordinary or a
challenge. Thus FR4 need not acquire a direct trap signature. Challenges
can still change the honest reference distribution, which must be tested
against the same statistics on ordinary models. FR1 sendback also needs
no trap. The current results establish the combined pipeline's behavior,
not that traps cause its detection gains. Norm-only, profile-only,
sendback-only and no-retained-memory variants are likewise untested.

'''+s[idx:]
a=s.index('At the evidence cutoff, 26');b=s.index(r'\subsection{Execution Time',a)
s=s[:a]+f'At the 12 November revision snapshot, {len(low)} of 48 low-prevalence\ncases are complete. Table~\\ref{{tab:low-share}} includes every completed\nIID and non-IID case; incomplete runs are not scored.\n'+r'''The passive ablation/MAD phase, oracle utility comparisons, published
decaying-noise and scaled-delta tests, and held-out seeds remain queued.
Stronger non-IID concentrations, mixed attacks and complete norm-matched
attack reruns are not covered by that queue.

Across the four honest-only federations, the observed permanent-removal
rate is zero. Four runs are too few for a narrow run-level uncertainty
interval. Treating federations as independent Bernoulli trials, the exact
two-sided 95\% interval for the probability of any honest removal is
approximately $[0,0.602]$. This is not a client-level interval: clients
within a federation share training and references. The main study's
three removals among 6,240 honest client-cases are descriptive; pooling
those cases as independent trials would understate uncertainty.

'''+s[b:]
idx=s.index('Figure~\\ref{fig:timing-phases} shows')
s=s[:idx]+r'''The deployment-relevant denominator must exclude simulated client SGD.
Using checking plus aggregation only, the checking fractions are about
$0.215/(0.215+0.030)=87.8\%$ on MNIST and
$0.791/(0.791+0.096)=89.2\%$ on CIFAR-10, approximately 7.2 and 8.2 times
aggregation. These are explicitly delimited server-core fractions, not
fractions of all server activity, which may also include evaluation and
I/O. The corresponding absolute times remain the primary cost measures.

Client diagnostic evaluation measures simulator-side evaluation of local
models for reporting. It is not an input to the detector or a required
client report. Its cost remains visible in the workflow table but is
outside the checking subtotal. This accounting does not justify concealing
it when comparing whole-experiment elapsed times.

Honest CIFAR-10 training averages 81.37 s for BaitFL versus 72.42 s for
the STD-DAGMM recipe. The stored timing records do not isolate the cause
of this 8.95 s difference. Changed dispatched models and execution
conditions are possible confounders, not established explanations.
Consequently the elapsed-time savings cannot be attributed solely to the
detector. Withheld response counts measure forgone contributions; they
are not a measured percentage of client CPU time or energy wasted.

'''+s[idx:]
s=s.replace('while the STD-DAGMM comparison measures a particular fitting budget.','while the STD-DAGMM comparison measures a particular fitting budget.\nIt is not a successful comparative detection baseline, and its five-epoch\ncost is not an intrinsic cost of the published method.')
s=s.replace('could share trained responses, while Sybil identities could distort the','can also compare hashes of received models. Shared frozen traps may then\nbe recognizable without training, so their being undisclosed is not a\ncollusion defense. Clients could share trained responses, while Sybil identities could distort the')
s=s.replace('Checking remains below\n1\\% of computation in the two instrumented workflows.','Checking averages 215 and 791 ms per round in the two instrumented\n100-client workflows, but dominates checking-plus-aggregation time.\nThe present study does not isolate the causal contribution of traps.')
idx=s.index(r'\bibliographystyle{IEEEtran}')
s=s[:idx]+r'''\clearpage
\appendices
\section{Complete Representative Score Geometry}\label{app:geometry}
Figures~\ref{fig:geometry-mnist} and~\ref{fig:geometry-cifar10} retain
the two 4-by-4 round-20 grids from study seed 42. Each panel contains
100 clients, including coincident points. Blue circles denote honest
clients and orange triangles denote free riders. Coordinates summarize
both selected traps. The plots illustrate observed geometry, not the
per-trap raw-norm and profile certificate tests. These examples do not
demonstrate robustness to norm matching or universal class separation.
\input{generated/geometry_mnist.tex}
\FloatBarrier
\input{generated/geometry_cifar10.tex}
\FloatBarrier

'''+s[idx:]
write(HERE/'paper_v7_3.tex',s)
for f in ['build.ps1','export.ps1']:
    write(HERE/f,read(HERE/f).replace('v7_2','v7_3').replace('v7.2','v7.3'))
supp=read(BASE/'paper_v7_2_supplement.tex').replace('7.2','7.3')
a=supp.index(r'\section{Complete Representative');b=supp.index(r'\section{Detailed Comparison',a)
supp=supp[:a]+'The complete geometry grids are included in Appendix A of the main\npaper rather than duplicated here.\n\n'+supp[b:]
write(HERE/'paper_v7_3_supplement.tex',supp)
# The remaining supplement table cross-references keep their established S numbers.
supp=read(HERE/'paper_v7_3_supplement.tex').replace(r'\section{Detailed Comparison',r'\setcounter{section}{1}'+'\n'+r'\section{Detailed Comparison')
write(HERE/'paper_v7_3_supplement.tex',supp)
print(json.dumps(dict(completed_low_share=len(low),queue=queue),indent=2))
