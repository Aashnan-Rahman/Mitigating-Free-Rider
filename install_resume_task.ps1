param(
    [string]$TaskName = "Mitigating Free Rider - Resume Experiments"
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$resumeScript = Join-Path $projectRoot "resume_experiments.ps1"
$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$resumeScript`"" `
    -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Resume the newest unfinished free-rider experiment batch after user logon." `
    -Force | Out-Null

Write-Host "Installed scheduled task: $TaskName"
Write-Host "It runs after $currentUser logs on and writes results\scheduled_resume.log."
