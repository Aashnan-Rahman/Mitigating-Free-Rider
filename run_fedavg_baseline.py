"""Ordinary FedAvg with simulated FR1-FR4, no detection/traps/filtering/removal."""
from __future__ import annotations
import argparse
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import random
import sys
import time
from dataclasses import replace

import torch
from torch import nn

import train as shared
from atomic_io import atomic_write_json
from benchmark_mnist_std_dagmm import MemorySampler,timed
from clients.attacks import FreeRiderAttacker
from config import ExperimentConfig
from run_std_dagmm_long import dump_csv
from server.aggregation import clone_state,fedavg_delta
from server.paired_challenges import derive_seed,stream_seeds
from std_dagmm_recovery import checkpoint,load_checkpoint,publish_status,exclusive_lock

ROOT=Path(__file__).resolve().parent
SOURCES=('run_fedavg_baseline.py','run_std_dagmm_long.py','std_dagmm_recovery.py',
    'benchmark_mnist_std_dagmm.py','comparison/std_dagmm.py','config.py','train.py',
    'clients/attacks.py','models/architectures.py','data/loaders.py','data/partition.py',
    'server/aggregation.py','server/paired_challenges.py')


def run(args):
    output=args.output
    if not args.resume and (output/'protocol.json').exists():
        raise ValueError('Existing experiment requires --resume')
    config=ExperimentConfig(methodology_version='fedavg_no_detection',dataset=args.dataset,
        distribution=args.distribution,num_clients=args.clients,num_rounds=args.rounds,
        local_epochs=args.local_epochs,seed=args.seed,attack_type=args.attack,
        free_rider_pct=args.free_rider_pct,device='cpu',num_workers=0,pin_memory=False,download_data=False)
    replace(config,methodology_version='swtcp_v13').validate()
    seeds=stream_seeds(config)
    protocol=dict(config=config.to_dict(),seed_streams=seeds,threads=args.threads,
        workflow='ordinary unweighted FedAvg; every response aggregates; no traps/detector/flags/removal',
        detection_enabled=False,trap_generation_enabled=False,removal_enabled=False,
        source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCES})
    if args.resume and json.loads((output/'protocol.json').read_text())!=protocol:
        raise ValueError('Source/config changed; refusing a mixed baseline resume')
    atomic_write_json(output/'protocol.json',protocol)
    publish_status(output,state='initializing',completed_rounds=0)
    shared.set_global_seed(seeds['model'])
    training,test=shared.get_datasets(config)
    partitions=shared.partition_dataset(training,replace(config,seed=seeds['partition']))
    loaders=[shared.make_client_loader(training,indices,config,derive_seed(seeds['training'],f'loader:{c}'))
             for c,indices in enumerate(partitions)]
    evaluation=shared.make_eval_loader(config,test)
    model=shared.get_model(args.dataset)
    global_state=clone_state(model.state_dict())
    attacker=FreeRiderAttacker(config,torch.device('cpu'))
    attack_rng=torch.Generator().manual_seed(seeds['attack'])
    truth=set(random.Random(seeds['attacker_selection']).sample(range(args.clients),math.ceil(args.free_rider_pct*args.clients)))
    atomic_write_json(output/'partition_manifest.json',dict(
        clients=[dict(client_id=c,indices=list(map(int,indices)),is_free_rider=c in truth)
                 for c,indices in enumerate(partitions)],
        note='Simulator audit metadata only; attackers fabricate rather than train on their assigned partition.'))
    rows,client_rows,start=[],[],1
    if args.resume:
        saved=load_checkpoint(output/'latest_checkpoint.pt',protocol)
        if saved is not None:
            global_state=saved['global_state']
            attacker.load_state_dict(saved['attacker'])
            attack_rng.set_state(saved['attack_rng'])
            for loader,state in zip(loaders,saved['loader_rngs']):
                loader.generator.set_state(state)
            rows,client_rows,start=saved['rows'],saved['client_rows'],saved['round']+1
            del saved
            gc.collect()
    dump_csv(output/'round_timings.csv',rows)
    dump_csv(output/'client_metrics.csv',client_rows)
    loss=nn.CrossEntropyLoss()
    for r in range(start,args.rounds+1):
        publish_status(output,state='client_training',round=r,completed_rounds=r-1,completed_clients=0)
        wall=time.perf_counter()
        base=clone_state(global_state)
        returned=[]
        honest_time,attack_time=0.,0.
        with MemorySampler() as memory:
            for c in range(args.clients):
                beginning=time.perf_counter()
                if c in truth:
                    response=attacker.fabricate(c,base,r,attack_rng)
                    local=dict(accuracy=None,loss=None)
                    duration=time.perf_counter()-beginning
                    attack_time+=duration
                    steps=0
                else:
                    shared.set_global_seed(derive_seed(seeds['training'],f'client:{c}:round:{r}'))
                    response,local=shared.train_local_model(model,base,loaders[c],loss,torch.device('cpu'),config)
                    duration=time.perf_counter()-beginning
                    honest_time+=duration
                    steps=args.local_epochs*len(loaders[c])
                returned.append(response)
                client_rows.append(dict(round=r,client_id=c,is_free_rider=int(c in truth),
                    was_active=1,was_aggregated=1,was_trapped=0,was_quarantined=0,
                    local_steps=steps,partition_samples=len(loaders[c].dataset),
                    local_accuracy=local['accuracy'],local_loss=local['loss'],compute_seconds=duration))
                if (c+1)%20==0:
                    publish_status(output,state='client_training',round=r,completed_rounds=r-1,completed_clients=c+1)
                    print(f'Round {r}/{args.rounds}: {c+1}/{args.clients} responses',flush=True)
            global_state,aggregation=timed(lambda:fedavg_delta(base,returned))
            model.load_state_dict(global_state)
            metrics,evaluating=timed(lambda:shared.evaluate_model(model,evaluation,loss,torch.device('cpu')))
        resource=memory.report()
        row=dict(round=r,active_clients=args.clients,honest_training_clients=args.clients-len(truth),
            num_aggregated=args.clients,num_trapped=0,permanent_removals=0,
            honest_training_seconds=honest_time,fabrication_seconds=attack_time,
            aggregation_seconds=aggregation,evaluation_seconds=evaluating,
            preparation_seconds=0.,fit_seconds=0.,inference_seconds=0.,decision_seconds=0.,detector_seconds=0.,
            baseline_compute_seconds=honest_time+attack_time+aggregation+evaluating,
            round_compute_seconds=honest_time+attack_time+aggregation+evaluating,
            observed_round_wall_seconds=time.perf_counter()-wall,
            global_accuracy=metrics['accuracy'],global_loss=metrics['loss'],
            training_parent_peak_rss_mib=resource['peak_sampled_rss_mib'],
            minimum_system_available_mib=resource['minimum_available_ram_mib'])
        rows.append(row)
        dump_csv(output/'round_timings.csv',rows)
        dump_csv(output/'client_metrics.csv',client_rows)
        checkpoint(output/'latest_checkpoint.pt',dict(protocol=protocol,round=r,global_state=global_state,
            attacker=attacker.state_dict(),attack_rng=attack_rng.get_state(),
            loader_rngs=[loader.generator.get_state() for loader in loaders],rows=rows,client_rows=client_rows))
        publish_status(output,state='running',round=r,completed_rounds=r,completed_clients=args.clients,latest_round=row)
        print(f"Round {r}: compute={row['round_compute_seconds']:.2f}s, accuracy={metrics['accuracy']:.4f}; all {args.clients} responses aggregated",flush=True)
        del returned,base
        gc.collect()
    torch.save(dict(global_state=global_state,protocol=protocol,round=args.rounds),output/'final_model.pt')
    summary=dict(state='completed',completed_rounds=len(rows),protocol=protocol,
        final_accuracy=rows[-1]['global_accuracy'],final_loss=rows[-1]['global_loss'],
        measured_total_compute_seconds=sum(row['round_compute_seconds'] for row in rows),
        mean_compute_seconds=sum(row['round_compute_seconds'] for row in rows)/len(rows),
        removals=0,detection_enabled=False,trap_generation_enabled=False,
        notes=['All clients participate and all responses aggregate; no detector is called.',
               'Real network communication is not measured in this serial local simulator.',
               'Client metrics, partition indices, protocol hashes, all round timings and final model are retained.',
               'Recovery retains latest/previous checkpoints, not every full client response tensor.'])
    atomic_write_json(output/'summary.json',summary)
    publish_status(output,state='completed',round=len(rows),completed_rounds=len(rows))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',choices=('mnist','cifar10'),default='cifar10')
    parser.add_argument('--distribution',choices=('iid','noniid'),default='noniid')
    parser.add_argument('--attack',choices=('FR1','FR2','FR3','FR4'),default='FR3')
    parser.add_argument('--free-rider-pct',type=float,default=.4)
    for name,default in (('rounds',100),('clients',100),('local-epochs',3),('threads',6),('seed',42)):
        parser.add_argument('--'+name,type=int,default=default)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    args.output=args.output.resolve()
    args.output.mkdir(parents=True,exist_ok=True)
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    try:
        with exclusive_lock(args.output/'.runtime/run.lock'):
            run(args)
    except BlockingIOError:
        print('Existing baseline runner owns this output; duplicate skipped',flush=True)
    except Exception as error:
        prior=json.loads((args.output/'status.json').read_text()) if (args.output/'status.json').exists() else {}
        publish_status(args.output,state='failed',completed_rounds=prior.get('completed_rounds',0),error=str(error))
        raise
