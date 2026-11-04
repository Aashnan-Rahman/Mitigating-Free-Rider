# Keep separately measured timing comparisons separate from the replicated study means.
# Called in the validated build_multiseed_table.ps1 scope.
$timingProvenance = ReadJson (Join-Path $PSScriptRoot 'generated/timing/provenance.json')
foreach ($inputHash in $timingProvenance.inputs.psobject.Properties) {
    Require ((Get-FileHash (Join-Path $RepositoryRoot $inputHash.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -eq $inputHash.Value) "Changed timing input: $($inputHash.Name)"
}
$payloads = @(Import-Csv (Join-Path $PSScriptRoot 'generated/model_payload.csv'))
$lines = [Collections.Generic.List[string]]::new()
@('\begin{table*}[t]\centering\footnotesize', '\caption{Calculated detector payload sizes.}\label{tab:payload}',
'\begin{tabular}{lrrrrrrr}\toprule',
'Model & Parameters & $P$ & $L$ & Two traps (MiB) & Pair payload (KiB) & Index array (MiB) & Counts (MiB) \\ \midrule') | ForEach-Object { $lines.Add($_) }
foreach ($row in $payloads) {
    $traps = 2*(Number $row.float_coordinates)*4/[math]::Pow(1024,2)
    $pairs = 2*100*((Number $row.profile_tensors)+3)*4/1024
    Require ([math]::Abs($traps-(Number $row.two_trap_mib)) -lt 1e-10 -and [math]::Abs($pairs-(Number $row.compact_pair_kib)) -lt 1e-10) 'Payload calculation mismatch'
    $cells = @($(if ($row.dataset -eq 'mnist') { 'MNIST' } else { 'CIFAR-10' }),$row.parameters,$row.float_coordinates,$row.profile_tensors)
    foreach ($value in @($traps,$pairs,(1000*100*8/[math]::Pow(1024,2)),(1000*10*8/[math]::Pow(1024,2)))) { $cells += $value.ToString('F3',$culture) }
    $lines.Add(($cells -join ' & ') + ' \\')
}
@('\bottomrule\end{tabular}\end{table*}') | ForEach-Object { $lines.Add($_) }
WriteTable 'model_payload' $lines
