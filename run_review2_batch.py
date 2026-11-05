"""Sequential, source-frozen review experiments with checkpoint recovery/watch.

The existing Windows watchdog owns the cross-batch mutex. Independent locks
protect both this batch and each worker if a launcher is interrupted.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

from atomic_io import atomic_write_json
from std_dagmm_recovery import exclusive_lock

ROOT = Path(__file__).resolve().parent
SOURCE_FILES = (
    'run_review2_batch.py', 'train_review2.py', 'review2_config.py', 'analyze_review2_results.py',
    'clients/review2_attacks.py', 'clients/attacks.py', 'config.py', 'train.py',
    'logging_utils.py', 'atomic_io.py', 'std_dagmm_recovery.py',
    'server/v15_protocol.py', 'server/diagonal_decision.py', 'server/v15_evidence.py',
    'server/v15_strict_norm.py', 'server/v15_certificate_memory.py',
    'server/aggregation.py', 'server/paired_challenges.py', 'server/model_fingerprint.py',
    'data/loaders.py', 'data/partition.py', 'models/architectures.py',
)


def read(path, default=None):
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return default


def validate_plan(plan):
    from review2_config import ReviewConfig
    if plan.get('workflow') != 'review2' or not plan.get('experiments'):
        raise ValueError('Expected a nonempty review2 plan')
    ids = [e['id'] for e in plan['experiments']]
    if len(set(ids)) != len(ids) or any(Path(i).name != i or i in {'.', '..'} for i in ids):
        raise ValueError('Run IDs must be unique safe directory names')
    for entry in plan['experiments']:
        if entry['variant'] not in {'paired', 'passive', 'oracle'}:
            raise ValueError('Unknown experiment variant')
        ReviewConfig(**{**plan['defaults'], **entry['config']}).validate()


def complete(output, horizon):
    marker = read(output/'latest_results.json', {})
    config = read(output/'run_config.json', {})
    if not marker.get('completed') or marker.get('latest_round') != horizon or config.get('completed_rounds') != horizon:
        return False
    try:
        with (output/'global_metrics.csv').open(newline='', encoding='utf-8-sig') as handle:
            return [int(r['round']) for r in csv.DictReader(handle)] == list(range(1, horizon+1))
    except (OSError, ValueError, KeyError):
        return False


def snapshot(plan):
    return dict(workflow='review2', plan=plan,
        source_sha256={name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCE_FILES},
        experiments=plan['experiments'])


def check_registration(plan_path):
    registration=read(ROOT/'configs/review2_registration.json')
    if not registration:
        raise ValueError('Freeze the review registration before starting experiments')
    relative=plan_path.relative_to(ROOT).as_posix()
    expected=registration['plan_sha256'].get(relative)
    if expected != hashlib.sha256(plan_path.read_bytes()).hexdigest():
        raise ValueError('Registered plan changed; no outcome-dependent revision is allowed')
    for name,digest in registration['source_sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != digest:
            raise ValueError(f'Registered source changed: {name}; start a separately declared version')


def publish(plan, batch, current=None, state='running', error=None):
    entries = []
    elapsed = 0.
    for entry in plan['experiments']:
        output = batch/entry['id']
        cfg = {**plan['defaults'], **entry['config']}
        latest = read(output/'latest_results.json', {})
        metrics = latest.get('latest_global_metrics', {})
        run = read(output/'run_config.json', {})
        elapsed += float(run.get('total_wall_clock_seconds') or 0)
        done = complete(output, cfg['num_rounds'])
        entries.append(dict(id=entry['id'], config=cfg, variant=entry['variant'],
            completed_rounds=latest.get('latest_round', 0),
            state='completed' if done else (state if current == entry['id'] else 'pending'),
            progress=dict(round=latest.get('latest_round', 0), total_rounds=cfg['num_rounds'],
                methodology_version='swtcp_v15_4', review_variant=entry['variant'],
                phase=metrics.get('phase', 'queued'), device='cpu',
                active_clients=metrics.get('num_active_clients'),
                global_accuracy=metrics.get('global_accuracy'),
                suspected_clients=metrics.get('num_suspected_clients'),
                candidate_clients=metrics.get('num_candidate_clients'),
                round_time_seconds=metrics.get('round_time_seconds'))))
    status = dict(batch_id=plan['batch_name'], state=state, current_experiment=current,
        total_experiments=len(entries), completed_experiments=sum(e['state']=='completed' for e in entries),
        failed_experiments=int(state == 'failed'), experiments=entries,
        completed_rounds=sum(e['completed_rounds'] for e in entries),
        total_rounds=sum(e['config']['num_rounds'] for e in entries),
        elapsed_seconds=elapsed, estimated_remaining_seconds=None,
        updated_at=datetime.now(timezone.utc).isoformat(), error=error)
    atomic_write_json(batch/'experiment_status.json', status)
    atomic_write_json(batch.parent/'experiment_status.json', status)
    return status


def worker(plan, batch, entry):
    from review2_config import ReviewConfig
    import train_review2
    output = batch/entry['id']
    output.mkdir(parents=True, exist_ok=True)
    with exclusive_lock(output/'.runtime/worker.lock'):
        cfg = ReviewConfig(**{**plan['defaults'], **entry['config'],
            'output_dir': str(batch), 'run_name': entry['id']})
        if complete(output, cfg.num_rounds):
            return
        checkpoint = output/'latest_checkpoint.pt'
        if checkpoint.exists():
            cfg.resume_checkpoint = str(checkpoint)
        train_review2.run_experiment(cfg, variant=entry['variant'])


def run(plan_path, poll_seconds=5):
    plan = read(plan_path)
    validate_plan(plan)
    check_registration(plan_path)
    batch = ROOT/plan.get('results_root', 'results')/plan['batch_name']
    batch.mkdir(parents=True, exist_ok=True)
    with exclusive_lock(batch/'.runtime/batch.lock'):
        expected = snapshot(plan)
        manifest_path = batch/'experiment_manifest.json'
        existing = read(manifest_path)
        if existing is not None and existing != expected:
            raise ValueError('Plan/source changed; refusing mixed review results')
        atomic_write_json(manifest_path, expected)
        for entry in plan['experiments']:
            if (batch/'STOP_REQUESTED').exists():
                publish(plan, batch, state='stopped')
                return
            output = batch/entry['id']
            horizon = {**plan['defaults'], **entry['config']}['num_rounds']
            if complete(output, horizon):
                continue
            output.mkdir(exist_ok=True)
            # Resource headroom only, never a detection threshold. Do not
            # start another training process while the PC is memory-starved.
            import psutil
            while psutil.virtual_memory().available < 2*2**30:
                publish(plan,batch,entry['id'],state='waiting_resources',
                    error='Waiting for 2 GiB available RAM before training')
                if (batch/'STOP_REQUESTED').exists():
                    publish(plan,batch,state='stopped')
                    return
                time.sleep(poll_seconds)
            command = [sys.executable, str(ROOT/'run_review2_batch.py'), '--plan', str(plan_path), '--worker', entry['id']]
            with (output/'console.log').open('a', encoding='utf-8') as log:
                child = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
                while child.poll() is None:
                    publish(plan, batch, entry['id'])
                    time.sleep(poll_seconds)
            if (batch/'STOP_REQUESTED').exists():
                publish(plan, batch, entry['id'], state='stopped')
                return
            if child.returncode or not complete(output, horizon):
                publish(plan, batch, entry['id'], state='recovering', error=f'Worker exit {child.returncode}; watchdog retries from checkpoint')
                raise RuntimeError(f'Incomplete run {entry["id"]}; successors blocked')
        from analyze_review2_results import analyze
        analyze(batch)
        publish(plan, batch, state='completed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--worker')
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    plan_path = args.plan.resolve()
    plan = read(plan_path)
    validate_plan(plan)
    if args.validate_only:
        print(f'{plan["batch_name"]}: {len(plan["experiments"])} validated runs')
    elif args.worker:
        check_registration(plan_path)
        batch = ROOT/plan.get('results_root', 'results')/plan['batch_name']
        worker(plan, batch, next(e for e in plan['experiments'] if e['id'] == args.worker))
    else:
        run(plan_path)
