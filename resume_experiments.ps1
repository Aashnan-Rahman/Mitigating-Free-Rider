$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$resultsRoot = Join-Path $projectRoot "results"
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$runner = Join-Path $projectRoot "run_experiments.py"
$log = Join-Path $resultsRoot "scheduled_resume.log"
$scheduledBatches = @(
    [pscustomobject]@{
        Label = "v11 validation: MNIST IID FR1, 40% free riders, seed 42"
        Plan = Join-Path $projectRoot "configs\v11_validation_mnist_iid_fr40_seed42_plan.json"
        Batch = Join-Path $resultsRoot "v11_validation_mnist_iid_fr40_seed42"
        GateBatch = $null
        GateRun = $null
    },
    [pscustomobject]@{
        Label = "v11 validation: MNIST IID FR2, 40% free riders, seed 42"
        Plan = Join-Path $projectRoot "configs\v11_validation_mnist_iid_fr2_seed42_plan.json"
        Batch = Join-Path $resultsRoot "v11_validation_mnist_iid_fr2_seed42"
        GateBatch = Join-Path $resultsRoot "v11_validation_mnist_iid_fr40_seed42"
        GateRun = "v11_mnist_iid_fr1_fr40_seed42"
    },
    [pscustomobject]@{
        Label = "v11 validation: MNIST IID FR3, 40% free riders, seed 42"
        Plan = Join-Path $projectRoot "configs\v11_validation_mnist_iid_fr3_seed42_plan.json"
        Batch = Join-Path $resultsRoot "v11_validation_mnist_iid_fr3_seed42"
        GateBatch = Join-Path $resultsRoot "v11_validation_mnist_iid_fr2_seed42"
        GateRun = "v11_mnist_iid_fr2_fr40_seed42"
    },
    [pscustomobject]@{
        Label = "v11 validation: MNIST IID FR4, 40% free riders, seed 42"
        Plan = Join-Path $projectRoot "configs\v11_validation_mnist_iid_fr4_seed42_plan.json"
        Batch = Join-Path $resultsRoot "v11_validation_mnist_iid_fr4_seed42"
        GateBatch = Join-Path $resultsRoot "v11_validation_mnist_iid_fr3_seed42"
        GateRun = "v11_mnist_iid_fr3_fr40_seed42"
    },
    [pscustomobject]@{
        Label = "v11 full MNIST IID/non-IID, FR1-FR4, 40% free riders, seed 42"
        Plan = Join-Path $projectRoot "configs\v11_full_mnist_iid_noniid_fr40_seed42_plan.json"
        Batch = Join-Path $resultsRoot "v11_full_mnist_iid_noniid_fr40_seed42"
        GateBatch = Join-Path $resultsRoot "v11_validation_mnist_iid_fr4_seed42"
        GateRun = "v11_mnist_iid_fr4_fr40_seed42"
    }
)

function Test-DetectionGate([string]$Batch, [string]$Run) {
    if (-not $Batch -or -not $Run) {
        return $true
    }
    $latestPath = Join-Path $Batch "$Run\latest_results.json"
    $summaryPath = Join-Path $Batch "$Run\detection_summary.csv"
    if (-not (Test-Path -LiteralPath $latestPath) -or
        -not (Test-Path -LiteralPath $summaryPath)) {
        return $false
    }
    $latest = Get-Content -LiteralPath $latestPath -Raw | ConvertFrom-Json
    $summary = Import-Csv -LiteralPath $summaryPath | Select-Object -First 1
    return (
        $latest.completed -and
        [int]$summary.removed_free_riders -eq 40 -and
        [int]$summary.removed_honest_clients -eq 0
    )
}

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

    foreach ($scheduled in $scheduledBatches) {
        if (-not (Test-DetectionGate $scheduled.GateBatch $scheduled.GateRun)) {
            throw "Validation gate failed or is incomplete before: $($scheduled.Label)"
        }
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
