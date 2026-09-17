param(
    [string]$TaskName = "Mitigating Free Rider - Resume Experiments",
    [switch]$StartNow
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$resumeScript = Join-Path $projectRoot "resume_experiments.ps1"
$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name

if (-not (Test-Path -LiteralPath $resumeScript)) {
    throw "Resume script was not found: $resumeScript"
}

$credential = Get-Credential `
    -UserName $currentUser `
    -Message "Enter your Windows password so Task Scheduler can resume experiments before login."
if (-not $credential) {
    throw "Task installation was cancelled."
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$resumeScript`"" `
    -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew

$plainPassword = $credential.GetNetworkCredential().Password
try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description "Resume unfinished free-rider experiments at Windows startup before interactive login." `
        -User $credential.UserName `
        -Password $plainPassword `
        -RunLevel Limited `
        -Force | Out-Null
} finally {
    $plainPassword = $null
    Remove-Variable plainPassword -ErrorAction SilentlyContinue
}

Write-Host "Installed startup task: $TaskName"
Write-Host "Account: $($credential.UserName)"
Write-Host "The task can now run before Windows is unlocked."
Write-Host "Output is written to results\scheduled_resume.log."
if ($StartNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "The task has also been started now."
}
