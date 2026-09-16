$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$resultsRoot = Join-Path $projectRoot "results"
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$runner = Join-Path $projectRoot "run_experiments.py"
$log = Join-Path $resultsRoot "scheduled_resume.log"
$seed43Plan = Join-Path $projectRoot "configs\stage1_v8_seed43_plan.json"
$seed43Batch = Join-Path $resultsRoot "batch_stage1_v8_mnist_noniid_fr40_seed43"

function Test-BatchComplete([System.IO.DirectoryInfo]$Batch) {
    $manifestPath = Join-Path $Batch.FullName "experiment_manifest.json"
    if (-not (Test-Path -LiteralPath $manifestPath)) {
        return $false
    }
    try {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        foreach ($experiment in $manifest.experiments) {
            $latestPath = Join-Path $Batch.FullName "$($experiment.id)\latest_results.json"
            if (-not (Test-Path -LiteralPath $latestPath)) {
                return $false
            }
            $latest = Get-Content -LiteralPath $latestPath -Raw | ConvertFrom-Json
            if (-not $latest.completed) {
                return $false
            }
        }
        return $true
    } catch {
        return $false
    }
}

Set-Location -LiteralPath $projectRoot
New-Item -ItemType Directory -Path $resultsRoot -Force | Out-Null
Start-Transcript -Path $log -Append | Out-Null

try {
    if (-not (Test-Path -LiteralPath $python)) {
        throw "Virtual-environment Python was not found: $python"
    }

    $alreadyRunning = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match '^python(w)?\.exe$' -and
            $_.CommandLine -like '*run_experiments.py*'
        } |
        Select-Object -First 1
    if ($alreadyRunning) {
        Write-Host "Experiment runner is already active as PID $($alreadyRunning.ProcessId)."
        exit 0
    }

    $batches = Get-ChildItem -LiteralPath $resultsRoot -Directory -Filter "batch_*" |
        Where-Object {
            (Test-Path -LiteralPath (Join-Path $_.FullName "experiment_manifest.json")) -and
            -not (Test-Path -LiteralPath (Join-Path $_.FullName ".resume_disabled"))
        } |
        Sort-Object LastWriteTime -Descending
    $batch = $batches | Where-Object { -not (Test-BatchComplete $_) } | Select-Object -First 1

    if ($batch) {
        Write-Host "Resuming batch: $($batch.FullName)"
        & $python $runner --resume-batch $batch.FullName --stop-on-error
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }

    if (Test-Path -LiteralPath $seed43Batch) {
        $seed43BatchInfo = Get-Item -LiteralPath $seed43Batch
        if (Test-BatchComplete $seed43BatchInfo) {
            Write-Host "Seed-43 batch is already complete; nothing remains to run."
        } else {
            Write-Host "Seed-43 batch remains incomplete; resuming it."
            & $python $runner --resume-batch $seed43Batch --stop-on-error
            exit $LASTEXITCODE
        }
        exit 0
    }

    Write-Host "Starting the scheduled four-experiment seed-43 batch."
    & $python $runner --plan $seed43Plan --stop-on-error
    exit $LASTEXITCODE
} finally {
    Stop-Transcript -ErrorAction SilentlyContinue | Out-Null
}
