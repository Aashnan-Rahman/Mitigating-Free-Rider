"""Exercise recovery ordering with fake runners; never register Windows tasks."""
import json
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from config import ExperimentConfig
from run_experiments import expand_plan


ROOT = Path(__file__).resolve().parents[1]
SHELL = shutil.which("pwsh") or shutil.which("powershell")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def batch(root, name, complete=False):
    path = root / "results" / name
    write_json(path / "experiment_manifest.json", {"batch_id": name, "experiments": [{"id": "run"}]})
    write_json(path / "experiment_status.json", {
        "state": "completed" if complete else "interrupted", "failed_experiments": 0,
    })
    write_json(path / "run/latest_results.json", {"completed": complete})
    return path


@pytest.fixture
def recovery(tmp_path):
    if not SHELL:
        pytest.skip("PowerShell is needed to exercise the real recovery launcher")
    script = (ROOT / "resume_experiments.ps1").read_text(encoding="utf-8-sig")
    script = script.replace(
        '$python = Join-Path $projectRoot ".venv\\Scripts\\python.exe"',
        '$python = Join-Path $projectRoot "fake_python.ps1"',
    ).replace("Local\\MitigatingFreeRiderBatchRunner", "QueueTest" + uuid.uuid4().hex)
    script = script.replace('$ErrorActionPreference = "Stop"',
                            '$ErrorActionPreference = "Stop"\nfunction Get-CimInstance { param($ClassName) }', 1)
    (tmp_path / "resume_experiments.ps1").write_text(script, encoding="utf-8")
    (tmp_path / "build_paper_v5_v15_4.py").write_text("fake paper marker", encoding="utf-8")
    (tmp_path / "fake_python.ps1").write_text(r'''
$ErrorActionPreference = 'Stop'
$log = Join-Path $PSScriptRoot 'calls.txt'
if ($args[0] -like '*build_paper_v5_v15_4.py') {
    Add-Content -LiteralPath $log -Value 'paper'
    $global:LASTEXITCODE = 0
    return
}
$mode = $args[1]
if ($mode -eq '--plan') {
    $plan = Get-Content -LiteralPath $args[2] -Raw | ConvertFrom-Json
    $name = $plan.batch_name
    $path = Join-Path (Join-Path $PSScriptRoot 'results') $name
} elseif ($mode -eq '--resume-batch') {
    $path = $args[2]
    $name = Split-Path -Leaf $path
} else { throw "Unexpected runner mode: $mode" }
Add-Content -LiteralPath $log -Value ($mode + ':' + $name)
$global:LASTEXITCODE = 0
if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'fail_runner')) {
    $global:LASTEXITCODE = 7
    return
}
New-Item -ItemType Directory -Path (Join-Path $path 'run') -Force | Out-Null
@{batch_id=$name;experiments=@(@{id='run'})} | ConvertTo-Json -Depth 4 |
    Set-Content -LiteralPath (Join-Path $path 'experiment_manifest.json')
$complete = -not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'incomplete_runner'))
@{state=$(if($complete){'completed'}else{'interrupted'});failed_experiments=0} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $path 'experiment_status.json')
@{completed=$complete} | ConvertTo-Json |
    Set-Content -LiteralPath (Join-Path $path 'run/latest_results.json')
''', encoding="utf-8")
    for name in ("cifar", "mnist40", "mnist30", "unrelated"):
        write_json(tmp_path / f"configs/{name}.json", {"batch_name": name, "results_root": "./results"})
    write_json(tmp_path / "configs/scheduled_experiment_queue.json", {
        "plans": [f"configs/{name}.json" for name in ("cifar", "mnist40", "mnist30")],
    })
    return tmp_path


def run_queue(root, name="cifar"):
    return subprocess.run(
        [SHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(root / "resume_experiments.ps1"), "-Plan", f"configs/{name}.json"],
        cwd=root, capture_output=True, text=True, timeout=45,
    )


def calls(root):
    path = root / "calls.txt"
    return path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []


def test_queue_runs_all_batches_in_order_and_builds_cifar_paper_first(recovery):
    result = run_queue(recovery)
    assert result.returncode == 0, result.stdout + result.stderr
    recorded = calls(recovery)
    assert [r for r in recorded if r.startswith("--")] == [
        "--plan:cifar", "--plan:mnist40", "--plan:mnist30",
    ]
    assert recorded.index("--plan:cifar") < recorded.index("paper") < recorded.index("--plan:mnist40")


def test_queue_skips_complete_batches_and_resumes_interrupted_batch(recovery):
    batch(recovery, "cifar", complete=True)
    batch(recovery, "mnist40")
    result = run_queue(recovery)
    assert result.returncode == 0, result.stdout + result.stderr
    assert [r for r in calls(recovery) if r.startswith("--")] == [
        "--resume-batch:mnist40", "--plan:mnist30",
    ]


@pytest.mark.parametrize("stopped", ["cifar", "mnist40"])
def test_stop_marker_blocks_later_batches(recovery, stopped):
    batch(recovery, "cifar", complete=stopped != "cifar")
    path = batch(recovery, stopped)
    (path / "STOP_REQUESTED").write_text("intentional stop", encoding="utf-8")
    result = run_queue(recovery)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not [r for r in calls(recovery) if r.startswith("--")]


@pytest.mark.parametrize("failure", ["incomplete_runner", "fail_runner"])
def test_incomplete_or_failed_prerequisite_never_advances(recovery, failure):
    (recovery / failure).touch()
    result = run_queue(recovery)
    assert result.returncode != 0
    assert [r for r in calls(recovery) if r.startswith("--")] == ["--plan:cifar"]


def test_unrelated_explicit_plan_does_not_join_this_queue(recovery):
    result = run_queue(recovery, "unrelated")
    assert result.returncode == 0, result.stdout + result.stderr
    assert [r for r in calls(recovery) if r.startswith("--")] == ["--plan:unrelated"]


def test_empty_completed_manifest_is_not_a_complete_prerequisite(recovery):
    path = batch(recovery, "cifar", complete=True)
    write_json(path / "experiment_manifest.json", {"experiments": []})
    result = run_queue(recovery)
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls(recovery)[0] == "--resume-batch:cifar"


@pytest.mark.parametrize("share", [30, 40])
def test_mnist_plan_grid_preserves_v154_policy(share):
    plan = json.loads((ROOT / f"configs/v15_4_mnist_seed42_fr{share}_plan.json").read_text())
    cifar = json.loads((ROOT / f"configs/v15_4_cifar10_seed42_fr{share}_plan.json").read_text())
    assert plan["defaults"] == {**cifar["defaults"], "dataset": "mnist"}
    experiments = expand_plan(plan, include_disabled=False)
    assert len(experiments) == 8
    assert len({e["id"] for e in experiments}) == 8
    assert [(e["config"]["distribution"], e["config"]["attack_type"]) for e in experiments] == [
        ("noniid", attack) for attack in ("FR3", "FR4", "FR2", "FR1")
    ] + [("iid", attack) for attack in ("FR4", "FR3", "FR2", "FR1")]
    for experiment in experiments:
        config = ExperimentConfig(**{**plan["defaults"], **experiment["config"]})
        config.validate()
        assert config.free_rider_pct == share / 100
        assert config.seed == 42 and config.num_rounds == 100


def test_persistent_queue_has_requested_prevalence_order():
    queue = json.loads((ROOT / "configs/scheduled_experiment_queue.json").read_text())
    plans = [json.loads((ROOT / name).read_text()) for name in queue["plans"]]
    assert [(p["defaults"]["dataset"], p["defaults"]["free_rider_pct"]) for p in plans] == [
        ("cifar10", .3), ("mnist", .4), ("mnist", .3),
    ]
