"""New-seed scheduling tests use fake runners and never launch real training."""
import json
from pathlib import Path

import pytest

from config import ExperimentConfig
from run_experiments import expand_plan
from test_scheduled_queue import recovery, run_queue, calls, batch, write_json

ROOT = Path(__file__).resolve().parents[1]


def select_active(root):
    write_json(root/'configs/active_experiment_schedule.json', dict(
        auto_resume=True, workflow='v15_detection', plan='configs/cifar.json',
        auto_update_paper=False, cpu_threads=6))
    # If the active selection fails to override native priority this would try
    # launching the real native runner instead of our isolated legacy fake.
    write_json(root/'configs/fedavg_cifar10_baseline_seed42_fr30_fr40.json', dict(
        auto_resume=True, batch_name='old-native', results_root='results',
        defaults=dict(rounds=2), experiments=[dict(id='run')]))


def test_seed73_plan_has_exact_sixteen_case_grid_and_unchanged_policy():
    plan = json.loads((ROOT/'configs/v15_4_cifar10_seed73_fr30_fr40_plan.json').read_text())
    old = json.loads((ROOT/'configs/v15_4_cifar10_seed42_fr40_plan.json').read_text())
    assert plan['defaults'] == {**old['defaults'], 'seed': 73}
    entries = expand_plan(plan, include_disabled=False)
    assert len(entries) == len({e['id'] for e in entries}) == 16
    actual = set()
    for entry in entries:
        config = ExperimentConfig.from_dict({**plan['defaults'], **entry['config']})
        config.validate()
        assert config.seed == 73 and config.methodology_version == 'swtcp_v15_4'
        assert config.num_rounds == 100 and config.num_clients == 100
        assert config.local_epochs == 3 and config.save_checkpoints and config.checkpoint_keep_last == 2
        assert f'fr{round(config.free_rider_pct * 100)}_seed73' in entry['id']
        actual.add((config.distribution, config.attack_type, config.free_rider_pct))
    assert actual == {(d, a, p) for d in ('iid', 'noniid')
                      for a in ('FR1', 'FR2', 'FR3', 'FR4') for p in (.3, .4)}
    assert [e['config']['distribution'] for e in entries] == ['noniid'] * 8 + ['iid'] * 8
    assert [e['config']['attack_type'] for e in entries[:4]] == ['FR3', 'FR4', 'FR2', 'FR1']


def test_active_selection_overrides_old_task_argument_and_native_queue(recovery):
    select_active(recovery)
    result = run_queue(recovery, 'unrelated')
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls(recovery) == ['--plan:cifar']
    # Explicitly disabling paper updates must preserve the manuscript.
    assert 'paper' not in calls(recovery)


def test_active_selection_resumes_incomplete_and_skips_complete(recovery):
    select_active(recovery)
    batch(recovery, 'cifar')
    result = run_queue(recovery)
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls(recovery) == ['--resume-batch:cifar']
    again = run_queue(recovery)
    assert again.returncode == 0, again.stdout + again.stderr
    assert calls(recovery) == ['--resume-batch:cifar']


def test_active_selection_respects_intentional_stop(recovery):
    select_active(recovery)
    path = batch(recovery, 'cifar')
    (path/'STOP_REQUESTED').touch()
    result = run_queue(recovery)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not calls(recovery)


def test_active_selection_recovers_outage_before_manifest_publication(recovery):
    select_active(recovery)
    path = recovery/'results/cifar'
    path.mkdir(parents=True)
    (path/'.experiment_manifest.json.123.tmp').touch()
    result = run_queue(recovery)
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls(recovery) == ['--plan:cifar']


def test_active_selection_never_overwrites_unidentified_results(recovery):
    select_active(recovery)
    path = recovery/'results/cifar'
    path.mkdir(parents=True)
    (path/'unknown-results.csv').write_text('preserve me')
    result = run_queue(recovery)
    assert result.returncode != 0
    assert not calls(recovery)
    assert (path/'unknown-results.csv').read_text() == 'preserve me'


@pytest.mark.parametrize('marker', ['fail_runner', 'incomplete_runner'])
def test_active_selection_does_not_treat_early_return_as_success(recovery, marker):
    select_active(recovery)
    (recovery/marker).touch()
    result = run_queue(recovery)
    assert result.returncode != 0
    assert calls(recovery) == ['--plan:cifar']


def test_watch_follows_selected_batch_before_first_checkpoint(tmp_path, monkeypatch):
    import monitor
    monkeypatch.chdir(tmp_path)
    write_json(tmp_path/'configs/active_experiment_schedule.json', dict(
        auto_resume=True, workflow='v15_detection', plan='configs/current.json'))
    write_json(tmp_path/'configs/current.json', dict(batch_name='new-seed', results_root='results'))
    write_json(tmp_path/'results/old/experiment_status.json', dict(state='running'))
    assert monitor.resolve_status_path(None) == Path('results/new-seed/experiment_status.json')
    assert monitor.resolve_status_path(Path('explicit.json')) == Path('explicit.json')


def test_watch_displays_seed_share_quarantine_and_removal_counts(tmp_path, capsys):
    import monitor
    status_path = tmp_path/'experiment_status.json'
    write_json(tmp_path/'run/run_config.json', dict(
        removed_free_riders=12, removed_honest_clients=1, missed_free_riders=28))
    monitor.render(dict(batch_id='v15_4_cifar10_seed73_fr30_fr40', total_experiments=16,
        total_rounds=1600, completed_rounds=30, current_experiment='run', experiments=[dict(
            id='run', config=dict(dataset='cifar10', distribution='noniid', attack_type='FR3',
                seed=73, free_rider_pct=.4), progress=dict(round=30, total_rounds=100,
                quarantined_clients=2))]), status_path)
    text = capsys.readouterr().out
    for value in ('seed 73', 'Free riders: 40%', 'Quarantined: 2',
                  'Removed FR / honest: 12 / 1', 'FR remaining: 28'):
        assert value in text


def test_python_watch_survives_failure_until_recovery(monkeypatch):
    import monitor
    states = iter([dict(state='failed'), dict(state='running'), dict(state='completed')])
    rendered = []
    monkeypatch.setattr('sys.argv', ['monitor.py', '--watch'])
    monkeypatch.setattr(monitor, 'resolve_status_path', lambda _: Path('test.json'))
    monkeypatch.setattr(monitor, 'scheduled_status_paths', lambda: [])
    monkeypatch.setattr(monitor, 'read_status', lambda _: next(states))
    monkeypatch.setattr(monitor, 'render', lambda state, _: rendered.append(state['state']))
    monkeypatch.setattr(monitor, 'clear_screen', lambda: None)
    monkeypatch.setattr(monitor.time, 'sleep', lambda _: None)
    monitor.main()
    assert rendered == ['failed', 'running', 'completed']
