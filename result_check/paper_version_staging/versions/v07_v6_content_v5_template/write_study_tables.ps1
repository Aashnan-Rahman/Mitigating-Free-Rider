# Invoked by build_multiseed_table.ps1 after validation of every replication.
function WriteTable([string]$Name, $Content) {
    [IO.File]::WriteAllLines((Join-Path $PSScriptRoot "generated/$Name.tex"), [string[]]$Content, [Text.UTF8Encoding]::new($false))
}
function AverageField($Runs, [string]$Field) { FormatNumber (Mean @($Runs | ForEach-Object { $_.$Field })) }
$detailRows = [Collections.Generic.List[object]]::new()
foreach ($dataset in $datasets) {
    foreach ($split in @('iid','noniid')) {
        foreach ($share in @(30,40)) {
            foreach ($attack in $attacks) {
                $runs = @($records | Where-Object { $_.dataset -eq $dataset -and $_.split -eq $split -and $_.share -eq $share -and $_.attack -eq $attack })
                Require ($runs.Count -eq 3) 'Incomplete detailed table cell'
                $row = [ordered]@{dataset=$dataset;split=$split;share=$share;attack=$attack}
                foreach ($field in @('tp','fp','fn','completion_round','final_accuracy','final_honest_candidates','honest_ever_quarantined','honest_quarantine_rounds','honest_trap_rounds','honest_nontrap_excluded','honest_excluded_pct')) {
                    $row[$field] = Mean @($runs | ForEach-Object { $_.$field })
                }
                $detailRows.Add([pscustomobject]$row)
            }
        }
    }
}
$detailRows | Export-Csv (Join-Path $exportDir 'attack_means.csv') -NoTypeInformation -Encoding utf8

$safetyRows = @($detailRows | Where-Object { $_.attack -eq 'FR3' -or $_.fp -gt 0 -or $_.honest_ever_quarantined -gt 0 })
$safetyRows | Export-Csv (Join-Path $exportDir 'table2_means.csv') -NoTypeInformation -Encoding utf8
$lines = [Collections.Generic.List[string]]::new()
@('\begin{table*}[t]', '\centering\footnotesize\setlength{\tabcolsep}{4pt}',
'\caption{Honest-client screening and exclusion.}\label{tab:safety}',
'\begin{tabular}{lll l rrr rrr r}', '\toprule',
'\multirow{2}{*}{Dataset} & \multirow{2}{*}{Partition} & \multirow{2}{*}{FR (\%)} & \multirow{2}{*}{Attack} & \multicolumn{3}{c}{Honest clients} & \multicolumn{3}{c}{Excluded client rounds} & \multirow{2}{*}{\shortstack{All excluded\\(\%)}} \\',
'\cmidrule(lr){5-7}\cmidrule(lr){8-10}',
'& & & & Candidates & Removed & Quarantined & Quarantine & Trap & Non-trap & \\', '\midrule') | ForEach-Object { $lines.Add($_) }
foreach ($dataset in $datasets) {
    if ($dataset -eq 'cifar10') { $lines.Add('\midrule') }
    $datasetRows = @($safetyRows | Where-Object dataset -eq $dataset)
    $datasetLabel = if ($dataset -eq 'mnist') { 'MNIST' } else { 'CIFAR-10' }
    $firstDatasetRow = $true
    foreach ($split in @('iid','noniid')) {
        $partitionRows = @($datasetRows | Where-Object split -eq $split)
        $partitionLabel = if ($split -eq 'iid') { 'IID' } else { 'Non-IID' }
        $firstPartitionRow = $true
        $previousShare = -1
        foreach ($row in $partitionRows) {
            $shareRows = @($partitionRows | Where-Object share -eq $row.share).Count
            $shareCell = if ($previousShare -eq $row.share) { '' } elseif ($shareRows -gt 1) { '\multirow{' + $shareRows + '}{*}{' + $row.share + '}' } else { [string]$row.share }
            $cells = @(
                $(if ($firstDatasetRow) { '\multirow{' + $datasetRows.Count + '}{*}{' + $datasetLabel + '}' } else { '' }),
                $(if ($firstPartitionRow) { '\multirow{' + $partitionRows.Count + '}{*}{' + $partitionLabel + '}' } else { '' }),
                $shareCell, $row.attack
            )
            foreach ($field in @('final_honest_candidates','fp','honest_ever_quarantined','honest_quarantine_rounds','honest_trap_rounds','honest_nontrap_excluded','honest_excluded_pct')) { $cells += FormatNumber $row.$field }
            $lines.Add(($cells -join ' & ') + ' \\')
            $firstDatasetRow = $false; $firstPartitionRow = $false
            $previousShare = $row.share
        }
    }
}
@('\bottomrule','\end{tabular}','\end{table*}') | ForEach-Object { $lines.Add($_) }
WriteTable 'safety' $lines

$costRows = [Collections.Generic.List[object]]::new()
$lines = [Collections.Generic.List[string]]::new()
@('\begin{table*}[t]', '\centering\footnotesize\setlength{\tabcolsep}{4pt}',
'\caption{CPU execution time and process memory.}\label{tab:cost}',
'\begin{tabular}{llrrrr}', '\toprule',
'Dataset & Partition & FR (\%) & s/round: mean [range] & Peak RSS GiB: mean [range] & min/run \\', '\midrule') | ForEach-Object { $lines.Add($_) }
foreach ($dataset in $datasets) {
    if ($dataset -eq 'cifar10') { $lines.Add('\midrule') }
    $datasetRowIndex = 0
    foreach ($split in @('iid','noniid')) {
        $splitRowIndex = 0
        foreach ($share in @(30,40)) {
            $runs = @($records | Where-Object { $_.dataset -eq $dataset -and $_.split -eq $split -and $_.share -eq $share })
            $row = [ordered]@{dataset=$dataset;split=$split;share=$share}
            foreach ($field in @('mean_round_seconds','peak_rss_gib','wall_minutes')) {
                $row[$field] = Mean @($runs | ForEach-Object { $_.$field })
                $row["${field}_min"] = ($runs | Measure-Object -Property $field -Minimum).Minimum
                $row["${field}_max"] = ($runs | Measure-Object -Property $field -Maximum).Maximum
            }
            $costRows.Add([pscustomobject]$row)
            $datasetLabel = if ($dataset -eq 'mnist') { 'MNIST' } else { 'CIFAR-10' }
            $splitLabel = if ($split -eq 'iid') { 'IID' } else { 'Non-IID' }
            $cells = @($(if ($datasetRowIndex -eq 0) { "\multirow{4}{*}{$datasetLabel}" } else { '' }), $(if ($splitRowIndex -eq 0) { "\multirow{2}{*}{$splitLabel}" } else { '' }), [string]$share)
            foreach ($field in @('mean_round_seconds','peak_rss_gib')) {
                $cells += (FormatNumber $row[$field]) + ' [' + (FormatNumber $row["${field}_min"]) + '--' + (FormatNumber $row["${field}_max"]) + ']'
            }
            $cells += FormatNumber $row.wall_minutes
            $lines.Add(($cells -join ' & ') + ' \\')
            $datasetRowIndex++; $splitRowIndex++
        }
    }
}
@('\bottomrule','\end{tabular}','\end{table*}') | ForEach-Object { $lines.Add($_) }
WriteTable 'cost' $lines
$costRows | Export-Csv (Join-Path $exportDir 'table3_means.csv') -NoTypeInformation -Encoding utf8

$lines = [Collections.Generic.List[string]]::new()
foreach ($dataset in $datasets) {
    $datasetLabel = if ($dataset -eq 'mnist') { 'MNIST' } else { 'CIFAR-10' }
    @('\begin{table*}[t]', '\centering\footnotesize\setlength{\tabcolsep}{4pt}',
        ('\caption{Detection and utility by attack on ' + $datasetLabel + '.}\label{tab:detail-' + $dataset + '}'),
        '\begin{tabular}{rllrrrrrrrr}', '\toprule',
        'FR (\%) & Partition & Attack & TP & FP & FN & $t_{\rm all}$ & Accuracy (\%) & $C_H$ & $Q_H$ & $q_H$ \\', '\midrule'
    ) | ForEach-Object { $lines.Add($_) }
    foreach ($share in @(30,40)) {
        if ($share -eq 40) { $lines.Add('\midrule') }
        foreach ($split in @('iid','noniid')) {
            foreach ($row in @($detailRows | Where-Object { $_.dataset -eq $dataset -and $_.share -eq $share -and $_.split -eq $split })) {
                $cells = @([string]$share, $(if ($split -eq 'iid') { 'IID' } else { 'Non-IID' }), $row.attack)
                foreach ($field in @('tp','fp','fn','completion_round')) { $cells += FormatNumber $row.$field }
                $cells += FormatNumber (100*$row.final_accuracy)
                foreach ($field in @('final_honest_candidates','honest_ever_quarantined','honest_quarantine_rounds')) { $cells += FormatNumber $row.$field }
                $lines.Add(($cells -join ' & ') + ' \\')
            }
        }
    }
    @('\bottomrule','\end{tabular}','\end{table*}') | ForEach-Object { $lines.Add($_) }
}
WriteTable 'details' $lines
