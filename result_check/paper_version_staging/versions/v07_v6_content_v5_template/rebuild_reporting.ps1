$ErrorActionPreference = 'Stop'
foreach ($script in @('build_multiseed_table.ps1','build_baseline_comparison.ps1','build_norm_figure.ps1','build_review_figures.ps1')) {
    & (Join-Path $PSScriptRoot $script)
    if (-not $?) { throw "Reporting regeneration failed: $script" }
}
