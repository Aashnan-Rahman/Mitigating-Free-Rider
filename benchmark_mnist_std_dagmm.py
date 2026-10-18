"""Isolated CPU timing pilot: current v15.4 vs full-update paper-guided STD-DAGMM.

Synthetic shape-matched inputs only. No FL training, known attacker fraction,
labels, removal threshold, detector changes, or claims of detection accuracy.
Each method receives the same TWO batches of N full MNIST returned states.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil
import torch

from atomic_io import atomic_write_json, atomic_write_text
from comparison.std_dagmm import StdDagmm
from models.architectures import get_model

ROOT = Path(__file__).resolve().parent


class MemorySampler:
    """Sample RSS/commit and available RAM; no forced memory pressure."""
    def __enter__(self):
        self.process = psutil.Process()
        self.stop = threading.Event()
        self.start = self.process.memory_info().rss
        self.peak = self.start
        self.min_available = psutil.virtual_memory().available
        self.thread = threading.Thread(target=self.sample, daemon=True)
        self.thread.start()
        return self

    def sample(self):
        while not self.stop.wait(.02):
            self.peak = max(self.peak, self.process.memory_info().rss)
            self.min_available = min(self.min_available, psutil.virtual_memory().available)

    def __exit__(self, *args):
        self.peak = max(self.peak, self.process.memory_info().rss)
        self.stop.set()
        self.thread.join()

    def report(self):
        return dict(baseline_rss_mib=self.start/2**20, peak_sampled_rss_mib=self.peak/2**20,
            incremental_sampled_peak_mib=(self.peak-self.start)/2**20,
            minimum_available_ram_mib=self.min_available/2**20, sample_interval_seconds=.02)


def workload(clients, seed):
    torch.manual_seed(seed)
    model = get_model('mnist')
    base = {k: v.clone() for k, v in model.state_dict().items()}
    generator = torch.Generator().manual_seed(seed + 1000)
    dimensions = sum(v.numel() for v in base.values())
    matrices, states = [], []
    flat_base = torch.cat([v.flatten() for v in base.values()])
    for _ in range(2):
        updates = torch.randn(clients, dimensions, generator=generator)
        # Unlabelled continuous variation, NOT an honest/attacker mixture.
        updates.mul_(torch.exp(.25*torch.randn(clients, 1, generator=generator)))
        updates.add_(flat_base)
        matrices.append(updates)
        batch = []
        for row in updates:
            start, state = 0, {}
            for key, value in base.items():
                state[key] = row[start:start+value.numel()].view_as(value)
                start += value.numel()
            batch.append(state)
        states.append(batch)
    fingerprint = hashlib.sha256()
    for matrix in matrices:
        fingerprint.update(matrix.numpy().tobytes())
    return base, states, fingerprint.hexdigest(), dimensions


def timed(call):
    start = time.perf_counter()
    result = call()
    return result, time.perf_counter()-start


def run_ours(base, batches, repeats):
    from clients.attacks import flatten_delta
    from server.model_fingerprint import model_fingerprint
    from server import v15_certificate_memory as detector
    from train import build_layer_profile
    clients = list(range(len(batches[0])))
    previous = model_fingerprint(base)
    def features():
        observations = {}
        for trap, batch in enumerate(batches):
            for client, state in enumerate(batch):
                delta = flatten_delta(state, base)
                norm = float(delta.norm())
                profile = build_layer_profile(state, base, 1e-6)
                sendback = norm == 0 or model_fingerprint(state) == previous
                observations.setdefault(client, {})[trap] = dict(norm=norm,
                    profile=profile.tolist(), round=11+trap, sendback=sendback)
        return observations
    def decision(rows):
        decisions, _ = detector.screen(rows, 20)
        state = detector.CycleState(clients)
        state.apply(decisions, 0, 20)
        return decisions
    trials = []
    for i in range(repeats+1):
        observations, feature_time = timed(features)
        rows, score_time = timed(lambda: detector.measurements(observations, clients, 20))
        _, decision_time = timed(lambda: decision(rows))
        if i:
            trials.append(dict(feature_seconds=feature_time, measurement_seconds=score_time,
                decision_seconds=decision_time, total_seconds=feature_time+score_time+decision_time))
        print(f'ours trial {i}/{repeats}: {feature_time+score_time+decision_time:.3f}s', flush=True)
    return dict(trials=trials, warmed_up_discarded_trials=1, includes='norm/profile/fingerprint extraction + exact LOO scores + screen/gates + fresh cycle state transition',
        excludes='trap generation, scheduling, aggregation, training, transport and research logging')


def prepare_std(base, batch):
    return torch.stack([torch.cat([(state[key]-value).flatten() for key, value in base.items()])
                        for state in batch])


def fit_std(x, epochs, batch_size, seed):
    torch.manual_seed(seed)
    network = StdDagmm(x.shape[1])
    optimizer = torch.optim.Adam(network.parameters(), lr=.001)
    losses, epochs_seconds = [], []
    generator = torch.Generator().manual_seed(seed + 1)
    for epoch in range(epochs):
        start = time.perf_counter()
        network.train()
        total = 0.
        for indices in torch.randperm(len(x), generator=generator).split(batch_size):
            batch = x[indices]
            optimizer.zero_grad(set_to_none=True)
            reconstruction, z, gamma = network(batch)
            loss, _ = network.objective(batch, reconstruction, z, gamma)
            if not torch.isfinite(loss):
                raise RuntimeError('Nonfinite STD-DAGMM objective; no timings may be presented as successful')
            loss.backward()
            torch.nn.utils.clip_grad_norm_(network.parameters(), 5.)
            optimizer.step()
            total += float(loss.detach())*len(batch)
        losses.append(total/len(x))
        epochs_seconds.append(time.perf_counter()-start)
        print(f'  STD epoch {epoch+1}/{epochs}: {epochs_seconds[-1]:.3f}s, objective={losses[-1]:.5g}', flush=True)
    optimizer.zero_grad(set_to_none=True)
    del optimizer
    gc.collect()
    network.eval()
    # Re-estimate global responsibilities/mixture after optimization, measured separately.
    start = time.perf_counter()
    with torch.inference_mode():
        all_z, all_gamma = [], []
        for batch in x.split(batch_size):
            _, z, gamma = network(batch)
            all_z.append(z)
            all_gamma.append(gamma)
        mixture = tuple(t.clone() for t in network.mixture(torch.cat(all_z), torch.cat(all_gamma)))
    mixture_seconds = time.perf_counter()-start
    return network, mixture, dict(epoch_seconds=epochs_seconds, training_loss=losses,
        model_parameters=sum(p.numel() for p in network.parameters()),
        parameter_bytes=sum(p.numel()*p.element_size() for p in network.parameters()),
        mixture_finalization_seconds=mixture_seconds)


def score_std(network, mixture, x, batch_size):
    energies = []
    with torch.inference_mode():
        for batch in x.split(batch_size):
            _, z, _ = network(batch)
            energies.append(network.energy(z, mixture))
        result = torch.cat(energies)
        if not torch.isfinite(result).all():
            raise RuntimeError('Nonfinite STD-DAGMM scores')
    return result


def run_std(base, batches, repeats, epochs, batch_size, seed):
    # No preloaded model copies or optimizer states from another detector.
    trials = []
    for trial in range(repeats):
        for trap, batch in enumerate(batches):
            print(f'STD trial {trial+1}/{repeats}, input batch {trap+1}/2', flush=True)
            x, preparation = timed(lambda: prepare_std(base, batch))
            (network, mixture, details), fitting = timed(lambda: fit_std(x, epochs, batch_size, seed+trial*2+trap))
            score_std(network, mixture, x, batch_size)  # exclude one inference warmup
            inference = []
            for _ in range(3):
                _, seconds = timed(lambda: score_std(network, mixture, x, batch_size))
                inference.append(seconds)
            trials.append(dict(trial=trial, input_batch=trap, preparation_seconds=preparation,
                fit_seconds=fitting, inference_samples_seconds=inference,
                inference_seconds=statistics.median(inference), details=details))
            del x, network, mixture
            gc.collect()
    return dict(trials=trials, official_implementation=False,
        architecture='P-128-64-32-64-128-P; latent32 + relative-L2 + cosine + input-STD; estimation35-10-3',
        components=3, energy_weight=.1, covariance_weight=.005, covariance_ridge=1e-6,
        covariance_dtype='float64; full-update autoencoder float32', optimizer='Adam', learning_rate=.001,
        epochs=epochs, batch_size=batch_size, inference_warmup_per_fit=1,
        training_schedule='fresh detector per independent 100-client batch; no assumed deployment refit frequency',
        caveat='paper-guided computational reproduction, NOT original author code or verified training-to-convergence recipe')


def worker(args):
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    base, batches, digest, dimensions = workload(args.clients, args.seed)
    # Import our helpers before the baseline memory sample, not during timed work.
    if args.worker == 'ours':
        import train
        from server import v15_certificate_memory
    gc.collect()
    before_cpu = psutil.Process().cpu_times()
    start = time.perf_counter()
    with MemorySampler() as memory:
        if args.worker == 'ours':
            result = run_ours(base, batches, args.repeats)
        else:
            result = run_std(base, batches, args.repeats, args.epochs, args.batch_size, args.seed)
    after_cpu = psutil.Process().cpu_times()
    result.update(method=args.worker, dimensions=dimensions, clients=args.clients,
        input_batches=2, input_sha256=digest, input_payload_mib=2*args.clients*dimensions*4/2**20,
        memory=memory.report(), worker_wall_seconds=time.perf_counter()-start,
        worker_cpu_seconds=after_cpu.user+after_cpu.system-before_cpu.user-before_cpu.system)
    atomic_write_json(args.output/f'{args.worker}.json', result)


def summaries(ours, std):
    if ours['input_sha256'] != std['input_sha256'] or ours['clients'] != std['clients']:
        raise ValueError('Methods did not receive identical input batches')
    a = statistics.median(t['total_seconds'] for t in ours['trials'])
    fit, online = [], []
    for trial in sorted({r['trial'] for r in std['trials']}):
        pair = [r for r in std['trials'] if r['trial'] == trial]
        if {r['input_batch'] for r in pair} != {0, 1}:
            raise ValueError('Incomplete STD trial')
        online.append(sum(r['preparation_seconds']+r['inference_seconds'] for r in pair))
        fit.append(sum(r['preparation_seconds']+r['fit_seconds']+r['inference_seconds'] for r in pair))
    online, fit = statistics.median(online), statistics.median(fit)
    return dict(ours_paired_batch_seconds=a, std_paired_online_seconds=online,
        std_paired_fit_plus_score_seconds=fit,
        ours_percent_of_std_online=100*a/online, ours_online_time_reduction_percent=100*(1-a/online),
        ours_percent_of_std_fit_plus_score=100*a/fit, ours_fit_plus_score_time_reduction_percent=100*(1-a/fit),
        overall_federated_round_overhead_percent=None,
        denominator_note='No matched no-detector federated run was measured; do not divide by old round-time logs.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', choices=('ours','std'))
    parser.add_argument('--clients', type=int, default=100)
    parser.add_argument('--epochs', type=int, default=5)
    parser.add_argument('--batch-size', type=int, default=20)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--threads', type=int, default=6)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--output', type=Path, default=ROOT/'analysis/mnist_std_dagmm_pilot')
    args = parser.parse_args()
    if min(args.clients, args.epochs, args.batch_size, args.repeats, args.threads) < 1 or args.batch_size < 2:
        parser.error('Positive settings and batch-size >=2 required')
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.worker:
        worker(args)
        return
    if any(args.output.glob('*.json')):
        raise ValueError('Output already contains a run; choose a new --output to preserve evidence')
    available = psutil.virtual_memory().available
    if available < 2*2**30:
        raise RuntimeError('Less than 2 GiB RAM available; close applications before this full-update pilot')
    atomic_write_json(args.output/'status.json', dict(state='running', settings=vars(args)|{'output':str(args.output)}))
    start = time.perf_counter()
    for method in ('ours','std'):
        command = [sys.executable, str(Path(__file__).resolve()), '--worker', method,
            '--clients', str(args.clients), '--epochs', str(args.epochs), '--batch-size', str(args.batch_size),
            '--repeats', str(args.repeats), '--threads', str(args.threads), '--seed', str(args.seed),
            '--output', str(args.output)]
        with (args.output/f'{method}.log').open('w', encoding='utf-8') as log:
            completed = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        if completed.returncode:
            atomic_write_json(args.output/'status.json', dict(state='failed', method=method, exit_code=completed.returncode))
            raise RuntimeError(f'{method} failed; inspect {args.output/method}.log')
    ours = json.loads((args.output/'ours.json').read_text())
    std = json.loads((args.output/'std.json').read_text())
    summary = summaries(ours, std)
    report = dict(state='completed', created_at_utc=datetime.now(timezone.utc).isoformat(),
        python=sys.version, torch=torch.__version__, platform=platform.platform(), processor=platform.processor(),
        logical_cpus=psutil.cpu_count(), physical_cpus=psutil.cpu_count(logical=False),
        total_ram_gib=psutil.virtual_memory().total/2**30, initial_available_ram_gib=available/2**30,
        settings=vars(args)|{'output':str(args.output)}, wall_seconds=time.perf_counter()-start,
        sources=['https://arxiv.org/pdf/1911.12560','https://arxiv.org/html/2410.05020v2'],
        limitations=['Synthetic full-sized unlabelled CPU workload; NOT MNIST training or detection accuracy.',
            'Paired comparison uses 200 responses (two batches of 100), not one deployment round.',
            'Ours includes features, scoring and first-cycle transition; excludes scheduling/trap generation/logging.',
            f'STD online assumes a fitted detector; fit+score reports fresh {args.epochs}-epoch fitting, not verified convergence.',
            'RSS is sampled every 20ms; Python heaps/allocators differ; peak includes untimed warmup.',
            'No matched federated baseline, so no overall FL overhead percentage can be asserted.'],
        implementation_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [Path(__file__).resolve(), ROOT/'comparison/std_dagmm.py', ROOT/'models/architectures.py',
                      *[ROOT/p for p in ('server/v15_protocol.py','server/diagonal_decision.py','server/v15_evidence.py',
                        'server/v15_strict_norm.py','server/v15_certificate_memory.py','server/model_fingerprint.py','train.py')]]},
        summary=summary)
    atomic_write_json(args.output/'summary.json', report)
    atomic_write_json(args.output/'status.json', dict(state='completed'))
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
