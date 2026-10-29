"""Ordered new-seed handoff and watch tests; no real training or task changes."""
import json
import subprocess
from pathlib import Path

import pytest

import monitor
from run_experiments import expand_plan
from test_scheduled_queue import ROOT, SHELL, recovery, run_queue, calls, batch, write_json
from test_seed73_schedule import select_active


def select_queue(root):
    select_active(root)
    for name in ('cifar', 'mnist40'):
        write_json(root / f'configs/{name}.json', dict(batch_name=name, results_root='./results'))
    path = root / 'configs/active_experiment_schedule.json'
    selection = json.loads(path.read_text())
    selection['queue'] = 'configs/followup_queue.json'
    write_json(path, selection)
    write_json(root / selection['queue'], dict(plans=['configs/cifar.json', 'configs/mnist40.json']))


def test_seed43_repeats_exact_grid_and_order_with_only_seed_changed():
    previous = json.loads((ROOT / 'configs/v15_4_cifar10_seed73_fr30_fr40_plan.json').read_text())
    following = json.loads((ROOT / 'configs/v15_4_cifar10_seed43_fr30_fr40_plan.json').read_text())
    assert following['defaults'] == {**previous['defaults'], 'seed': 43}
    for old, new in zip(previous['stages'], following['stages'], strict=True):
        assert new == {**old, 'matrix': {**old['matrix'], 'seed': [43]}}
    entries = expand_plan(following, include_disabled=False)
    assert len(entries) == len({e['id'] for e in entries}) == 16
    assert all(e['config']['seed'] == 43 and e['id'].endswith('_seed43') for e in entries)
    active = json.loads((ROOT / 'configs/active_experiment_schedule.json').read_text())
    queue = json.loads((ROOT / active['queue']).read_text())
    assert queue['plans'][:2] == [active['plan'], 'configs/v15_4_cifar10_seed43_fr30_fr40_plan.json']
    assert active['cpu_threads'] == 6 and active['auto_update_paper'] is False


def test_active_queue_finishes_current_before_followup_and_skips_completed(recovery):
    select_queue(recovery)
    batch(recovery, 'cifar')
    result = run_queue(recovery, 'unrelated')
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls(recovery) == ['--resume-batch:cifar', '--plan:mnist40']
    again = run_queue(recovery)
    assert again.returncode == 0, again.stdout + again.stderr
    assert calls(recovery) == ['--resume-batch:cifar', '--plan:mnist40']


def test_active_queue_recovers_followup_after_restart(recovery):
    select_queue(recovery)
    batch(recovery, 'cifar', complete=True)
    batch(recovery, 'mnist40')
    result = run_queue(recovery)
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls(recovery) == ['--resume-batch:mnist40']


@pytest.mark.parametrize('marker', ['STOP_REQUESTED', 'fail_runner', 'incomplete_runner'])
def test_active_queue_never_advances_on_stop_failure_or_early_return(recovery, marker):
    select_queue(recovery)
    path = batch(recovery, 'cifar')
    ((path if marker == 'STOP_REQUESTED' else recovery) / marker).touch()
    result = run_queue(recovery)
    assert calls(recovery) == ([] if marker == 'STOP_REQUESTED' else ['--resume-batch:cifar'])
    assert (result.returncode == 0) == (marker == 'STOP_REQUESTED')
    assert not (recovery / 'results/mnist40').exists()


@pytest.mark.parametrize('bad_queue', ['missing', 'anchor_missing', 'duplicate'])
def test_bad_active_queue_fails_closed(recovery, bad_queue):
    select_queue(recovery)
    path = recovery / 'configs/followup_queue.json'
    if bad_queue == 'missing':
        path.unlink()
    else:
        write_json(path, dict(plans=(['configs/mnist40.json'] if bad_queue == 'anchor_missing'
                                    else ['configs/cifar.json'] * 2)))
    result = run_queue(recovery)
    assert result.returncode != 0
    assert not calls(recovery)


@pytest.mark.parametrize('condition', ['running', 'failed', 'stopped', 'missing_run_marker'])
def test_watch_does_not_skip_current_prerequisite(tmp_path, monkeypatch, condition):
    select_queue(tmp_path)
    monkeypatch.chdir(tmp_path)
    current = batch(tmp_path, 'cifar', complete=True)
    batch(tmp_path, 'mnist40', complete=True)
    if condition == 'missing_run_marker':
        (current / 'run/latest_results.json').unlink()
    elif condition == 'stopped':
        (current / 'STOP_REQUESTED').touch()
    else:
        write_json(current / 'experiment_status.json', dict(state=condition, failed_experiments=0))
    assert monitor.resolve_status_path(None) == Path('results/cifar/experiment_status.json')
    assert monitor.resolve_status_path(Path('fixed.json')) == Path('fixed.json')


def test_watch_handoff_waits_for_next_status_then_finishes(tmp_path, monkeypatch, capsys):
    select_queue(tmp_path)
    batch(tmp_path, 'cifar', complete=True)
    monkeypatch.chdir(tmp_path)
    assert monitor.resolve_status_path(None) == Path('results/mnist40/experiment_status.json')
    monkeypatch.setattr('sys.argv', ['monitor.py', '--watch'])
    monkeypatch.setattr(monitor, 'clear_screen', lambda: None)
    steps = iter(['running', 'complete'])

    def advance(_):
        step = next(steps)  # Fails if watch gets stuck after complete.
        if step == 'complete':
            batch(tmp_path, 'mnist40', complete=True)
        else:
            write_json(tmp_path / 'results/mnist40/experiment_status.json', dict(state='running'))

    monkeypatch.setattr(monitor.time, 'sleep', advance)
    monitor.main()
    output = capsys.readouterr().out
    assert 'Waiting for status file: results' in output
    assert 'mnist40: current / awaiting recovery' in output and 'mnist40: complete' in output


@pytest.mark.parametrize('finished', [False, True])
def test_powershell_watch_follows_same_queue(recovery, finished):
    select_queue(recovery)
    batch(recovery, 'cifar', complete=finished)
    script = recovery / 'check_status.ps1'
    script.write_text((ROOT / 'check_status.txt').read_text(), encoding='utf-8')
    result = subprocess.run([SHELL, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                             str(script), '-Once'], cwd=recovery, capture_output=True,
                            text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'Batch schedule (in order)' in result.stdout
    if finished:
        assert 'cifar: complete' in result.stdout
        assert 'Waiting for status file:' in result.stdout
        assert 'mnist40' in result.stdout
    else:
        assert 'Status file:' in result.stdout
        assert 'cifar: current / awaiting recovery' in result.stdout
        assert 'mnist40: queued' in result.stdout
