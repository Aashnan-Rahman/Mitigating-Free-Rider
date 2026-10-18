param(
    [string]$TaskName = "Mitigating Free Rider - Resume Experiments",
    [string]$Plan,
    [int]$WatchdogMinutes = 5,
    [switch]$StartNow
)

$ErrorActionPreference = "Stop"
$installerIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$installerPrincipal = [Security.Principal.WindowsPrincipal]::new($installerIdentity)
if (-not $installerPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this startup installer from PowerShell as Administrator. No credential has been requested and the existing task is unchanged."
}
# Start-Process from PowerShell 7 may pass its module search path to Windows
# PowerShell. Load the native security module explicitly for its credential UI.
if ($PSVersionTable.PSEdition -eq "Desktop") {
    Import-Module (Join-Path $PSHOME "Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1") -ErrorAction Stop
}
if ($WatchdogMinutes -lt 1) { throw "WatchdogMinutes must be positive." }
$projectRoot = $PSScriptRoot
$resumeScript = Join-Path $projectRoot "resume_experiments.ps1"
$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name

if (-not (Test-Path -LiteralPath $resumeScript)) {
    throw "Resume script was not found: $resumeScript"
}
if ($Plan) {
    $planPath = if ([IO.Path]::IsPathRooted($Plan)) { $Plan } else { Join-Path $projectRoot $Plan }
    if (-not (Test-Path -LiteralPath $planPath -PathType Leaf)) {
        throw "Experiment plan was not found: $planPath"
    }
    $planConfig = Get-Content -LiteralPath $planPath -Raw | ConvertFrom-Json
    if (-not $planConfig.batch_name) { throw "Startup recovery requires a fixed batch_name." }
}

$credential = Get-Credential `
    -UserName $currentUser `
    -Message "Enter your Windows password so Task Scheduler can resume experiments before login."
if (-not $credential) {
    throw "Task installation was cancelled."
}

$taskArguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$resumeScript`""
if ($Plan) { $taskArguments += " -Plan `"$Plan`"" }
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument $taskArguments `
    -WorkingDirectory $projectRoot
$trigger = @(
    (New-ScheduledTaskTrigger -AtStartup),
    (New-ScheduledTaskTrigger -AtLogOn -User $credential.UserName),
    (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
        -RepetitionInterval (New-TimeSpan -Minutes $WatchdogMinutes))
)
# Give Windows and the local data volume time to become ready after boot.
$trigger[0].Delay = "PT1M"
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew
$settings.DisallowStartIfOnBatteries = $false
$settings.StopIfGoingOnBatteries = $false

$plainPassword = $credential.GetNetworkCredential().Password
try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description "Resume the selected experiment batch at Windows startup and every $WatchdogMinutes minutes without requiring login." `
        -User $credential.UserName `
        -Password $plainPassword `
        -RunLevel Limited `
        -Force | Out-Null
} finally {
    $plainPassword = $null
    Remove-Variable plainPassword -ErrorAction SilentlyContinue
}

$installed = Get-ScheduledTask -TaskName $TaskName
$triggerTypes = @($installed.Triggers | ForEach-Object { $_.CimClass.CimClassName })
if ($installed.Principal.LogonType -ne "Password" -or
    $triggerTypes -notcontains "MSFT_TaskBootTrigger" -or
    $triggerTypes -notcontains "MSFT_TaskLogonTrigger" -or
    -not @($installed.Triggers | Where-Object { $_.Enabled -and $_.Repetition.Interval -eq "PT${WatchdogMinutes}M" }).Count -or
    -not $installed.Settings.Enabled) {
    throw "Task registration did not retain the requested unattended startup/watchdog settings."
}

Write-Host "Installed startup task: $TaskName"
Write-Host "Account: $($credential.UserName)"
Write-Host "Verified Password login mode, startup/logon triggers and periodic recovery."
Write-Host "Recovery is scheduled one minute after startup without requiring login."
Write-Host "Recovery checks also run every $WatchdogMinutes minutes."
Write-Host "Output is written to results\scheduled_resume.log."
if ($StartNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "The task has also been started now."
}
