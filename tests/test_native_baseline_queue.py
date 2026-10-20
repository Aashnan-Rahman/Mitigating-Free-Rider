"""Exercise the real recovery dispatch using fake runners, never real training."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHELL = shutil.which('pwsh') or shutil.which('powershell')
PLAN_NAMES = [f'fedavg_{dataset}_baseline_seed42_fr30_fr40' for dataset in ('cifar10', 'mnist')]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


@pytest.fixture
def native_queue(tmp_path):
    if not SHELL:
        pytest.skip('PowerShell required')
    script = (ROOT / 'resume_experiments.ps1').read_text(encoding='utf-8-sig')
    script = script.replace("$nativePython = Join-Path $PSScriptRoot '.venv\\Scripts\\python.exe'",
                            "$nativePython = Join-Path $PSScriptRoot 'fake_python.ps1'")
    (tmp_path / 'resume_experiments.ps1').write_text(script, encoding='utf-8')
    for name in PLAN_NAMES:
        write_json(tmp_path / f'configs/{name}.json', dict(auto_resume=True,
            batch_name=name, results_root='results', defaults=dict(rounds=2), experiments=[dict(id='run')]))
    (tmp_path / 'fake_python.ps1').write_text(r'''
$plan = Get-Content -LiteralPath $args[2] -Raw | ConvertFrom-Json
Add-Content -LiteralPath (Join-Path $PSScriptRoot 'calls.txt') -Value $plan.batch_name
$global:LASTEXITCODE = 0
if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'fail')) {
    $global:LASTEXITCODE = 7
    return
}
$batch = Join-Path (Join-Path $PSScriptRoot 'results') $plan.batch_name
New-Item -ItemType Directory -Force -Path (Join-Path $batch 'run') | Out-Null
if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'incomplete')) { return }
@{state='completed'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $batch 'experiment_status.json')
@{state='completed';completed_rounds=2} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $batch 'run/summary.json')
@{state='completed'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $batch 'run/status.json')
"round`n1`n2" | Set-Content -LiteralPath (Join-Path $batch 'run/round_timings.csv')
if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'stop_during_run')) {
    New-Item -ItemType File -Path (Join-Path $batch 'STOP_REQUESTED') | Out-Null
}
''', encoding='utf-8')
    return tmp_path


def dispatch(root):
    return subprocess.run([SHELL, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                           str(root / 'resume_experiments.ps1')], cwd=root,
                          capture_output=True, text=True, timeout=45)


def calls(root):
    path = root / 'calls.txt'
    return path.read_text(encoding='utf-8-sig').splitlines() if path.exists() else []


def complete_batch(root, name):
    batch = root / 'results' / name
    write_json(batch / 'experiment_status.json', dict(state='completed'))
    write_json(batch / 'run/summary.json', dict(state='completed', completed_rounds=2))
    write_json(batch / 'run/status.json', dict(state='completed'))
    (batch / 'run/round_timings.csv').write_text('round\n1\n2\n', encoding='utf-8')
    return batch


def test_native_batches_run_in_order_then_skip_completed(native_queue):
    first = dispatch(native_queue)
    assert first.returncode == 0, first.stdout + first.stderr
    assert calls(native_queue) == PLAN_NAMES
    second = dispatch(native_queue)
    assert second.returncode == 0, second.stdout + second.stderr
    assert calls(native_queue) == PLAN_NAMES


def test_completed_cifar_advances_to_mnist(native_queue):
    complete_batch(native_queue, PLAN_NAMES[0])
    result = dispatch(native_queue)
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls(native_queue) == PLAN_NAMES[1:]


@pytest.mark.parametrize('marker,code', [('fail', 7), ('incomplete', 0), ('stop_during_run', 0)])
def test_native_failure_or_early_return_blocks_successor(native_queue, marker, code):
    (native_queue / marker).touch()
    result = dispatch(native_queue)
    assert result.returncode == code, result.stdout + result.stderr
    assert calls(native_queue) == PLAN_NAMES[:1]


def test_stopped_completed_batch_still_blocks_successor(native_queue):
    batch = complete_batch(native_queue, PLAN_NAMES[0])
    (batch / 'STOP_REQUESTED').touch()
    result = dispatch(native_queue)
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls(native_queue) == []


def test_incomplete_round_grid_does_not_skip_cifar(native_queue):
    batch = complete_batch(native_queue, PLAN_NAMES[0])
    (batch / 'run/round_timings.csv').write_text('round\n1\n1\n', encoding='utf-8')
    (native_queue / 'incomplete').touch()
    result = dispatch(native_queue)
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls(native_queue) == PLAN_NAMES[:1]


def test_mnist_plan_preserves_baseline_grid_and_settings():
    plan = json.loads((ROOT / f'configs/{PLAN_NAMES[1]}.json').read_text())
    cifar = json.loads((ROOT / f'configs/{PLAN_NAMES[0]}.json').read_text())
    assert plan['defaults'] == {**cifar['defaults'], 'dataset': 'mnist'}
    assert plan['auto_resume'] and plan['workflow'] == 'fedavg_no_detection'
    assert len({e['id'] for e in plan['experiments']}) == 16
    assert {(e['distribution'], e['attack'], e['free_rider_pct']) for e in plan['experiments']} == {
        (d, a, p) for d in ('iid', 'noniid') for a in ('FR1', 'FR2', 'FR3', 'FR4') for p in (.3, .4)}
    assert [e['free_rider_pct'] for e in plan['experiments']] == [.4] * 8 + [.3] * 8
    assert [e['distribution'] for e in plan['experiments']] == ['noniid'] * 4 + ['iid'] * 4 + ['noniid'] * 4 + ['iid'] * 4
