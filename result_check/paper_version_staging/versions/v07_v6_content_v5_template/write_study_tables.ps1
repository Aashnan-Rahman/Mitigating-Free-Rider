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
                foreach ($field in @('fp','honest_ever_quarantined')) {
                    $row["${field}_min"]=($runs|Measure-Object -Property $field -Minimum).Minimum
                    $row["${field}_max"]=($runs|Measure-Object -Property $field -Maximum).Maximum
                }
                $detailRows.Add([pscustomobject]$row)
            }
        }
    }
}
$detailRows | Export-Csv (Join-Path $exportDir 'attack_means.csv') -NoTypeInformation -Encoding utf8

$safetyRows = @($detailRows)
$safetyRows | Export-Csv (Join-Path $exportDir 'table2_means.csv') -NoTypeInformation -Encoding utf8
$lines = [Collections.Generic.List[string]]::new()
@('\begin{table*}[!t]', '\centering\footnotesize\setlength{\tabcolsep}{3.5pt}',
'\caption{Honest-client impact.}\label{tab:safety}',
'\begin{tabular}{llllrrrrrr}', '\toprule',
'\multirow{2}{*}{Dataset} & \multirow{2}{*}{Partition} & \multirow{2}{*}{FR (\%)} & \multirow{2}{*}{Attack} & \multicolumn{3}{c}{Mean honest clients per run} & \multicolumn{2}{c}{Excluded client-rounds} & \multirow{2}{*}{\shortstack{Responses\\withheld (\%)}} \\',
'\cmidrule(lr){5-7}\cmidrule(lr){8-9}',
'& & & & \shortstack{Final\\candidates} & \shortstack{Permanent\\removals [range]} & \shortstack{Ever\\quarantined [range]} & Quarantine & \shortstack{Ordinary\\responses} & \\', '\midrule') | ForEach-Object { $lines.Add($_) }
foreach ($dataset in $datasets) {
    if ($dataset -eq 'cifar10') { $lines.Add('\midrule') }
    $datasetRows = @($safetyRows | Where-Object dataset -eq $dataset)
    $datasetLabel = if ($dataset -eq 'mnist') { 'MNIST' } else { 'CIFAR-10' }
    $firstDatasetRow = $true
    foreach ($split in @('iid','noniid')) {
        $partitionRows = @($datasetRows | Where-Object split -eq $split)
        if ($split -eq 'noniid' -and $partitionRows.Count -gt 0) { $lines.Add('\cmidrule(lr){2-10}') }
        $partitionLabel = if ($split -eq 'iid') { 'IID' } else { 'Non-IID' }
        $firstPartitionRow = $true
        $previousShare = -1
        foreach ($row in $partitionRows) {
            if ($previousShare -ge 0 -and $previousShare -ne $row.share) { $lines.Add('\cmidrule(lr){3-10}') }
            $shareRows = @($partitionRows | Where-Object share -eq $row.share).Count
            $shareCell = if ($previousShare -eq $row.share) { '' } elseif ($shareRows -gt 1) { '\multirow{' + $shareRows + '}{*}{' + $row.share + '}' } else { [string]$row.share }
            $cells = @(
                $(if ($firstDatasetRow) { '\multirow{' + $datasetRows.Count + '}{*}{' + $datasetLabel + '}' } else { '' }),
                $(if ($firstPartitionRow) { '\multirow{' + $partitionRows.Count + '}{*}{' + $partitionLabel + '}' } else { '' }),
                $shareCell, $row.attack
            )
            $cells += FormatNumber $row.final_honest_candidates
            foreach ($field in @('fp','honest_ever_quarantined')) {
                $minimum=[int]$row.("${field}_min");$maximum=[int]$row.("${field}_max")
                $cells += $(if($minimum -eq $maximum){[string]$minimum}else{(FormatNumber $row.$field)+' ['+$minimum+'--'+$maximum+']'})
            }
            foreach ($field in @('honest_quarantine_rounds','honest_nontrap_excluded','honest_excluded_pct')) { $cells += FormatNumber $row.$field }
            $lines.Add(($cells -join ' & ') + ' \\')
            $firstDatasetRow = $false; $firstPartitionRow = $false
            $previousShare = $row.share
        }
    }
}
@('\bottomrule','\end{tabular}',
'\par\smallskip\parbox{0.97\textwidth}{\scriptsize Entries are per-run means; brackets give observed minimum--maximum counts. A client-round is one honest client in one round. Withheld responses include traps and quarantine without double counting, as a percentage of active honest client-rounds. Ordinary exclusions count non-trap responses.}',
'\end{table*}') | ForEach-Object { $lines.Add($_) }
WriteTable 'safety' $lines

$costRows = [Collections.Generic.List[object]]::new()
$lines = [Collections.Generic.List[string]]::new()
@('\begin{table*}[t]', '\centering\footnotesize\setlength{\tabcolsep}{4pt}',
'\caption{Execution time and process memory.}\label{tab:cost}',
'\begin{tabular}{llrrrr}', '\toprule',
'Dataset & Partition & FR (\%) & \shortstack{Round time (s)\\mean [range]} & \shortstack{Peak process RSS (GiB)\\mean [range]} & \shortstack{Execution duration\\(min/run)} \\', '\midrule') | ForEach-Object { $lines.Add($_) }
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
