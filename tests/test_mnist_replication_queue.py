"""MNIST's 32-case follow-up grid and safe handoff, without real training."""
import json
from pathlib import Path

import pytest

import monitor
from config import ExperimentConfig
from run_experiments import expand_plan
from test_scheduled_queue import ROOT, recovery, run_queue, calls, batch, write_json


def read_plan(relative):
    return json.loads((ROOT / relative).read_text())


def active_queue():
    active = read_plan('configs/active_experiment_schedule.json')
    return active, read_plan(active['queue'])


@pytest.mark.parametrize('seed', [73, 43])
def test_mnist_grid_uses_both_percentages_with_unchanged_policy(seed):
    plan = read_plan(f'configs/v15_4_mnist_seed{seed}_fr30_fr40_plan.json')
    previous = read_plan('configs/v15_4_mnist_seed42_fr40_plan.json')
    cifar = read_plan(f'configs/v15_4_cifar10_seed{seed}_fr30_fr40_plan.json')
    assert plan['defaults'] == {**previous['defaults'], 'seed': seed}
    assert plan['defaults'] == {**cifar['defaults'], 'dataset': 'mnist'}
    entries = expand_plan(plan, include_disabled=False)
    assert len(entries) == len({e['id'] for e in entries}) == 16
    actual = set()
    for entry in entries:
        config = ExperimentConfig.from_dict({**plan['defaults'], **entry['config']})
        config.validate()
        assert config.dataset == 'mnist' and config.seed == seed
        assert config.num_clients == config.num_rounds == 100
        assert config.methodology_version == 'swtcp_v15_4' and config.local_epochs == 3
        assert config.save_checkpoints and config.checkpoint_keep_last == 2
        assert f'_fr{round(config.free_rider_pct * 100)}_seed{seed}' in entry['id']
        actual.add((config.distribution, config.attack_type, config.free_rider_pct))
    assert actual == {(d, a, p) for d in ('iid', 'noniid')
                      for a in ('FR1', 'FR2', 'FR3', 'FR4') for p in (.3, .4)}
    assert [e['config']['distribution'] for e in entries] == ['noniid'] * 8 + ['iid'] * 8
    assert [e['config']['free_rider_pct'] for e in entries] == [.4] * 4 + [.3] * 4 + [.4] * 4 + [.3] * 4
    assert [e['config']['attack_type'] for e in entries[:4]] == ['FR3', 'FR4', 'FR2', 'FR1']


def test_persistent_queue_preserves_cifar_prefix_then_exactly_32_mnist_runs():
    active, queue = active_queue()
    original = read_plan('configs/v15_4_cifar10_seed73_seed43_queue.json')
    assert queue['plans'][:2] == original['plans']
    assert active['plan'] == queue['plans'][0]
    assert active['auto_resume'] and not active['auto_update_paper'] and active['cpu_threads'] == 6
    plans = [read_plan(path) for path in queue['plans'][:4]]
    assert [(p['defaults']['dataset'], p['defaults']['seed']) for p in plans] == [
        ('cifar10', 73), ('cifar10', 43), ('mnist', 73), ('mnist', 43)]
    entries = [entry for plan in plans[2:] for entry in expand_plan(plan, include_disabled=False)]
    assert len(entries) == len({e['id'] for e in entries}) == 32
    assert len({p['batch_name'] for p in plans}) == 4


@pytest.fixture
def mnist_queue(recovery):
    active, queue = active_queue()
    # This fixture isolates the original detection prefix. Mixed-workflow
    # successor coverage lives in test_matched_baseline_schedule.py.
    queue = {**queue, 'plans': queue['plans'][:4]}
    write_json(recovery / 'configs/active_experiment_schedule.json', active)
    write_json(recovery / active['queue'], queue)
    names = []
    for path in queue['plans']:
        plan = read_plan(path)
        names.append(plan['batch_name'])
        # Only the recovery launcher is real; the fake runner writes one marker.
        write_json(recovery / path, dict(batch_name=plan['batch_name'], results_root='./results'))
    return recovery, names


def test_current_cifar_finishes_before_mnist_and_completed_batches_skip(mnist_queue):
    root, names = mnist_queue
    batch(root, names[0], complete=True)
    batch(root, names[1])
    result = run_queue(root, 'unrelated')
    assert result.returncode == 0, result.stdout + result.stderr
    expected = [f'--resume-batch:{names[1]}', f'--plan:{names[2]}', f'--plan:{names[3]}']
    assert calls(root) == expected
    again = run_queue(root)
    assert again.returncode == 0, again.stdout + again.stderr
    assert calls(root) == expected


def test_restart_resumes_mnist_before_starting_other_seed(mnist_queue):
    root, names = mnist_queue
    for name in names[:2]:
        batch(root, name, complete=True)
    batch(root, names[2])
    result = run_queue(root)
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls(root) == [f'--resume-batch:{names[2]}', f'--plan:{names[3]}']


@pytest.mark.parametrize('marker', ['STOP_REQUESTED', 'fail_runner', 'incomplete_runner'])
def test_cifar_stop_failure_or_incomplete_return_blocks_all_mnist(mnist_queue, marker):
    root, names = mnist_queue
    batch(root, names[0], complete=True)
    path = batch(root, names[1])
    ((path if marker == 'STOP_REQUESTED' else root) / marker).touch()
    result = run_queue(root)
    assert (result.returncode == 0) == (marker == 'STOP_REQUESTED')
    assert calls(root) == ([] if marker == 'STOP_REQUESTED' else [f'--resume-batch:{names[1]}'])
    assert not any((root / 'results' / name).exists() for name in names[2:])


def test_watch_follows_both_mnist_seeds_through_handoff(mnist_queue, monkeypatch):
    root, names = mnist_queue
    monkeypatch.chdir(root)
    for name in names[:2]:
        batch(root, name, complete=True)
    paths = [Path('results') / name / 'experiment_status.json' for name in names]
    assert monitor.scheduled_status_paths() == paths
    assert monitor.resolve_status_path(None) == paths[2]
    batch(root, names[2], complete=True)
    assert monitor.resolve_status_path(None) == paths[3]
    batch(root, names[3], complete=True)
    assert monitor.resolve_status_path(None) == paths[3]
    assert all(monitor.batch_complete(path) for path in paths)
