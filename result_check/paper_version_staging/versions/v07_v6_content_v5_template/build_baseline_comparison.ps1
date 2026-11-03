param([string]$RepositoryRoot = (Join-Path $PSScriptRoot '../../../..'))
$ErrorActionPreference = 'Stop'
$RepositoryRoot = (Resolve-Path $RepositoryRoot).Path
$culture = [Globalization.CultureInfo]::InvariantCulture
$output = Join-Path $PSScriptRoot 'generated/comparison'
New-Item -ItemType Directory -Force -Path $output | Out-Null
function Require([bool]$Condition,[string]$Message) { if (-not $Condition) { throw $Message } }
function Json([string]$Path) { Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json }
function Num($Value) { [double]::Parse([string]$Value,$culture) }
function Mean($Values) { [double](($Values | Measure-Object -Average).Average) }
function Sd($Values) { $center=Mean $Values; [math]::Sqrt((($Values | ForEach-Object {[math]::Pow($_-$center,2)} | Measure-Object -Sum).Sum)/(@($Values).Count-1)) }
function F([double]$Value,[int]$Digits=2) { ([decimal]$Value).ToString("F$Digits",$culture) }
function WriteGenerated([string]$Name,$Lines) { [IO.File]::WriteAllLines((Join-Path $PSScriptRoot "generated/$Name.tex"),[string[]]$Lines,[Text.UTF8Encoding]::new($false)) }
$study = @(Import-Csv (Join-Path $PSScriptRoot 'generated/multiseed/per_run.csv'))
$pairs = [Collections.Generic.List[object]]::new()
$trajectories = [Collections.Generic.List[object]]::new()
$inputs = [Collections.Generic.List[object]]::new()
$timingRows = @{}
$primaryBatches = @('fedavg_mnist_baseline_seed42_fr30_fr40','fedavg_cifar10_baseline_seed42_fr30_fr40')
$runPaths = [Collections.Generic.List[string]]::new()
foreach ($batchName in $primaryBatches) {
    $batch = Join-Path $RepositoryRoot "results/$batchName"
    $status = Json (Join-Path $batch 'experiment_status.json')
    Require ($status.state -eq 'completed' -and $status.completed_experiments -eq 16 -and $status.failed_experiments -eq 0) "Incomplete baseline grid $batchName"
    foreach ($entry in $status.experiments) { $runPaths.Add((Join-Path $batch $entry.id)) }
}
foreach ($directory in Get-ChildItem (Join-Path $RepositoryRoot 'results/fedavg_cifar10_baseline_seed73_fr30_fr40') -Directory) {
    if (Test-Path (Join-Path $directory.FullName 'summary.json')) { $runPaths.Add($directory.FullName) }
}
foreach ($run in $runPaths) {
    $summary = Json (Join-Path $run 'summary.json')
    $protocol = Json (Join-Path $run 'protocol.json')
    $config = $protocol.config
    Require ($summary.state -eq 'completed' -and $summary.completed_rounds -eq 100 -and $summary.detection_enabled -eq $false -and $protocol.detection_enabled -eq $false -and $protocol.trap_generation_enabled -eq $false -and $protocol.removal_enabled -eq $false) "Invalid no-defense run $run"
    $dataset=$config.dataset; $split=$config.distribution; $share=[int][math]::Round(100*$config.free_rider_pct); $attack=$config.attack_type; $seed=[int]$config.seed
    $match = @($study | Where-Object { $_.dataset -eq $dataset -and $_.split -eq $split -and [int]$_.share -eq $share -and $_.attack -eq $attack -and [int]$_.seed -eq $seed })
    Require ($match.Count -eq 1) "No unique BaitFL match $run"
    $baitDir = Join-Path $RepositoryRoot $match[0].source
    $baitConfig = Json (Join-Path $baitDir 'run_config.json')
    foreach ($field in @('dataset','distribution','seed','num_clients','num_rounds','local_epochs','batch_size','optimizer','learning_rate','momentum','dirichlet_alpha','attack_type','free_rider_pct','fr2_update_range','fr3_window','fr4_history_size','fr4_noise_fraction','fr4_cold_start_scale','partition_seed','model_seed','training_seed','attack_seed','attacker_selection_seed')) {
        Require ($config.$field -eq $baitConfig.$field) "Mismatched $field in $run"
    }
    $baseRows = @(Import-Csv (Join-Path $run 'round_timings.csv'))
    $baitRows = @(Import-Csv (Join-Path $baitDir 'global_metrics.csv'))
    Require ($baseRows.Count -eq 100 -and $baitRows.Count -eq 100) "Incomplete paired horizon $run"
    for ($index=0; $index -lt 100; $index++) {
        $base=$baseRows[$index]; $bait=$baitRows[$index]
        Require ([int]$base.round -eq $index+1 -and [int]$bait.round -eq $index+1 -and [int]$base.active_clients -eq 100 -and [int]$base.num_aggregated -eq 100) "Invalid baseline participation $run"
        foreach ($field in @('num_trapped','permanent_removals','preparation_seconds','fit_seconds','inference_seconds','decision_seconds','detector_seconds')) { Require ((Num $base.$field) -eq 0) "Baseline has defense activity $run" }
        if ($index -lt 10) { Require ([math]::Abs((Num $base.global_accuracy)-(Num $bait.global_accuracy)) -lt 1e-10) "Warmup trajectories do not match $run" }
        $trajectories.Add([pscustomobject]@{dataset=$dataset;split=$split;share=$share;attack=$attack;seed=$seed;round=$index+1;baseline_accuracy=Num $base.global_accuracy;bait_accuracy=Num $bait.global_accuracy;baseline_seconds=Num $base.round_compute_seconds;bait_seconds=Num $bait.round_time_seconds})
    }
    $clientCount=0
    Import-Csv (Join-Path $run 'client_metrics.csv') | ForEach-Object {
        Require ([int]$_.was_aggregated -eq 1 -and [int]$_.was_trapped -eq 0) "Baseline withholds a client response $run"
        $clientCount++
    }
    Require ($clientCount -eq 10000) "Incomplete baseline client records $run"
    $baseFinal=Num $baseRows[-1].global_accuracy; $baitFinal=Num $baitRows[-1].global_accuracy
    Require ([math]::Abs($baseFinal-$summary.final_accuracy) -lt 1e-10) 'Baseline final accuracy mismatch'
    $baseSeconds=Mean @($baseRows | ForEach-Object {Num $_.round_compute_seconds})
    $baitSeconds=Mean @($baitRows | ForEach-Object {Num $_.round_time_seconds})
    $record = [pscustomobject]@{
        dataset=$dataset;split=$split;share=$share;attack=$attack;seed=$seed;primary=($seed -eq 42)
        baseline_accuracy=$baseFinal;bait_accuracy=$baitFinal;accuracy_change_pp=100*($baitFinal-$baseFinal)
        baseline_seconds=$baseSeconds;bait_seconds=$baitSeconds;time_change_pct=100*($baitSeconds/$baseSeconds-1)
        baseline_late_sd_pp=100*(Sd @($baseRows | Select-Object -Last 20 | ForEach-Object {Num $_.global_accuracy}))
        bait_late_sd_pp=100*(Sd @($baitRows | Select-Object -Last 20 | ForEach-Object {Num $_.global_accuracy}))
        baseline_source=$run.Substring($RepositoryRoot.Length+1).Replace('\','/');bait_source=$match[0].source
    }
    $pairs.Add($record)
    if ($seed -eq 42 -and $split -eq 'noniid' -and $share -eq 40 -and $attack -eq 'FR3') { $timingRows[$dataset]=@{baseline=$baseRows;bait=$baitRows} }
    foreach ($item in @(@($run,'summary.json'),@($run,'protocol.json'),@($run,'round_timings.csv'),@($run,'client_metrics.csv'),@($baitDir,'global_metrics.csv'))) {
        $path=Join-Path $item[0] $item[1]
        $inputs.Add([pscustomobject]@{path=$path.Substring($RepositoryRoot.Length+1).Replace('\','/');sha256=(Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant()})
    }
}
$primary=@($pairs | Where-Object primary)
Require ($primary.Count -eq 32 -and @($primary | Group-Object dataset,split,share,attack | Where-Object Count -ne 1).Count -eq 0) 'Incomplete common baseline grid'
$pairs | Export-Csv (Join-Path $output 'paired_results.csv') -NoTypeInformation -Encoding utf8
$trajectories | Export-Csv (Join-Path $output 'paired_trajectories.csv') -NoTypeInformation -Encoding utf8
@{inputs=$inputs;primary_selection='Complete seed-matched grid common to both datasets; additional completed CIFAR-10 cases exported separately';warmup_validation='First ten global accuracies agree exactly in every pair';timing_basis='BaitFL logged whole-round timer; baseline and STD summed component compute timers; excludes checkpoint publication; different host load and simulator instrumentation'} | ConvertTo-Json -Depth 12 | Set-Content (Join-Path $output 'provenance.json') -Encoding utf8

$groupRows=[Collections.Generic.List[object]]::new()
$lines=[Collections.Generic.List[string]]::new()
@('\begin{table*}[t]\centering\footnotesize\setlength{\tabcolsep}{5pt}',
'\caption{Comparison with federated averaging without a defense.}\label{tab:baseline}',
'\begin{tabular}{llrrrrrrr}\toprule',
'\multirow{2}{*}{Dataset} & \multirow{2}{*}{Partition} & \multirow{2}{*}{FR (\%)} & \multicolumn{3}{c}{Final accuracy (\%)} & \multicolumn{3}{c}{Mean round time (s)} \\',
'\cmidrule(lr){4-6}\cmidrule(lr){7-9}',
'& & & No defense & BaitFL & $\Delta$ (pp) & No defense & BaitFL & $\Delta$ (\%) \\ \midrule') | ForEach-Object {$lines.Add($_)}
foreach ($dataset in @('mnist','cifar10')) {
    if ($dataset -eq 'cifar10') {$lines.Add('\midrule')}
    $datasetLabel=if ($dataset -eq 'mnist') {'MNIST'} else {'CIFAR-10'}
    $datasetIndex=0
    foreach ($split in @('iid','noniid')) {
        $partitionLabel=if ($split -eq 'iid') {'IID'} else {'Non-IID'}
        $splitIndex=0
        foreach ($share in @(30,40)) {
            $runs=@($primary | Where-Object {$_.dataset -eq $dataset -and $_.split -eq $split -and $_.share -eq $share})
            Require ($runs.Count -eq 4) 'Incomplete baseline table cell'
            $row=[pscustomobject]@{dataset=$dataset;split=$split;share=$share;baseline_accuracy=Mean $runs.baseline_accuracy;bait_accuracy=Mean $runs.bait_accuracy;accuracy_change_pp=Mean $runs.accuracy_change_pp;baseline_seconds=Mean $runs.baseline_seconds;bait_seconds=Mean $runs.bait_seconds;time_change_pct=100*((Mean $runs.bait_seconds)/(Mean $runs.baseline_seconds)-1)}
            $groupRows.Add($row)
            $cells=@($(if ($datasetIndex -eq 0) {"\multirow{4}{*}{$datasetLabel}"} else {''}),$(if ($splitIndex -eq 0) {"\multirow{2}{*}{$partitionLabel}"} else {''}),[string]$share,(F (100*$row.baseline_accuracy)),(F (100*$row.bait_accuracy)),(F $row.accuracy_change_pp),(F $row.baseline_seconds),(F $row.bait_seconds),(F $row.time_change_pct))
            $lines.Add(($cells -join ' & ')+' \\');$datasetIndex++;$splitIndex++
        }
    }
}
@('\bottomrule\end{tabular}\end{table*}') | ForEach-Object {$lines.Add($_)}
WriteGenerated 'baseline_table' $lines
$groupRows | Export-Csv (Join-Path $output 'baseline_group_means.csv') -NoTypeInformation -Encoding utf8
$lines=[Collections.Generic.List[string]]::new()
@('\begin{table*}[t]\centering\footnotesize', '\caption{Additional matched CIFAR-10 non-IID comparisons at 40\% free riders.}\label{tab:baseline-extra}',
'\begin{tabular}{lrrrrrr}\toprule',
' & \multicolumn{3}{c}{Final accuracy (\%)} & \multicolumn{3}{c}{Mean round time (s)} \\',
'Attack & No defense & BaitFL & $\Delta$ (pp) & No defense & BaitFL & $\Delta$ (\%) \\ \midrule') | ForEach-Object {$lines.Add($_)}
foreach ($row in @($pairs | Where-Object {-not $_.primary} | Sort-Object attack)) {
    $lines.Add(($row.attack,(F (100*$row.baseline_accuracy)),(F (100*$row.bait_accuracy)),(F $row.accuracy_change_pp),(F $row.baseline_seconds),(F $row.bait_seconds),(F $row.time_change_pct) -join ' & ')+' \\')
}
@('\bottomrule\end{tabular}\end{table*}') | ForEach-Object {$lines.Add($_)}
WriteGenerated 'baseline_extra' $lines
$summary=[ordered]@{matched_cases=$pairs.Count;primary_cases=$primary.Count;primary_accuracy_wins=@($primary | Where-Object accuracy_change_pp -gt 0).Count;primary_accuracy_ties=@($primary | Where-Object accuracy_change_pp -eq 0).Count;primary_accuracy_losses=@($primary | Where-Object accuracy_change_pp -lt 0).Count;dataset_summary=@()}
foreach ($dataset in @('mnist','cifar10')) {
    $runs=@($primary | Where-Object dataset -eq $dataset)
    $summary.dataset_summary += [pscustomobject]@{dataset=$dataset;mean_accuracy_change_pp=Mean $runs.accuracy_change_pp;min_accuracy_change_pp=($runs | Measure-Object accuracy_change_pp -Minimum).Minimum;max_accuracy_change_pp=($runs | Measure-Object accuracy_change_pp -Maximum).Maximum;baseline_late_sd_pp=Mean $runs.baseline_late_sd_pp;bait_late_sd_pp=Mean $runs.bait_late_sd_pp;baseline_seconds=Mean $runs.baseline_seconds;bait_seconds=Mean $runs.bait_seconds}
}
$summary | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $output 'summary.json') -Encoding utf8
$summary | ConvertTo-Json -Depth 8
