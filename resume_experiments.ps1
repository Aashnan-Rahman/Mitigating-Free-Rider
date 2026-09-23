$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$resultsRoot = Join-Path $projectRoot "results"
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$runner = Join-Path $projectRoot "run_experiments.py"
$log = Join-Path $resultsRoot "scheduled_resume.log"
$scheduledBatches = @(
    [pscustomobject]@{
        Label = "FR4, 40% free riders, seed 44"
        Plan = Join-Path $projectRoot "configs\mnist_noniid_fr40_seed44_fr4_plan.json"
        Batch = Join-Path $resultsRoot "mnist_noniid_fr40_seed44"
    },
    [pscustomobject]@{
        Label = "FR4, 40% free riders, seed 45"
        Plan = Join-Path $projectRoot "configs\mnist_noniid_fr40_seed45_fr4_plan.json"
        Batch = Join-Path $resultsRoot "mnist_noniid_fr40_seed45"
    },
    [pscustomobject]@{
        Label = "FR4, 40% free riders, seed 46"
        Plan = Join-Path $projectRoot "configs\mnist_noniid_fr40_seed46_fr4_plan.json"
        Batch = Join-Path $resultsRoot "mnist_noniid_fr40_seed46"
    },
    [pscustomobject]@{
        Label = "CIFAR-10 IID, FR1-FR4, 40% free riders, seed 42"
        Plan = Join-Path $projectRoot "configs\cifar10_iid_fr40_seed42_plan.json"
        Batch = Join-Path $resultsRoot "cifar10_iid_fr40_seed42"
    },
    [pscustomobject]@{
        Label = "CIFAR-10 non-IID, FR1-FR4, 40% free riders, seed 43"
        Plan = Join-Path $projectRoot "configs\cifar10_noniid_fr40_seed43_plan.json"
        Batch = Join-Path $resultsRoot "cifar10_noniid_fr40_seed43"
    },
    [pscustomobject]@{
        Label = "CIFAR-10 IID, FR1-FR4, 40% free riders, seed 43"
        Plan = Join-Path $projectRoot "configs\cifar10_iid_fr40_seed43_plan.json"
        Batch = Join-Path $resultsRoot "cifar10_iid_fr40_seed43"
    },
    [pscustomobject]@{
        Label = "CIFAR-10 non-IID, FR1-FR4, 40% free riders, seed 42"
        Plan = Join-Path $projectRoot "configs\cifar10_noniid_fr40_seed42_plan.json"
        Batch = Join-Path $resultsRoot "cifar10_noniid_fr40_seed42"
    },
    [pscustomobject]@{
        Label = "MNIST FRIDA-loss and FRAD, IID/non-IID, FR1-FR4, 40% free riders, seed 42"
        Plan = Join-Path $projectRoot "configs\mnist_baselines_fr40_seed42_plan.json"
        Batch = Join-Path $resultsRoot "mnist_baselines_fr40_seed42"
    },
    [pscustomobject]@{
        Label = "MNIST non-IID, FR1-FR4, 30% free riders, seed 42 recovery"
        Plan = Join-Path $projectRoot "configs\mnist_noniid_fr30_seed42_plan.json"
        Batch = Join-Path $resultsRoot "mnist_noniid_fr30_seed42"
    },
    [pscustomobject]@{
        Label = "CIFAR-10 IID/non-IID, FR1-FR4, 30% free riders, seeds 42 and 43"
        Plan = Join-Path $projectRoot "configs\cifar10_fr30_seeds42_43_plan.json"
        Batch = Join-Path $resultsRoot "cifar10_fr30_seeds42_43"
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

    $scheduledPaths = @($scheduledBatches | ForEach-Object { $_.Batch })
    $batches = Get-ChildItem -LiteralPath $resultsRoot -Directory |
        Where-Object {
            (Test-Path -LiteralPath (Join-Path $_.FullName "experiment_manifest.json")) -and
            -not (Test-Path -LiteralPath (Join-Path $_.FullName ".resume_disabled")) -and
            $_.FullName -notin $scheduledPaths
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

    Write-Host "All scheduled experiments are complete."
    exit 0
} finally {
    Stop-Transcript -ErrorAction SilentlyContinue | Out-Null
}
