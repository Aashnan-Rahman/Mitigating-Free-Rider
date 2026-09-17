$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$resultsRoot = Join-Path $projectRoot "results"
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$runner = Join-Path $projectRoot "run_experiments.py"
$log = Join-Path $resultsRoot "scheduled_resume.log"
$scheduledBatches = @(
    [pscustomobject]@{
        Label = "30% free riders, seed 42"
        Plan = Join-Path $projectRoot "configs\mnist_noniid_fr30_seed42_plan.json"
        Batch = Join-Path $resultsRoot "mnist_noniid_fr30_seed42"
    },
    [pscustomobject]@{
        Label = "30% free riders, seed 43"
        Plan = Join-Path $projectRoot "configs\mnist_noniid_fr30_seed43_plan.json"
        Batch = Join-Path $resultsRoot "mnist_noniid_fr30_seed43"
    }
)

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

    $batches = Get-ChildItem -LiteralPath $resultsRoot -Directory |
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

    foreach ($scheduled in $scheduledBatches) {
        if (Test-Path -LiteralPath $scheduled.Batch) {
            $batchInfo = Get-Item -LiteralPath $scheduled.Batch
            if (Test-BatchComplete $batchInfo) {
                Write-Host "Scheduled batch is complete: $($scheduled.Label)"
                continue
            }
            Write-Host "Resuming scheduled batch: $($scheduled.Label)"
            & $python $runner --resume-batch $scheduled.Batch --stop-on-error
        } else {
            Write-Host "Starting scheduled batch: $($scheduled.Label)"
            & $python $runner --plan $scheduled.Plan --stop-on-error
        }
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }

    Write-Host "All scheduled 30% seed-42 and seed-43 experiments are complete."
    exit 0
} finally {
    Stop-Transcript -ErrorAction SilentlyContinue | Out-Null
}
