param([string]$Commit='8519fe180f337486e18dfc752cfedfcef64eaf53')
& (Join-Path $PSScriptRoot 'import_instrumented_timing.ps1') -Dataset mnist -Commit $Commit
