"""Lin-setting validation ATTEMPT, not author code or exact replication.

Known published setting: MNIST, 100 clients, one delta-weight attacker,
two-layer fully connected model, global eta .3/1. Underspecified choices
(256 hidden units, SGD .01, one local epoch, 50 AE epochs) are declared.
All score and failure outcomes are retained, not used to select settings.
"""
import csv
import gc
import hashlib
import json
from pathlib import Path
import time
import torch
from torch import nn
from torch.nn.utils import parameters_to_vector,vector_to_parameters
import train as shared
from config import ExperimentConfig
from server.paired_challenges import derive_seed
from benchmark_mnist_std_dagmm import fit_std,score_std
from std_dagmm_recovery import checkpoint
from atomic_io import atomic_write_json
from review3_analysis import auc

def run(plan,output,entry):
    cfg={**plan['defaults'],**entry['config']}
    config=ExperimentConfig(dataset='mnist',distribution='iid',num_clients=100,num_rounds=10,
        seed=42,local_epochs=1,learning_rate=.01,download_data=False,device='cpu')
    torch.set_num_threads(6)
    shared.set_global_seed(42)
    train_set,test_set=shared.get_datasets(config)
    partitions=shared.partition_dataset(train_set,config)
    loaders=[shared.make_client_loader(train_set,p,config,derive_seed(42,f'lin-loader:{c}')) for c,p in enumerate(partitions)]
    model=nn.Sequential(nn.Flatten(),nn.Linear(784,256),nn.ReLU(),nn.Linear(256,10))
    base=parameters_to_vector(model.parameters()).detach().clone()
    previous=None; rows=[]; scores=[]; start_round=1
    source=Path(__file__).resolve().parent
    reg=json.loads((source/'configs/review3_registration.json').read_text())
    protocol=dict(config=cfg,registration_sha256=hashlib.sha256((source/'configs/review3_registration.json').read_bytes()).hexdigest(),
        source='https://arxiv.org/html/1911.12560#S5.SS3',
        status='paper-setting approximation; no claim of author-equivalent hyperparameters',
        choices=dict(hidden=256,local_sgd_lr=.01,local_epochs=1,detector_epochs=50,detector_batch=20,
                     detection='native roundwise energy AUROC and mean+1 SD flags; no removal',first_dwa='zero without history'))
    if (output/'latest_checkpoint.pt').exists():
        saved=torch.load(output/'latest_checkpoint.pt',weights_only=False,map_location='cpu')
        if saved['protocol']!=protocol: raise ValueError('Lin validation checkpoint changed')
        base,previous,rows,scores=saved['base'],saved['previous'],saved['rows'],saved['scores']
        for loader,state in zip(loaders,saved['loaders']): loader.generator.set_state(state)
        start_round=saved['round']+1
    atomic_write_json(output/'protocol.json',protocol)
    for t in range(start_round,11):
        start=time.perf_counter(); updates=[]
        for c in range(100):
            if c==0:
                gradient=previous-base if previous is not None else torch.zeros_like(base)
            else:
                shared.set_global_seed(derive_seed(42,f'lin:{c}:{t}'))
                vector_to_parameters(base.clone(),model.parameters());model.train()
                opt=torch.optim.SGD(model.parameters(),lr=.01)
                for x,y in loaders[c]:
                    opt.zero_grad(set_to_none=True);loss=nn.functional.cross_entropy(model(x),y);loss.backward();opt.step()
                gradient=base-parameters_to_vector(model.parameters()).detach()
                del opt
            updates.append(gradient.clone())
        x=torch.stack(updates)
        training=time.perf_counter()-start
        start=time.perf_counter();network,mixture,details=fit_std(x,50,20,derive_seed(42,f'lin-fit:{t}'))
        atomic_write_json(output/f'fit_round_{t:03d}.json',details)
        fit=time.perf_counter()-start;start=time.perf_counter();energy=score_std(network,mixture,x,20)
        inference=time.perf_counter()-start
        flags=energy>energy.mean()+energy.std(correction=0)
        rows.append(dict(round=t,training_seconds=training,fit_seconds=fit,inference_seconds=inference,
                         energy_auc=auc(energy.tolist(),[1]+[0]*99),flagged_free_riders=int(flags[0]),flagged_honest=int(flags[1:].sum())))
        scores.extend(dict(round=t,client_id=c,energy=float(energy[c]),is_free_rider=int(c==0)) for c in range(100))
        previous=base.clone();base=base-float(cfg['global_eta'])*x.mean(0)
        if not torch.isfinite(base).all(): raise ValueError('Nonfinite global model')
        for name,values in [('global_metrics.csv',rows),('energy_scores.csv',scores)]:
            with (output/name).open('w',newline='',encoding='utf-8') as h:
                w=csv.DictWriter(h,fieldnames=list(values[0]));w.writeheader();w.writerows(values)
        atomic_write_json(output/'run_config.json',dict(completed_rounds=t,total_wall_clock_seconds=sum(r['training_seconds']+r['fit_seconds']+r['inference_seconds'] for r in rows)))
        checkpoint(output/'latest_checkpoint.pt',dict(protocol=protocol,round=t,base=base,previous=previous,rows=rows,scores=scores,loaders=[l.generator.get_state() for l in loaders]))
        atomic_write_json(output/'latest_results.json',dict(completed=t==10,latest_round=t,latest_global_metrics=dict(phase='std_validation',round=t)))
        print(f'Lin-setting attempt eta={cfg["global_eta"]} round={t}/10 AUROC={rows[-1]["energy_auc"]}',flush=True)
        del network,mixture,updates,x;gc.collect()
    # A crash after the final checkpoint but before publishing completion is
    # repaired without rerunning already committed rounds.
    if len(rows)==10:
        atomic_write_json(output/'latest_results.json',dict(completed=True,latest_round=10))
