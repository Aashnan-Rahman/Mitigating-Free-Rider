"""Preregistered reporting and isolated scaling, no federated training."""
import csv
import json
import hashlib
import math
import statistics
import time
from pathlib import Path
from atomic_io import atomic_write_json

ROOT=Path(__file__).resolve().parent

def auc(scores,labels):
    if not all(math.isfinite(float(s)) for s in scores): raise ValueError('Invalid score')
    positives=sum(labels); negatives=len(labels)-positives
    if not positives or not negatives: return None
    ordered=sorted(zip(scores,labels)); rank_sum=0.; i=0
    while i<len(ordered):
        j=i+1
        while j<len(ordered) and ordered[j][0]==ordered[i][0]: j+=1
        rank_sum+=sum(y for _,y in ordered[i:j])*((i+1+j)/2)
        i=j
    return (rank_sum-positives*(positives+1)/2)/(positives*negatives)

def score_report(paths):
    result=[]
    for path in paths:
        with path.open(newline='',encoding='utf-8-sig') as h:
            rows=[r for r in csv.DictReader(h) if int(r['round'])==20]
        clients={}
        for r in rows: clients.setdefault(int(r['client_id']),[]).append(r)
        if len(clients)!=100 or any({int(r['trap_id']) for r in rs}!={0,1} or len(rs)!=2 for rs in clients.values()):
            raise ValueError('Incomplete round-20 selected pair: '+str(path))
        labels=[int(rs[0]['is_free_rider']) for rs in clients.values()]
        result.append(dict(path=path.relative_to(ROOT).as_posix(),input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),endpoint='initial-cycle separation, not removal',
            norm_auc=auc([-statistics.mean(float(r['norm_z']) for r in rs) for rs in clients.values()],labels),
            profile_auc=auc([statistics.mean(float(r['profile_z']) for r in rs) for rs in clients.values()],labels)))
    return result

def scaling(populations=(100,500,1000),repeats=3):
    import torch, psutil
    from server.v15_certificate_memory import measurements,screen
    torch.set_num_threads(1)
    rows=[]
    for n in populations:
        gen=torch.Generator().manual_seed(42)
        norms=torch.exp(torch.randn((n,2),generator=gen))
        profile=torch.softmax(torch.randn((n,2,8),generator=gen),dim=-1)
        obs={c:{t:dict(norm=float(norms[c,t]),profile=profile[c,t].tolist(),round=11+t,sendback=False) for t in (0,1)} for c in range(n)}
        for iteration in range(repeats+1):
            before=psutil.Process().memory_info().rss
            start=time.perf_counter(); signals=measurements(obs,list(range(n)),20); features=time.perf_counter()-start
            start=time.perf_counter();screen(signals,20);decision=time.perf_counter()-start
            if iteration:
                rows.append(dict(clients=n,tensors=8,repeat=iteration,torch_threads=1,feature_seconds=features,
                    decision_seconds=decision,rss_before_bytes=before,rss_after_bytes=psutil.Process().memory_info().rss,
                    input_kind='synthetic continuous profiles, no full models; RSS snapshots are not peak memory'))
    return rows

def timing_reanalysis():
    reports=[]
    for dataset in ['mnist','cifar10']:
        base=ROOT/'results'/f'{dataset}_segment_timing_20261103'
        with (base/'ours/round_timings.csv').open(newline='') as h: ours=list(csv.DictReader(h))
        with (base/'std/round_timings.csv').open(newline='') as h: std=list(csv.DictReader(h))
        if len(ours)!=100 or len(std)!=100: raise ValueError('Incomplete native timing evidence')
        means=lambda rows,key:statistics.mean(float(r.get(key,0) or 0) for r in rows)
        check=[sum(float(r[k]) for k in ['trap_generation_seconds','scheduling_seconds','model_preparation_seconds','feature_seconds','decision_seconds']) for r in ours]
        checking=statistics.mean(check);aggregation=means(ours,'aggregation_seconds')
        reports.append(dict(dataset=dataset,checking_mean_ms=1000*checking,checking_sd_ms=1000*statistics.stdev(check),
            aggregation_mean_ms=1000*aggregation,checking_fraction_of_checking_plus_aggregation=checking/(checking+aggregation),
            client_diagnostic_evaluation_seconds=means(ours,'client_evaluation_seconds'),
            honest_training_seconds_ours=means(ours,'honest_training_seconds'),honest_training_seconds_std=means(std,'honest_training_seconds'),
            honest_training_gap_seconds=means(ours,'honest_training_seconds')-means(std,'honest_training_seconds'),
            interpretation='server-core denominator excludes client SGD and evaluation/I/O; training gap cause not identifiable from these observational logs; not a detector-only native speedup'))
    return reports

def run(plan,output):
    # This job is in the sequential queue after passive training; no contention
    # with another project worker is deliberately introduced.
    paths=[]
    for batch in ['review2_03_passive_seed42','v15_4_mnist_seed42_fr40','v15_4_cifar10_seed42_fr40']:
        paths.extend(sorted((ROOT/'results'/batch).glob('*/cycle_signals.csv')))
    if len(paths)!=32: raise ValueError(f'Expected 16 active + 16 passive files; found {len(paths)}')
    scores=score_report(paths)
    from analyze_review2_results import analyze
    _,mad=analyze(ROOT/'results/review2_03_passive_seed42')
    values=scaling()
    # Synthetic numerical smoke check, not an author-setting replication.
    import torch
    from benchmark_mnist_std_dagmm import fit_std,score_std
    gen=torch.Generator().manual_seed(42)
    benign=torch.randn((64,256),generator=gen)*.1
    abnormal=torch.randn((16,256),generator=gen)*2+3
    network,mixture,details=fit_std(benign,50,20,42)
    energies=score_std(network,mixture,torch.cat([benign,abnormal]),20)
    smoke=dict(auc=auc(energies.tolist(),[0]*64+[1]*16),epochs=50,
               interpretation='numerical smoke diagnostic only; labels evaluated after scores; not real free-rider effectiveness')
    atomic_write_json(output/'analysis.json',dict(auroc=scores,mad=mad,scaling=values,std_smoke=smoke,timing=timing_reanalysis()))
    # Standard completion contract understood by recovery/watch.
    (output/'global_metrics.csv').write_text('round\n1\n',encoding='utf-8')
    atomic_write_json(output/'run_config.json',dict(completed_rounds=1,total_wall_clock_seconds=0))
    atomic_write_json(output/'latest_results.json',dict(completed=True,latest_round=1))
