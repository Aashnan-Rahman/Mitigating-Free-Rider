$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
$outputPath = Join-Path $PSScriptRoot 'analysis/std_dagmm_cifar10_native_seed42_fr40_FR3_noniid'
$runArguments = @('run_std_dagmm_native.py', '--dataset', 'cifar10', '--rounds', '10', '--clients', '100', '--distribution', 'noniid', '--attack', 'FR3', '--free-rider-pct', '.4', '--seed', '42', '--threads', '6', '--detector-epochs', '5', '--detector-batch', '20', '--local-epochs', '3', '--output', $outputPath)
if (Test-Path -LiteralPath (Join-Path $outputPath 'latest_checkpoint.pt')) {
    $runArguments += '--resume'
}
& $pythonPath @runArguments
if ($LASTEXITCODE -ne 0) { throw 'CIFAR timing run failed; inspect console and status logs.' }
& $pythonPath analyze_std_dagmm_native.py $outputPath
if ($LASTEXITCODE -ne 0) { throw 'CIFAR analysis failed.' }
& $pythonPath compare_std_dagmm_datasets.py
if ($LASTEXITCODE -ne 0) { throw 'Dataset comparison failed.' }
