# Keep separately measured timing comparisons separate from the replicated study means.
# Called in the validated build_multiseed_table.ps1 scope.
$timingProvenance = ReadJson (Join-Path $PSScriptRoot 'generated/timing/provenance.json')
foreach ($inputHash in $timingProvenance.inputs.psobject.Properties) {
    Require ((Get-FileHash (Join-Path $RepositoryRoot $inputHash.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -eq $inputHash.Value) "Changed timing input: $($inputHash.Name)"
}
$measurements = @{}
foreach ($dataset in $datasets) {
    $path = Join-Path $RepositoryRoot "results/std_dagmm_100_seed42_fr40/std_dagmm_${dataset}_noniid_FR3_seed42/round_timings.csv"
    $measurements[$dataset] = @(Import-Csv $path)
    Require ($measurements[$dataset].Count -eq 100) 'Incomplete STD timing horizon'
}
$lines = [Collections.Generic.List[string]]::new()
@('\begin{table*}[t]\centering\footnotesize',
'\caption{STD-DAGMM component execution time (s per round).}\label{tab:std-segments}',
'\begin{tabular}{lrr}\toprule Component & MNIST & CIFAR-10 \\ \midrule') | ForEach-Object { $lines.Add($_) }
foreach ($component in @(
    @('Client training','honest_training_seconds'), @('Simulated FR response','fabrication_seconds'),
    @('Server aggregation','aggregation_seconds'), @('Global evaluation','evaluation_seconds'),
    @('Update preparation','preparation_seconds'), @('Detector fitting','fit_seconds'),
    @('Detector scoring','inference_seconds'), @('Flag decision','decision_seconds'),
    @('All detector work','detector_seconds'), @('Combined compute','round_compute_seconds')
)) {
    $cells = @($component[0])
    foreach ($dataset in $datasets) {
        $values = @($measurements[$dataset] | ForEach-Object { Number $_.($component[1]) })
        $cells += (Mean $values).ToString('F3',$culture) + ' $\pm$ ' + (SampleSd $values).ToString('F3',$culture)
    }
    $lines.Add(($cells -join ' & ') + ' \\')
}
@('\bottomrule\end{tabular}\end{table*}', '\begin{table*}[t]\centering\footnotesize',
'\caption{Native-workflow execution time over 100 rounds.}\label{tab:timing-horizons}',
'\begin{tabular}{llrrr}\toprule Dataset & Workflow / horizon & Rounds & Mean s/round & Sum (min) \\ \midrule') | ForEach-Object { $lines.Add($_) }
foreach ($dataset in $datasets) {
    $datasetLabel = if ($dataset -eq 'mnist') { 'MNIST' } else { 'CIFAR-10' }
    $ours = $records | Where-Object { $_.dataset -eq $dataset -and $_.split -eq 'noniid' -and $_.share -eq 40 -and $_.attack -eq 'FR3' -and $_.seed -eq 42 }
    $meanStd = Mean @($measurements[$dataset] | ForEach-Object { Number $_.round_compute_seconds })
    $lines.Add($datasetLabel + ' & Ours, measured full horizon & 100 & ' + (FormatNumber $ours.mean_round_seconds) + ' & ' + (FormatNumber ($ours.mean_round_seconds*100/60)) + ' \\')
    $lines.Add($datasetLabel + ' & STD-DAGMM, measured full horizon & 100 & ' + (FormatNumber $meanStd) + ' & ' + (FormatNumber ($meanStd*100/60)) + ' \\')
}
@('\bottomrule\end{tabular}\end{table*}', '\begin{table*}[t]\centering\footnotesize',
'\caption{Execution time by round category.}\label{tab:timing-phases}',
'\begin{tabular}{llrrr}\toprule Dataset & Round category & Count & Within-category mean (s) & Contribution (s/round) \\ \midrule') | ForEach-Object { $lines.Add($_) }
$phases = @(Import-Csv (Join-Path $PSScriptRoot 'generated/timing/phases.csv'))
$phaseNames = @{warmup='Warm-up';probe='Probe without cycle decision';full_cycle='Full-cycle decision';single_audit='Single audit';ordinary='Ordinary'}
foreach ($dataset in $datasets) {
    $datasetLabel = if ($dataset -eq 'mnist') { 'MNIST' } else { 'CIFAR-10' }
    $ours = $records | Where-Object { $_.dataset -eq $dataset -and $_.split -eq 'noniid' -and $_.share -eq 40 -and $_.attack -eq 'FR3' -and $_.seed -eq 42 }
    $phaseRows = @($phases | Where-Object dataset -eq $dataset)
    Require (($phaseRows | Measure-Object rounds -Sum).Sum -eq 100) 'Invalid phase coverage'
    Require ([math]::Abs(($phaseRows | Measure-Object total_s -Sum).Sum/100-$ours.mean_round_seconds) -lt 1e-7) 'Invalid phase sum'
    foreach ($phase in $phaseRows) {
        $lines.Add(($datasetLabel, $phaseNames[$phase.phase], $phase.rounds, (FormatNumber (Number $phase.mean_within_phase_s)), (FormatNumber (Number $phase.amortized_s)) -join ' & ') + ' \\')
    }
}
@('\bottomrule\end{tabular}\end{table*}') | ForEach-Object { $lines.Add($_) }
WriteTable 'timing_tables' $lines

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
