$ErrorActionPreference = 'Stop'
foreach ($script in @('import_completed_baselines.ps1','build_multiseed_table.ps1','build_baseline_comparison.ps1','build_review_figures.ps1','build_time_target.ps1','check_review2_evidence.ps1')) {
    & (Join-Path $PSScriptRoot $script)
    if (-not $?) { throw "Reporting regeneration failed: $script" }
}
