param(
    [Parameter(Mandatory = $true)][string]$PrerequisitePlan,
    [Parameter(Mandatory = $true)][string]$Plan
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$resumeScript = Join-Path $projectRoot "resume_experiments.ps1"

function Get-PlanBatch([string]$PlanPath) {
    $absolutePlan = if ([IO.Path]::IsPathRooted($PlanPath)) { $PlanPath } else { Join-Path $projectRoot $PlanPath }
    $config = Get-Content -LiteralPath $absolutePlan -Raw | ConvertFrom-Json
    if (-not $config.batch_name) { throw "Queued plans require a fixed batch_name." }
    $results = if ([IO.Path]::IsPathRooted($config.results_root)) { $config.results_root } else { Join-Path $projectRoot $config.results_root }
    return Join-Path $results $config.batch_name
}

function Test-QueueBatchComplete([string]$BatchPath) {
    $manifestPath = Join-Path $BatchPath "experiment_manifest.json"
    $statusPath = Join-Path $BatchPath "experiment_status.json"
    if (-not (Test-Path -LiteralPath $manifestPath) -or -not (Test-Path -LiteralPath $statusPath)) { return $false }
    try {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        $status = Get-Content -LiteralPath $statusPath -Raw | ConvertFrom-Json
        if ($status.state -ne "completed" -or $status.failed_experiments -ne 0 -or @($manifest.experiments).Count -eq 0) { return $false }
        foreach ($experiment in $manifest.experiments) {
            $latestPath = Join-Path (Join-Path $BatchPath $experiment.id) "latest_results.json"
            if (-not (Test-Path -LiteralPath $latestPath)) { return $false }
            $latest = Get-Content -LiteralPath $latestPath -Raw | ConvertFrom-Json
            if (-not $latest.completed) { return $false }
        }
        return $true
    } catch { return $false }
}

$prerequisiteBatch = Get-PlanBatch $PrerequisitePlan
$queuedBatch = Get-PlanBatch $Plan
if ($prerequisiteBatch -eq $queuedBatch) { throw "Prerequisite and queued batch must be different." }
Set-Location -LiteralPath $projectRoot

while ($true) {
    if ((Test-Path -LiteralPath (Join-Path $prerequisiteBatch "STOP_REQUESTED")) -or
        (Test-Path -LiteralPath (Join-Path $queuedBatch "STOP_REQUESTED"))) {
        Write-Host "A batch was stopped by the user; the queue will not launch work."
        exit 0
    }
    if (Test-QueueBatchComplete $queuedBatch) { exit 0 }
    $running = Get-CimInstance Win32_Process |
        Where-Object { $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -like '*run_experiments.py*' } |
        Select-Object -First 1
    if ($running) {
        # Background queue wait: the running batch is never stopped or modified.
        Start-Sleep -Seconds 30
        continue
    }
    if (Test-QueueBatchComplete $prerequisiteBatch) {
        & $resumeScript -Plan $Plan
    } else {
        # After a restart/outage, finish the prerequisite before the queued plan.
        & $resumeScript -Plan $PrerequisitePlan
    }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Start-Sleep -Seconds 5
}
