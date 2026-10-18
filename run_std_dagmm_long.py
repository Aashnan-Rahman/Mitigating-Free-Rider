"""Recoverable native 100-round MNIST or CIFAR-10/STD-DAGMM timing run, no trap protocol.

Paper-guided computational reproduction, NOT author code. Full-update detector
fits from scratch every round. Paper epochs/reinitialization are unspecified;
5 epochs is a declared budget, not a convergence claim. Roundwise high energy
mean+1 population SD follows the FRIDA baseline's z=1 convention. No quota,
truth labels, warmup, traps, confirmation, quarantine or permanent removal.
All clients continue FedAvg; flags are recorded, not turned into a new defense.
"""
from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import io
import json
import math
import os
import platform
import random
import statistics
import subprocess
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import psutil
import torch
from torch import nn

from atomic_io import atomic_write_json, atomic_write_text
from std_dagmm_recovery import checkpoint, load_checkpoint, publish_status, exclusive_lock
from benchmark_mnist_std_dagmm import MemorySampler, fit_std, score_std, timed
from config import ExperimentConfig
from server.paired_challenges import derive_seed, stream_seeds

ROOT = Path(__file__).resolve().parent
SOURCE_FILES = ('run_std_dagmm_long.py', 'std_dagmm_recovery.py', 'config.py', 'benchmark_mnist_std_dagmm.py', 'comparison/std_dagmm.py',
    'models/architectures.py', 'data/partition.py', 'data/loaders.py', 'clients/attacks.py',
    'server/aggregation.py', 'server/paired_challenges.py', 'train.py')


def dump_csv(path, rows):
    if not rows:
        if path.is_file():
            # A crash may leave CSV round one ahead of the first checkpoint.
            atomic_write_text(path,path.read_text().splitlines()[0]+'\n')
        return
    handle = io.StringIO(newline='')
    writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    atomic_write_text(path, handle.getvalue())


def high_energy_flags(scores):
    """Only scores enter this rule; never a known attacker share or identity."""
    values = torch.as_tensor(scores, dtype=torch.float64)
    if values.ndim != 1 or len(values) < 2 or not torch.isfinite(values).all():
        raise ValueError('Expected finite scalar energy per client')
    center, scale = values.mean(), values.std(correction=0)
    threshold = center+scale
    return (values > threshold).tolist(), float(threshold), float(center), float(scale)


def detector_worker(args):
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    x = torch.load(args.output/'.runtime/input.pt', weights_only=True, map_location='cpu')
    gc.collect()
    with MemorySampler() as memory:
        (network, mixture, details), fitting = timed(lambda: fit_std(x, args.detector_epochs, args.detector_batch,
            derive_seed(args.seed, f'std-fit:{args.worker_round}')))
        energies, scoring = timed(lambda: score_std(network, mixture, x, args.detector_batch))
        (flags, threshold, center, scale), decision = timed(lambda: high_energy_flags(energies))
    atomic_write_json(args.output/'.runtime/detector.json', dict(
        round=args.worker_round, input_shape=list(x.shape), fit_seconds=fitting,
        inference_seconds=scoring, decision_seconds=decision,
        energies=energies.tolist(), flags=flags, threshold=threshold,
        energy_mean=center, energy_population_sd=scale, memory=memory.report(), fit_details=details))


def projection(rows, horizon=100):
    fields = ('preparation_seconds','fit_seconds','inference_seconds','decision_seconds',
        'detector_seconds','baseline_compute_seconds','round_compute_seconds')
    result = {}
    for field in fields:
        values = [r[field] for r in rows]
        result[field] = dict(mean=statistics.mean(values), median=statistics.median(values),
            minimum=min(values), maximum=max(values),
            sample_sd=statistics.stdev(values) if len(values)>1 else None,
            coefficient_of_variation=(statistics.stdev(values)/statistics.mean(values)
                if len(values)>1 and statistics.mean(values)>0 else None),
            projected_100_round_seconds=horizon*statistics.mean(values))
    base = sum(r['baseline_compute_seconds'] for r in rows)
    det = sum(r['detector_seconds'] for r in rows)
    result['added_detector_time_percent_of_same_trajectory_baseline'] = 100*det/base
    result['detector_fraction_of_instrumented_compute_percent'] = 100*det/(base+det)
    result['fixed_workload_conditions'] = '100 active clients, unchanged detector/local epochs, same model and hardware; descriptive projection, NOT a completed 100-round run'
    return result


def run(args):
    import train as shared
    from clients.attacks import FreeRiderAttacker, flatten_delta
    from server.aggregation import clone_state, fedavg_delta
    out = args.output
    if args.resume:
        if not (out/'protocol.json').is_file():
            raise ValueError('Resume requires the recorded protocol')
    elif any(out.glob('*.json')):
        raise ValueError('Output already contains a run; choose a fresh directory or --resume')
    if psutil.virtual_memory().available < 2*2**30:
        raise RuntimeError('Less than 2 GiB system memory available; close memory-heavy programs first')
    config = ExperimentConfig(methodology_version='std_dagmm_native_observational', dataset=args.dataset, distribution=args.distribution,
        seed=args.seed, num_clients=args.clients, num_rounds=args.rounds, attack_type=args.attack,
        free_rider_pct=args.free_rider_pct, local_epochs=args.local_epochs, device='cpu',
        num_workers=0, pin_memory=False, download_data=False)
    # Validate shared training/partition fields with a recognized container tag.
    # This script never dispatches an SWT-CP engine or uses its detector settings.
    replace(config, methodology_version='swtcp_v13').validate()
    seeds = stream_seeds(config)
    protocol = dict(config=config.to_dict(), seed_streams=seeds, detector_epochs=args.detector_epochs,
        detector_batch=args.detector_batch, threads=args.threads,
        workflow='ordinary FedAvg -> fresh STD-DAGMM fit and energy flags each round; no update filtering or permanent removals',
        flag_rule='energy > population mean + 1 population SD, no truth/prevalence input',
        detector_recipe='paper-guided full update 128-64-32 symmetric AE, K3, energy .1, covariance .005; non-author code',
        unspecified_paper_choices='5 detector epochs, fresh initialization, Adam .001, batch20, clipping5, ridge1e-6, float64 mixture; see prior pilot recipe',
        source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCE_FILES})
    if args.resume and json.loads((out/'protocol.json').read_text()) != protocol:
        raise ValueError('Protocol/config/source changed; refuse mixed benchmark resume')
    atomic_write_json(out/'protocol.json', protocol)
    publish_status(out,state='initializing',completed_rounds=0)
    setup_start = time.perf_counter()
    shared.set_global_seed(seeds['model'])
    train_set, test_set = shared.get_datasets(config)
    partitions = shared.partition_dataset(train_set, replace(config, seed=seeds['partition']))
    loaders = [shared.make_client_loader(train_set, indices, config, derive_seed(seeds['training'], f'loader:{c}'))
        for c, indices in enumerate(partitions)]
    eval_loader = shared.make_eval_loader(config, test_set)
    model = shared.get_model(args.dataset)
    global_state = clone_state(model.state_dict())
    update_dimensions = flatten_delta(global_state, global_state).numel()
    device, loss_fn = torch.device('cpu'), nn.CrossEntropyLoss()
    attacker = FreeRiderAttacker(config, device)
    attack_rng = torch.Generator().manual_seed(seeds['attack'])
    truth = set(random.Random(seeds['attacker_selection']).sample(range(args.clients), math.ceil(args.free_rider_pct*args.clients)))
    rows, score_rows, start_round = [], [], 1
    if args.resume:
        saved = load_checkpoint(out/'latest_checkpoint.pt',protocol)
        if saved is None:
            saved=dict(protocol=protocol,global_state=global_state,attacker=attacker.state_dict(),
                attack_rng=attack_rng.get_state(),loader_rngs=[loader.generator.get_state() for loader in loaders],
                rows=[],score_rows=[],round=0)
        if saved['protocol'] != protocol:
            raise ValueError('Checkpoint protocol mismatch')
        global_state = saved['global_state']
        attacker.load_state_dict(saved['attacker'])
        attack_rng.set_state(saved['attack_rng'])
        for loader, state in zip(loaders, saved['loader_rngs']):
            loader.generator.set_state(state)
        rows, score_rows = saved['rows'], saved['score_rows']
        start_round = saved['round']+1
        del saved
        gc.collect()
    # Restore CSVs to the last durable checkpoint, discarding a partial round.
    dump_csv(out/'round_timings.csv',rows)
    dump_csv(out/'client_flags.csv',score_rows)
    setup_seconds = time.perf_counter()-setup_start
    (out/'.runtime').mkdir(exist_ok=True)
    for round_index in range(start_round, args.rounds+1):
        publish_status(out,state='client_training',round=round_index,completed_rounds=round_index-1,completed_clients=0)
        observed_start = time.perf_counter()
        base = clone_state(global_state)
        returned, honest_seconds, attack_seconds = [], 0., 0.
        with MemorySampler() as round_memory:
            for client in range(args.clients):
                start = time.perf_counter()
                if client in truth:
                    state = attacker.fabricate(client, base, round_index, attack_rng)
                    attack_seconds += time.perf_counter()-start
                else:
                    shared.set_global_seed(derive_seed(seeds['training'], f'client:{client}:round:{round_index}'))
                    state, _ = shared.train_local_model(model, base, loaders[client], loss_fn, device, config)
                    honest_seconds += time.perf_counter()-start
                returned.append(state)
                if (client+1)%20 == 0:
                    publish_status(out,state='client_training',round=round_index,completed_rounds=round_index-1,completed_clients=client+1)
                    print(f'Round {round_index}/{args.rounds}: {client+1}/{args.clients} client responses', flush=True)
            x, preparation = timed(lambda: torch.stack([flatten_delta(state, base) for state in returned]))
            input_digest = hashlib.sha256(x.numpy().tobytes()).hexdigest()
            # Detector gets only the full-update matrix, never labels/client telemetry.
            torch.save(x, out/'.runtime/input.pt')
            del x
            publish_status(out,state='detector_fitting',round=round_index,completed_rounds=round_index-1,completed_clients=args.clients)
            command = [sys.executable, str(Path(__file__).resolve()), '--worker-round', str(round_index),
                '--output', str(out), '--detector-epochs', str(args.detector_epochs), '--detector-batch', str(args.detector_batch),
                '--threads', str(args.threads), '--seed', str(args.seed)]
            with (out/f'detector_round_{round_index:02d}.log').open('w', encoding='utf-8') as log:
                worker = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            if worker.returncode:
                raise RuntimeError(f'STD-DAGMM round {round_index} failed; see detector_round_{round_index:02d}.log')
            details = json.loads((out/'.runtime/detector.json').read_text())
            if details['round'] != round_index or details['input_shape'] != [args.clients, update_dimensions]:
                raise ValueError('Mismatched detector response or full-update dimensions')
            atomic_write_json(out/f'detector_round_{round_index:02d}.json', details)
            (out/'.runtime/input.pt').unlink()
            global_state, aggregation = timed(lambda: fedavg_delta(base, returned))
            model.load_state_dict(global_state)
            evaluation, evaluating = timed(lambda: shared.evaluate_model(model, eval_loader, loss_fn, device))
        flags = details['flags']
        # Evaluation labels are joined only AFTER the scores and flags are finalized.
        tp = sum(bool(flags[c]) for c in truth)
        fp = sum(bool(flags[c]) for c in range(args.clients) if c not in truth)
        row = dict(round=round_index, active_clients=args.clients, honest_training_clients=args.clients-len(truth),
            honest_training_seconds=honest_seconds, fabrication_seconds=attack_seconds,
            aggregation_seconds=aggregation, evaluation_seconds=evaluating,
            preparation_seconds=preparation, fit_seconds=details['fit_seconds'],
            inference_seconds=details['inference_seconds'], decision_seconds=details['decision_seconds'])
        row['detector_seconds'] = sum(row[k] for k in ('preparation_seconds','fit_seconds','inference_seconds','decision_seconds'))
        row['baseline_compute_seconds'] = honest_seconds+attack_seconds+aggregation+evaluating
        row['round_compute_seconds'] = row['baseline_compute_seconds']+row['detector_seconds']
        row['observed_round_wall_seconds'] = time.perf_counter()-observed_start
        row['harness_and_unassigned_seconds'] = row['observed_round_wall_seconds']-row['round_compute_seconds']
        row.update(flagged_free_riders=tp, flagged_honest=fp, missed_free_riders=len(truth)-tp,
            flag_recall=tp/len(truth), flag_precision=tp/(tp+fp) if tp+fp else None,
            permanent_removals=0, global_accuracy=evaluation['accuracy'], input_sha256=input_digest,
            detector_peak_rss_mib=details['memory']['peak_sampled_rss_mib'],
            detector_incremental_rss_mib=details['memory']['incremental_sampled_peak_mib'],
            training_parent_peak_rss_mib=round_memory.report()['peak_sampled_rss_mib'],
            minimum_system_available_mib=min(round_memory.min_available/2**20, details['memory']['minimum_available_ram_mib']))
        rows.append(row)
        for client, (energy, flag) in enumerate(zip(details['energies'], flags)):
            score_rows.append(dict(round=round_index, client_id=client, energy=energy, flagged=int(flag),
                is_free_rider=int(client in truth), threshold=details['threshold']))
        dump_csv(out/'round_timings.csv', rows)
        dump_csv(out/'client_flags.csv', score_rows)
        checkpoint(out/'latest_checkpoint.pt', dict(protocol=protocol, round=round_index, global_state=global_state,
            attacker=attacker.state_dict(), attack_rng=attack_rng.get_state(),
            loader_rngs=[loader.generator.get_state() for loader in loaders], rows=rows, score_rows=score_rows))
        publish_status(out,state='running',round=round_index,completed_rounds=round_index,completed_clients=args.clients,latest_round=row)
        print(f"Round {round_index}: fit={row['fit_seconds']:.2f}s score={row['inference_seconds']:.3f}s, "
            f"compute={row['round_compute_seconds']:.2f}s, flagged FR={tp}/{len(truth)}, H={fp}/{args.clients-len(truth)}", flush=True)
        del returned, base, details
        gc.collect()
    report = dict(state='completed', completed_rounds=len(rows), created_at_utc=datetime.now(timezone.utc).isoformat(),
        protocol=protocol, update_dimensions=update_dimensions, setup_seconds=setup_seconds, python=sys.version, torch=torch.__version__,
        platform=platform.platform(), projection=projection(rows),
        notes=[f'Measured real {args.dataset} ordinary-FedAvg updates, no traps or v15 gating.',
            'Fresh fitting every round is an explicitly selected reproduction schedule; paper initialization/epoch budget unspecified.',
            'Five detector epochs not proof of convergence; native mechanism, not exact author-code replication.',
            'Flags are roundwise diagnoses, NOT permanent removals. All clients remain for fixed-workload timing.',
            'Flag threshold does not use truth, known attack proportion, or results-fitted quantiles.',
            'Baseline-compute sum shares this actual trajectory; not a separately executed no-detector control.',
            'Instrumented wall includes worker startup/input serialization; computational projection excludes these harness costs.',
            '100-round estimate holds N, model, epoch budgets and device fixed; no claim of late-round detection recall.'])
    for field in ('preparation_seconds','fit_seconds','inference_seconds','decision_seconds','detector_seconds','baseline_compute_seconds','round_compute_seconds'):
        report['projection'][field]['measured_total_seconds']=sum(row[field] for row in rows)
    report['measurement_horizon_rounds']=len(rows)
    if len(rows)==100:
        report['projection']['fixed_workload_conditions']='100 actual measured rounds; measured totals are not projections'
        report['notes'][-1]='100 completed actual rounds, not a ten-round extrapolation; the declared five-epoch fitting budget is unchanged.'
    atomic_write_json(out/'summary.json', report)
    publish_status(out,state='completed',round=len(rows),completed_rounds=len(rows))
    print(json.dumps(report['projection'], indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', choices=('mnist','cifar10'), default='mnist')
    parser.add_argument('--rounds', type=int, default=100)
    parser.add_argument('--clients', type=int, default=100)
    parser.add_argument('--local-epochs', type=int, default=3)
    parser.add_argument('--detector-epochs', type=int, default=5)
    parser.add_argument('--detector-batch', type=int, default=20)
    parser.add_argument('--distribution', choices=('iid','noniid'), default='noniid')
    parser.add_argument('--attack', choices=('FR1','FR2','FR3','FR4'), default='FR3')
    parser.add_argument('--free-rider-pct', type=float, default=.4)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--threads', type=int, default=6)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--worker-round', type=int)
    parser.add_argument('--output', type=Path, default=None)
    args = parser.parse_args()
    if min(args.rounds,args.clients,args.local_epochs,args.detector_epochs,args.detector_batch,args.threads)<1:
        parser.error('All counts must be positive')
    if args.output is None:
        args.output = ROOT/f'results/std_dagmm_100_seed{args.seed}_fr{round(100*args.free_rider_pct)}/std_dagmm_{args.dataset}_{args.distribution}_{args.attack}_seed{args.seed}'
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.worker_round is not None:
        detector_worker(args)
        return
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    try:
        with exclusive_lock(args.output/'.runtime/run.lock'):
            run(args)
    except BlockingIOError:
        print('Another native runner owns this output; duplicate skipped',flush=True)
    except Exception as error:
        if (args.output/'protocol.json').exists():
            prior=json.loads((args.output/'status.json').read_text()) if (args.output/'status.json').exists() else {}
            publish_status(args.output,state='failed',completed_rounds=prior.get('completed_rounds',0),error=str(error))
        raise


if __name__ == '__main__':
    main()
