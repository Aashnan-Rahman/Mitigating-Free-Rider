"""Fresh/recoverable v15.4 MNIST/CIFAR-10 timing run; no frozen source edits."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

import torch
from atomic_io import atomic_write_json
from config import ExperimentConfig
from segment_timing import RoundTimer, instrumented_engine, read_rows


def run(config, output):
    output.mkdir(parents=True, exist_ok=True)
    rows = read_rows(output/'round_timings.csv')
    latest = json.loads((output/'latest_results.json').read_text()) if (output/'latest_results.json').is_file() else {}
    complete = bool(latest.get('completed')) and len(rows) == config.num_rounds
    completed = int(rows[-1]['round']) if rows else 0
    if not complete and completed:
        candidates = []
        for path in output.glob('checkpoint_round_*.pt'):
            index = int(path.stem.removeprefix('checkpoint_round_'))
            if index <= completed:
                candidates.append((index, path))
        if not candidates:
            raise RuntimeError('Timings exist but no matching durable checkpoint; refusing a mixed replay')
        completed, checkpoint = max(candidates)
        config.resume_checkpoint = str(checkpoint)
    timer = RoundTimer(output/'round_timings.csv', completed)
    engine, provenance = instrumented_engine(timer)
    provenance['settings'] = {k:v for k,v in config.to_dict().items() if k != 'resume_checkpoint'}
    path = output/'timing_protocol.json'
    if path.is_file() and json.loads(path.read_text()) != provenance:
        raise RuntimeError('Instrumentation/config changed; use a new output')
    atomic_write_json(path, provenance)
    if not complete:
        def progress(values):
            atomic_write_json(output/'status.json', dict(state='running', completed_rounds=values['round'], latest_round=values))
            print(f"Round {values['round']}/{config.num_rounds}: accuracy={values['global_accuracy']:.4f}", flush=True)
        engine(config, progress)
    rows = read_rows(output/'round_timings.csv')
    if [int(r['round']) for r in rows] != list(range(1, config.num_rounds+1)):
        raise RuntimeError('Missing measured timing rounds')
    atomic_write_json(output/'timing_summary.json', dict(state='completed', completed_rounds=len(rows),
        setup_seconds=timer.setup_seconds, instrumentation_publication_seconds_this_invocation=timer.publication_seconds,
        measured=True, protocol=provenance))


def timing_config(dataset, output, rounds=100, seed=42):
    if dataset not in ('mnist', 'cifar10'):
        raise ValueError('Unsupported timing dataset')
    return ExperimentConfig(methodology_version='swtcp_v15_4', dataset=dataset, distribution='noniid',
        attack_type='FR3', free_rider_pct=.4, num_clients=100, num_rounds=rounds,
        seed=seed, device='cpu', local_epochs=3, save_checkpoints=True,
        checkpoint_keep_last=2, run_name=output.name, output_dir=str(output.parent))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rounds', type=int, default=100)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--dataset', choices=('mnist', 'cifar10'), default='mnist')
    args = parser.parse_args()
    torch.set_num_threads(6)
    torch.set_num_interop_threads(1)
    cfg = timing_config(args.dataset, args.output, args.rounds, args.seed)
    run(cfg, args.output.resolve())
