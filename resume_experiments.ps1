param(
    [string]$Plan = "configs\v15_4_cifar10_seed42_fr30_plan.json",
    [string]$Queue = "configs\scheduled_experiment_queue.json"
)

$ErrorActionPreference = "Stop"

# An explicit active selection overrides historical native queues without changing
# their frozen manifests or the existing Windows task credentials/action.
$activeSchedule = $null
$activeSchedulePath = Join-Path $PSScriptRoot 'configs\active_experiment_schedule.json'
if (Test-Path -LiteralPath $activeSchedulePath) {
    $selection = Get-Content -LiteralPath $activeSchedulePath -Raw | ConvertFrom-Json
    if ($selection.auto_resume) {
        if ($selection.workflow -ne 'v15_detection' -or -not $selection.plan) {
            throw 'Active schedule must name a v15_detection plan.'
        }
        $activeSchedule = $selection
        $Plan = $selection.plan
        $Queue = if ($selection.queue) { [string]$selection.queue } else { '' }
        if ($Queue) {
            $selectedQueuePath = if ([IO.Path]::IsPathRooted($Queue)) { $Queue } else { Join-Path $PSScriptRoot $Queue }
            if (-not (Test-Path -LiteralPath $selectedQueuePath)) {
                throw "Active recovery queue is missing: $selectedQueuePath"
            }
        }
        if ($null -ne $selection.cpu_threads) {
            if ([int]$selection.cpu_threads -lt 1) { throw 'cpu_threads must be positive.' }
            $env:OMP_NUM_THREADS = [string]$selection.cpu_threads
            $env:MKL_NUM_THREADS = [string]$selection.cpu_threads
        }
    }
}

# Native batches run in order, never advancing on a duplicate runner's early
# return, intentional stop, failure, or incomplete checkpoint. Keep the existing
# Task Scheduler credentials/triggers; its watchdog also picks up newly queued
# batches after an already-running (older) launcher invocation finishes.
function Test-NativeBatchComplete($Config, $Batch) {
    $statusPath = Join-Path $Batch 'experiment_status.json'
    if (-not (Test-Path -LiteralPath $statusPath)) { return $false }
    $status = Get-Content -LiteralPath $statusPath -Raw | ConvertFrom-Json
    if ($status.state -ne 'completed' -or @($Config.experiments).Count -eq 0) { return $false }
    foreach ($entry in $Config.experiments) {
        $output = Join-Path $Batch $entry.id
        $horizon = if ($null -ne $entry.rounds) { [int]$entry.rounds } else { [int]$Config.defaults.rounds }
        foreach ($name in @('summary.json', 'status.json', 'round_timings.csv')) {
            if (-not (Test-Path -LiteralPath (Join-Path $output $name))) { return $false }
        }
        $summary = Get-Content -LiteralPath (Join-Path $output 'summary.json') -Raw | ConvertFrom-Json
        $runStatus = Get-Content -LiteralPath (Join-Path $output 'status.json') -Raw | ConvertFrom-Json
        if ($summary.state -ne 'completed' -or $summary.completed_rounds -ne $horizon -or $runStatus.state -ne 'completed') { return $false }
        $rows = @(Import-Csv -LiteralPath (Join-Path $output 'round_timings.csv'))
        if ($rows.Count -ne $horizon) { return $false }
        for ($round = 1; $round -le $horizon; $round++) {
            if ([int]$rows[$round - 1].round -ne $round) { return $false }
        }
    }
    return $true
}
$nativeQueueEnabled = $false
foreach ($nativeQueueRelative in @(
    'configs\fedavg_cifar10_baseline_seed42_fr30_fr40.json',
    'configs\fedavg_mnist_baseline_seed42_fr30_fr40.json',
    'configs\std_dagmm_100_queue.json'
)) {
    if ($activeSchedule) { break }
    $nativeQueuePath = Join-Path $PSScriptRoot $nativeQueueRelative
if (Test-Path -LiteralPath $nativeQueuePath) {
    $nativeQueueConfig = Get-Content -LiteralPath $nativeQueuePath -Raw | ConvertFrom-Json
    if ($nativeQueueConfig.auto_resume) {
        $nativeQueueEnabled = $true
        $nativeBatch = Join-Path (Join-Path $PSScriptRoot $nativeQueueConfig.results_root) $nativeQueueConfig.batch_name
        if (Test-Path -LiteralPath (Join-Path $nativeBatch 'STOP_REQUESTED')) { exit 0 }
        if (Test-NativeBatchComplete $nativeQueueConfig $nativeBatch) { continue }
        $nativePython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
        Set-Location -LiteralPath $PSScriptRoot
        New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot 'results') | Out-Null
        Start-Transcript -Path (Join-Path $PSScriptRoot 'results\std_dagmm_recovery.log') -Append | Out-Null
        try {
            & $nativePython (Join-Path $PSScriptRoot 'run_std_dagmm_batch.py') --plan $nativeQueuePath
            $nativeExitCode = $LASTEXITCODE
        } finally {
            Stop-Transcript -ErrorAction SilentlyContinue | Out-Null
        }
        if ($nativeExitCode -ne 0) { exit $nativeExitCode }
        if (Test-Path -LiteralPath (Join-Path $nativeBatch 'STOP_REQUESTED')) { exit 0 }
        if (-not (Test-NativeBatchComplete $nativeQueueConfig $nativeBatch)) { exit 0 }
    }
}
}
if ($nativeQueueEnabled) { exit 0 }

$projectRoot = $PSScriptRoot
$resultsRoot = Join-Path $projectRoot "results"
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$runner = Join-Path $projectRoot "run_experiments.py"
$log = Join-Path $resultsRoot "scheduled_resume.log"
$queuedSequence = [bool]$activeSchedule
$scheduledBatches = @(
    [pscustomobject]@{
        Label = "v13 priority MNIST IID/non-IID, 40% free riders; hardest cases first"
        Plan = Join-Path $projectRoot "configs\v13_mnist_priority_fr40_plan.json"
        Batch = Join-Path $resultsRoot "v13_mnist_priority_fr40"
        GateBatch = $null
        GateRun = $null
    },
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
    },
    [pscustomobject]@{
        Label = "v12 full MNIST IID/non-IID, FR1-FR4, 40% free riders, seed 42"
        Plan = Join-Path $projectRoot "configs\v12_full_mnist_iid_noniid_fr40_seed42_plan.json"
        Batch = Join-Path $resultsRoot "v12_full_mnist_iid_noniid_fr40_seed42"
        GateBatch = $null
        GateRun = $null
    },
    [pscustomobject]@{
        Label = "v12 full CIFAR-10 IID/non-IID, FR1-FR4, 40% free riders, seed 42"
        Plan = Join-Path $projectRoot "configs\v12_full_cifar10_iid_noniid_fr40_seed42_plan.json"
        Batch = Join-Path $resultsRoot "v12_full_cifar10_iid_noniid_fr40_seed42"
        GateBatch = $null
        GateRun = $null
    }
)

if ($Plan) {
    $planPath = [IO.Path]::GetFullPath($(if ([IO.Path]::IsPathRooted($Plan)) { $Plan } else { Join-Path $projectRoot $Plan }))
    $planPaths = @($planPath)
    if ($Queue) {
        $queuePath = if ([IO.Path]::IsPathRooted($Queue)) { $Queue } else { Join-Path $projectRoot $Queue }
        if (Test-Path -LiteralPath $queuePath) {
            $queueConfig = Get-Content -LiteralPath $queuePath -Raw | ConvertFrom-Json
            $queuePlans = @($queueConfig.plans | ForEach-Object {
                [IO.Path]::GetFullPath($(if ([IO.Path]::IsPathRooted($_)) { $_ } else { Join-Path $projectRoot $_ }))
            })
            if ($queuePlans.Count -eq 0 -or @($queuePlans | Select-Object -Unique).Count -ne $queuePlans.Count) {
                throw "Recovery queue must contain nonempty, unique plan paths."
            }
            if ($activeSchedule -and $planPath -notin $queuePlans) {
                throw "Active plan must be present in its recovery queue."
            }
            for ($index = 0; $index -lt $queuePlans.Count; $index++) {
                if ($queuePlans[$index] -eq $planPath) {
                    $planPaths = @($queuePlans[$index..($queuePlans.Count - 1)])
                    $queuedSequence = $true
                    break
                }
            }
        }
    }
    $scheduledBatches = @($planPaths | ForEach-Object {
        $planConfig = Get-Content -LiteralPath $_ -Raw | ConvertFrom-Json
        if (-not $planConfig.batch_name) { throw "Recovery requires a fixed batch_name in each plan." }
        $workflow = if ($planConfig.workflow) { [string]$planConfig.workflow } else { 'v15_detection' }
        if ($workflow -notin @('v15_detection', 'fedavg_no_detection')) {
            throw "Unsupported workflow in recovery queue: $workflow"
        }
        $planResults = if ([IO.Path]::IsPathRooted($planConfig.results_root)) {
            $planConfig.results_root
        } else { Join-Path $projectRoot $planConfig.results_root }
        [pscustomobject]@{
            Label = $planConfig.batch_name
            Plan = $_
            Batch = Join-Path $planResults $planConfig.batch_name
            Workflow = $workflow
            Config = $planConfig
            GateBatch = $null
            GateRun = $null
        }
    })
    if (@($scheduledBatches.Batch | Select-Object -Unique).Count -ne $scheduledBatches.Count) {
        throw "Recovery queue plans must have distinct batch directories."
    }
}

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
        $statusPath = Join-Path $Batch.FullName "experiment_status.json"
        if (-not (Test-Path -LiteralPath $statusPath)) { return $false }
        $status = Get-Content -LiteralPath $statusPath -Raw | ConvertFrom-Json
        if ($status.state -ne "completed" -or $status.failed_experiments -ne 0 -or
            @($manifest.experiments).Count -eq 0) { return $false }
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

function Update-PaperWhenReady {
    # A replication run must not rebuild or change the manuscript being edited.
    if ($activeSchedule -and -not $activeSchedule.auto_update_paper) { return }
    # CIFAR publication must not wait for the newly queued MNIST executions.
    $paperBuilder = Join-Path $projectRoot "build_paper_v5_v15_4.py"
    if (Test-Path -LiteralPath $paperBuilder) {
        & $python $paperBuilder --update-if-ready --compile
        if ($LASTEXITCODE -ne 0) {
            throw "Paper v5 validation/build failed; recovery will retry without rerunning completed training."
        }
    }
}

Set-Location -LiteralPath $projectRoot
New-Item -ItemType Directory -Path $resultsRoot -Force | Out-Null
$runnerMutex = [System.Threading.Mutex]::new($false, "Local\MitigatingFreeRiderBatchRunner")
$ownsRunnerMutex = $false
$transcriptStarted = $false

try {
    try { $ownsRunnerMutex = $runnerMutex.WaitOne(0) }
    catch [System.Threading.AbandonedMutexException] { $ownsRunnerMutex = $true }
    if (-not $ownsRunnerMutex) {
        Write-Host "Another scheduled launcher owns the batch-runner lock."
        exit 0
    }
    Start-Transcript -Path $log -Append | Out-Null
    $transcriptStarted = $true
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
        if (Test-Path -LiteralPath (Join-Path $scheduled.Batch "STOP_REQUESTED")) {
            Write-Host "Batch stopped by user; automatic resume is blocked: $($scheduled.Label)"
            if ($queuedSequence) { exit 0 }
            continue
        }
        if (-not (Test-DetectionGate $scheduled.GateBatch $scheduled.GateRun)) {
            throw "Validation gate failed or is incomplete before: $($scheduled.Label)"
        }
        if ($scheduled.Workflow -eq 'fedavg_no_detection') {
            if (Test-NativeBatchComplete $scheduled.Config $scheduled.Batch) {
                Write-Host "Scheduled baseline is complete: $($scheduled.Label)"
                continue
            }
            Write-Host "Starting/resuming no-defense baseline: $($scheduled.Label)"
            & $python (Join-Path $projectRoot 'run_std_dagmm_batch.py') --plan $scheduled.Plan
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            if (Test-Path -LiteralPath (Join-Path $scheduled.Batch 'STOP_REQUESTED')) { exit 0 }
            if (-not (Test-NativeBatchComplete $scheduled.Config $scheduled.Batch)) {
                throw "Baseline did not complete; later queued batches will not start: $($scheduled.Label)"
            }
            continue
        }
        if (Test-Path -LiteralPath $scheduled.Batch) {
            $batchInfo = Get-Item -LiteralPath $scheduled.Batch
            if (Test-BatchComplete $batchInfo) {
                Write-Host "Scheduled batch is complete: $($scheduled.Label)"
                Update-PaperWhenReady
                continue
            }
            if (Test-Path -LiteralPath (Join-Path $scheduled.Batch 'experiment_manifest.json')) {
                Write-Host "Resuming scheduled batch: $($scheduled.Label)"
                & $python $runner --resume-batch $scheduled.Batch --stop-on-error
            } else {
                # A power loss may leave just the new directory / an unpublished
                # manifest temp file. Never overwrite unidentified result files.
                $unexpected = @(Get-ChildItem -LiteralPath $scheduled.Batch -Force |
                    Where-Object { $_.Name -notlike '.experiment_manifest.json.*.tmp' })
                if ($unexpected.Count) { throw "Batch has results but no manifest; refusing to overwrite: $($scheduled.Batch)" }
                Write-Host "Retrying interrupted batch initialization: $($scheduled.Label)"
                & $python $runner --plan $scheduled.Plan --stop-on-error
            }
        } else {
            Write-Host "Starting scheduled batch: $($scheduled.Label)"
            & $python $runner --plan $scheduled.Plan --stop-on-error
        }
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
        if ($queuedSequence -and -not (Test-BatchComplete (Get-Item -LiteralPath $scheduled.Batch))) {
            throw "Prerequisite did not complete; later queued batches will not start: $($scheduled.Label)"
        }
        Update-PaperWhenReady
    }

    Update-PaperWhenReady
    Write-Host "All scheduled experiments are complete."
    exit 0
} finally {
    if ($transcriptStarted) { Stop-Transcript -ErrorAction SilentlyContinue | Out-Null }
    if ($ownsRunnerMutex) { $runnerMutex.ReleaseMutex() }
    $runnerMutex.Dispose()
}
