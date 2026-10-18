param(
    [string]$TaskName = "Mitigating Free Rider - Resume Experiments",
    [string]$Plan,
    [int]$WatchdogMinutes = 5
)

$ErrorActionPreference = "Stop"
if ($WatchdogMinutes -lt 1) { throw "WatchdogMinutes must be positive." }
$projectRoot = $PSScriptRoot
$resumeScript = Join-Path $projectRoot "resume_experiments.ps1"
$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$preserveUnattended = $existingTask -and $existingTask.Principal.LogonType -in @("Password", "S4U")

$taskArguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$resumeScript`""
if ($Plan) { $taskArguments += " -Plan `"$Plan`"" }
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument $taskArguments `
    -WorkingDirectory $projectRoot
$trigger = @(
    (New-ScheduledTaskTrigger -AtLogOn -User $currentUser),
    (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
        -RepetitionInterval (New-TimeSpan -Minutes $WatchdogMinutes))
)
if ($preserveUnattended) {
    $trigger += New-ScheduledTaskTrigger -AtStartup
}
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
$settings.DisallowStartIfOnBatteries = $false
$settings.StopIfGoingOnBatteries = $false

if ($preserveUnattended) {
    # Updating actions/triggers/settings without replacing the principal keeps
    # the existing unattended account and Windows-managed credentials intact.
    Set-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings | Out-Null
} else {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description "Resume the selected free-rider batch at logon and periodically after interruptions; honour STOP_REQUESTED." `
        -Force | Out-Null
}

Write-Host "Installed scheduled task: $TaskName"
if ($preserveUnattended) {
    Write-Host "Preserved unattended account/credentials. Recovery runs at startup, logon and every $WatchdogMinutes minutes."
} else {
    Write-Host "Interactive recovery runs at logon and every $WatchdogMinutes minutes while logged on."
    Write-Warning "Before-login recovery requires install_startup_resume_task.ps1 and its secure Windows credential prompt."
}
Write-Host "Output: results\scheduled_resume.log"
