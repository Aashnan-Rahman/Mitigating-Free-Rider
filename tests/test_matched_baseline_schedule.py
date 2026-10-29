"""Matched baseline plans and mixed-workflow recovery; never train a model."""
import json
import subprocess
from pathlib import Path

import pytest

import monitor
from run_experiments import expand_plan
from run_std_dagmm_batch import command_for
from test_scheduled_queue import ROOT, SHELL, recovery, run_queue, calls, batch, write_json

QUEUE = 'configs/replication_with_baselines_seed73_seed43_queue.json'


def read_plan(path):
    return json.loads((ROOT / path).read_text())


def test_64_baseline_cases_match_detection_configs_and_use_only_fedavg(tmp_path):
    queue = read_plan(QUEUE)
    previous = read_plan('configs/v15_4_replication_seed73_seed43_queue.json')
    assert queue['plans'][:4] == previous['plans']
    plans = [read_plan(p) for p in queue['plans']]
    assert len(plans) == len({p['batch_name'] for p in plans}) == 8
    assert [(p['defaults']['dataset'], p['defaults']['seed']) for p in plans[4:]] == [
        ('cifar10', 73), ('cifar10', 43), ('mnist', 73), ('mnist', 43)]
    all_ids = []
    for plan in plans[4:]:
        cfg = plan['defaults']
        old = read_plan(f"configs/fedavg_{cfg['dataset']}_baseline_seed42_fr30_fr40.json")
        assert cfg == {**old['defaults'], 'seed': cfg['seed']}
        assert plan['workflow'] == 'fedavg_no_detection' and plan['auto_resume']
        assert cfg['clients'] == cfg['rounds'] == 100 and cfg['local_epochs'] == 3 and cfg['threads'] == 6
        expected = read_plan(f"configs/v15_4_{cfg['dataset']}_seed{cfg['seed']}_fr30_fr40_plan.json")
        detection = expand_plan(expected, include_disabled=False)
        assert [(e['distribution'], e['attack'], e['free_rider_pct']) for e in plan['experiments']] == [
            (e['config']['distribution'], e['config']['attack_type'], e['config']['free_rider_pct']) for e in detection]
        for entry in plan['experiments']:
            command = command_for(plan, entry, tmp_path / entry['id'])
            assert Path(command[1]).name == 'run_fedavg_baseline.py'
            assert not any('detector' in arg or 'trap' in arg for arg in command)
            all_ids.append(entry['id'])
    assert len(all_ids) == len(set(all_ids)) == 64


@pytest.fixture
def mixed_queue(recovery):
    queue = read_plan(QUEUE)
    write_json(recovery / QUEUE, queue)
    write_json(recovery / 'configs/active_experiment_schedule.json', dict(
        auto_resume=True, workflow='v15_detection', plan=queue['plans'][0], queue=QUEUE,
        auto_update_paper=False, cpu_threads=6))
    names = []
    for path in queue['plans']:
        real = read_plan(path)
        names.append(real['batch_name'])
        fake = dict(batch_name=real['batch_name'], results_root='results')
        if real.get('workflow') == 'fedavg_no_detection':
            fake.update(workflow='fedavg_no_detection', defaults=dict(rounds=2), experiments=[dict(id='run')])
        write_json(recovery / path, fake)
    # Extend the existing legacy fake with native baseline evidence.
    fake = recovery / 'fake_python.ps1'
    original = fake.read_text()
    fake.write_text(r'''
if ($args[0] -like '*run_std_dagmm_batch.py') {
    $ErrorActionPreference = 'Stop'
    $plan = Get-Content -LiteralPath $args[2] -Raw | ConvertFrom-Json
    Add-Content -LiteralPath (Join-Path $PSScriptRoot 'calls.txt') -Value ('native:' + $plan.batch_name)
    $global:LASTEXITCODE = 0
    if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'fail_native')) {
        $global:LASTEXITCODE = 7
        return
    }
    $batch = Join-Path (Join-Path $PSScriptRoot 'results') $plan.batch_name
    $output = Join-Path $batch 'run'
    New-Item -ItemType Directory -Force -Path $output | Out-Null
    $plan | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $batch 'experiment_manifest.json')
    @{state='completed';failed_experiments=0} | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $batch 'experiment_status.json')
    @{state='completed';completed_rounds=2} | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $output 'summary.json')
    @{state='completed'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $output 'status.json')
    $rounds = if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'incomplete_native')) { "round`n1`n1" } else { "round`n1`n2" }
    $rounds | Set-Content -LiteralPath (Join-Path $output 'round_timings.csv')
    if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'stop_native')) {
        New-Item -ItemType File -Path (Join-Path $batch 'STOP_REQUESTED') | Out-Null
    }
    return
}
''' + original, encoding='utf-8')
    return recovery, names


def complete_native(root, name):
    path = root / 'results' / name
    write_json(path / 'experiment_manifest.json', dict(workflow='fedavg_no_detection',
        defaults=dict(rounds=2), experiments=[dict(id='run')]))
    write_json(path / 'experiment_status.json', dict(state='completed', failed_experiments=0))
    write_json(path / 'run/summary.json', dict(state='completed', completed_rounds=2))
    write_json(path / 'run/status.json', dict(state='completed'))
    (path / 'run/round_timings.csv').write_text('round\n1\n2\n', encoding='utf-8')
    return path


def test_detection_finishes_then_all_baselines_run_and_completed_cases_skip(mixed_queue):
    root, names = mixed_queue
    for name in names[:3]:
        batch(root, name, complete=True)
    batch(root, names[3])
    result = run_queue(root)
    assert result.returncode == 0, result.stdout + result.stderr
    expected = [f'--resume-batch:{names[3]}'] + [f'native:{n}' for n in names[4:]]
    assert calls(root) == expected
    again = run_queue(root)
    assert again.returncode == 0, again.stdout + again.stderr
    assert calls(root) == expected and 'paper' not in calls(root)


def test_restart_skips_completed_baseline_and_resumes_incomplete_baseline(mixed_queue):
    root, names = mixed_queue
    for name in names[:4]:
        batch(root, name, complete=True)
    complete_native(root, names[4])
    partial = complete_native(root, names[5])
    (partial / 'run/round_timings.csv').write_text('round\n1\n', encoding='utf-8')
    result = run_queue(root)
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls(root) == [f'native:{n}' for n in names[5:]]


@pytest.mark.parametrize('marker', ['STOP_REQUESTED', 'fail_runner', 'incomplete_runner'])
def test_unfinished_detection_blocks_baselines(mixed_queue, marker):
    root, names = mixed_queue
    for name in names[:3]:
        batch(root, name, complete=True)
    path = batch(root, names[3])
    ((path if marker == 'STOP_REQUESTED' else root) / marker).touch()
    result = run_queue(root)
    assert (result.returncode == 0) == (marker == 'STOP_REQUESTED')
    assert not any(c.startswith('native:') for c in calls(root))


@pytest.mark.parametrize('marker', ['fail_native', 'incomplete_native', 'stop_native'])
def test_native_failure_early_return_or_stop_blocks_later_baselines(mixed_queue, marker):
    root, names = mixed_queue
    for name in names[:4]:
        batch(root, name, complete=True)
    (root / marker).touch()
    result = run_queue(root)
    assert (result.returncode == 0) == (marker == 'stop_native')
    assert calls(root) == [f'native:{names[4]}']
    assert not any((root / 'results' / name).exists() for name in names[5:])


@pytest.mark.parametrize('bad_evidence', ['missing_csv', 'duplicate_round', 'stopped'])
def test_watch_blocks_on_incomplete_native_evidence(mixed_queue, monkeypatch, bad_evidence):
    root, names = mixed_queue
    for name in names[:4]:
        batch(root, name, complete=True)
    path = complete_native(root, names[4])
    if bad_evidence == 'missing_csv':
        (path / 'run/round_timings.csv').unlink()
    elif bad_evidence == 'duplicate_round':
        (path / 'run/round_timings.csv').write_text('round\n1\n1\n', encoding='utf-8')
    else:
        (path / 'STOP_REQUESTED').touch()
    monkeypatch.chdir(root)
    assert monitor.resolve_status_path(None) == Path('results') / names[4] / 'experiment_status.json'


def test_python_and_powershell_watch_advance_after_completed_baseline(mixed_queue, monkeypatch):
    root, names = mixed_queue
    for name in names[:4]:
        batch(root, name, complete=True)
    complete_native(root, names[4])
    monkeypatch.chdir(root)
    assert monitor.resolve_status_path(None) == Path('results') / names[5] / 'experiment_status.json'
    script = root / 'check_status.ps1'
    script.write_text((ROOT / 'check_status.txt').read_text(), encoding='utf-8')
    result = subprocess.run([SHELL, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                             str(script), '-Once'], cwd=root, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f'{names[4]}: complete' in result.stdout
    assert f'{names[5]}: current / awaiting recovery' in result.stdout
    assert 'Waiting for status file:' in result.stdout
