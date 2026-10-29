param([string]$RepositoryRoot = (Join-Path $PSScriptRoot '../../../..'))
$ErrorActionPreference = 'Stop'
$RepositoryRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$exportDir = Join-Path $PSScriptRoot 'generated/multiseed'
$culture = [Globalization.CultureInfo]::InvariantCulture
$seeds = @(42, 43, 73)
$attacks = @('FR1', 'FR2', 'FR3', 'FR4')
$datasets = @('mnist', 'cifar10')
$records = [Collections.Generic.List[object]]::new()
$inputs = [Collections.Generic.List[object]]::new()
$referenceHashes = @{}
$referencePolicy = $null
$settings = @{
    methodology_version='swtcp_v15_4'; num_clients=100; num_rounds=100
    warmup_rounds=10; surveillance_groups=10; v15_cycle_rounds=10
    cycle_strong_cycles_for_removal=2; cycle_suspect_clean_cycles=2
    cycle_candidate_clean_cycles=2; v15_candidate_review_cycles=2
    v15_candidate_cooldown_audits=2; cycle_reference_probation_cycles=1
    v15_audit_interval_rounds=10; local_epochs=3; batch_size=32
    optimizer='sgd'; learning_rate=0.01; momentum=0.9; dirichlet_alpha=0.5
    trap_noise_scale=0.01; trap_noise_floor=0.0001; zero_update_epsilon=0.000001
    fr2_update_range=0.001; fr3_window=5; fr4_history_size=5
    fr4_noise_fraction=0.1; fr4_cold_start_scale=0.0001
}
function Require([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
function ReadJson([string]$Path) {
    Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
}
function Number($Value) {
    $result = [double]::Parse([string]$Value, $culture)
    Require (-not [double]::IsNaN($result) -and -not [double]::IsInfinity($result)) 'Nonfinite measurement'
    return $result
}
function Mean($Values) { return [double](($Values | Measure-Object -Average).Average) }
function SampleSd($Values) {
    $valuesArray = @($Values)
    $center = Mean $valuesArray
    return [math]::Sqrt((($valuesArray | ForEach-Object { [math]::Pow($_ - $center, 2) } | Measure-Object -Sum).Sum) / ($valuesArray.Count - 1))
}
function FormatNumber([double]$Value) { return $Value.ToString('F2', $culture) }

foreach ($dataset in $datasets) {
    foreach ($seed in $seeds) {
        $batchNames = if ($seed -eq 42) {
            @("v15_4_${dataset}_seed${seed}_fr30", "v15_4_${dataset}_seed${seed}_fr40")
        } else { @("v15_4_${dataset}_seed${seed}_fr30_fr40") }
        foreach ($batchName in $batchNames) {
            $batchDir = Join-Path $RepositoryRoot "results/$batchName"
            $status = ReadJson (Join-Path $batchDir 'experiment_status.json')
            $manifest = ReadJson (Join-Path $batchDir 'experiment_manifest.json')
            Require ($status.state -eq 'completed' -and $status.failed_experiments -eq 0) "Incomplete batch $batchName"
            $expectedCount = if ($seed -eq 42) { 8 } else { 16 }
            Require (@($status.experiments).Count -eq $expectedCount) "Unexpected batch size $batchName"
            Require (@($manifest.experiments).Count -eq $expectedCount) "Unexpected manifest size $batchName"
            $manifestIds = @($manifest.experiments.id | Sort-Object)
            $statusIds = @($status.experiments.id | Sort-Object)
            Require (($manifestIds -join '|') -eq ($statusIds -join '|')) "Manifest/status mismatch $batchName"
            foreach ($entry in $status.experiments) {
                Require ($entry.state -eq 'completed') "Incomplete run $($entry.id)"
                $run = Join-Path $batchDir $entry.id
                $config = ReadJson (Join-Path $run 'run_config.json')
                $protocol = ReadJson (Join-Path $run 'protocol.json')
                $marker = ReadJson (Join-Path $run 'latest_results.json')
                Require ($marker.completed -eq $true -and $marker.latest_round -eq 100) "Incomplete marker $run"
                Require ($config.dataset -eq $dataset -and $config.seed -eq $seed) "Dataset/seed mismatch $run"
                Require ($config.completed_rounds -eq 100 -and $config.device_resolved -eq 'cpu') "Horizon/device mismatch $run"
                foreach ($field in $settings.Keys) {
                    Require ($config.$field -eq $settings[$field]) "Setting mismatch: $field in $run"
                }
                Require ($protocol.policy.revision -eq 'v15_4_fresh_certificate_memory_v1') "Wrong policy $run"
                $policyJson = $protocol.policy | ConvertTo-Json -Compress -Depth 30
                if ($null -eq $referencePolicy) { $referencePolicy = $policyJson }
                Require ($policyJson -eq $referencePolicy) "Policy differs across replications: $run"
                foreach ($hash in $protocol.implementation_sha256.psobject.Properties) {
                    if (-not $referenceHashes.ContainsKey($hash.Name)) { $referenceHashes[$hash.Name] = $hash.Value }
                    Require ($referenceHashes[$hash.Name] -eq $hash.Value) "Implementation differs: $($hash.Name) in $run"
                }
                Require (@($protocol.implementation_sha256.psobject.Properties).Count -eq 6) "Missing implementation hashes $run"
                $share = [int][math]::Round(100 * $config.free_rider_pct)
                $split = $config.distribution
                $attack = $config.attack_type
                Require ($share -in @(30,40) -and $split -in @('iid','noniid') -and $attack -in $attacks) "Unexpected configuration $run"
                $metrics = @(Import-Csv -LiteralPath (Join-Path $run 'global_metrics.csv'))
                Require ($metrics.Count -eq 100) "Missing round metrics $run"
                for ($index = 0; $index -lt 100; $index++) {
                    Require ([int]$metrics[$index].round -eq $index + 1) "Unordered round metrics $run"
                    $accuracy = Number $metrics[$index].global_accuracy
                    Require ($accuracy -ge 0 -and $accuracy -le 1 -and (Number $metrics[$index].round_time_seconds) -ge 0) "Invalid metrics $run"
                }
                $initialSignals = @(Import-Csv -LiteralPath (Join-Path $run 'cycle_signals.csv') | Where-Object { [int]$_.round -eq 20 })
                Require ($initialSignals.Count -eq 200) "Missing initial paired coverage $run"
                $truth = @{}
                $pairs = @{}
                foreach ($signal in $initialSignals) {
                    $client = [int]$signal.client_id
                    $label = [int]$signal.is_free_rider
                    $pair = "$client/$($signal.trap_id)"
                    Require ($client -ge 0 -and $client -lt 100 -and $label -in @(0,1) -and [int]$signal.trap_id -in @(0,1)) "Invalid evaluation identity $run"
                    Require (-not $pairs.ContainsKey($pair)) "Repeated initial response $run"
                    if ($truth.ContainsKey($client)) { Require ($truth[$client] -eq $label) "Changing label $run" }
                    $truth[$client] = $label
                    $pairs[$pair] = $true
                }
                Require ($truth.Count -eq 100 -and ($truth.Values | Measure-Object -Sum).Sum -eq $share) "Prevalence mismatch $run"
                $removals = @(Import-Csv -LiteralPath (Join-Path $run 'removals.csv'))
                $seen = @{}
                foreach ($removal in $removals) {
                    $client = [int]$removal.client_id
                    Require (-not $seen.ContainsKey($client) -and $truth.ContainsKey($client)) "Invalid removal identity $run"
                    Require ([int]$removal.is_free_rider -eq $truth[$client] -and [int]$removal.round -ge 30 -and [int]$removal.round -le 100) "Invalid removal $run"
                    $seen[$client] = $true
                }
                $tp = @($removals | Where-Object { [int]$_.is_free_rider -eq 1 }).Count
                $fp = $removals.Count - $tp
                $fn = $share - $tp
                $summary = @(Import-Csv -LiteralPath (Join-Path $run 'detection_summary.csv'))
                Require ($summary.Count -eq 1) "Invalid detection summary $run"
                foreach ($pair in @(@('removed_free_riders',$tp), @('removed_honest_clients',$fp), @('missed_free_riders',$fn))) {
                    Require ([int]$summary[0].($pair[0]) -eq $pair[1] -and [int]$config.($pair[0]) -eq $pair[1]) "Detection summary mismatch $run"
                }
                $finalAccuracy = Number $metrics[-1].global_accuracy
                Require ([math]::Abs($finalAccuracy - $config.final_global_accuracy) -lt 1e-10) "Final accuracy mismatch $run"
                Require ([int]$metrics[-1].num_active_clients -eq 100 - $tp - $fp) "Active population mismatch $run"
                $roundTime = Mean @($metrics | ForEach-Object { Number $_.round_time_seconds })
                Require ([math]::Abs($roundTime - $config.average_round_time_seconds) -lt 1e-7) "Round time mismatch $run"
                $completion = if ($fn -eq 0) { [int](($removals | Where-Object { [int]$_.is_free_rider -eq 1 } | Measure-Object round -Maximum).Maximum) } else { $null }
                $relative = $run.Substring($RepositoryRoot.Length + 1).Replace('\','/')
                $records.Add([pscustomobject]@{
                    dataset=$dataset; split=$split; share=$share; attack=$attack; seed=$seed
                    tp=$tp; fp=$fp; fn=$fn; honest=100-$share
                    precision=$tp/($tp+$fp); recall=$tp/$share; f1=2*$tp/(2*$tp+$fp+$fn)
                    final_accuracy=$finalAccuracy; mean_round_seconds=$roundTime; completion_round=$completion
                    honest_ever_quarantined=$config.honest_clients_ever_quarantined
                    honest_quarantine_rounds=$config.honest_quarantine_client_rounds
                    final_honest_candidates=$config.final_honest_candidate_clients; source=$relative
                })
                foreach ($name in @('run_config.json','protocol.json','latest_results.json','global_metrics.csv','cycle_signals.csv','removals.csv','detection_summary.csv')) {
                    $inputs.Add([pscustomobject]@{path="$relative/$name"; sha256=(Get-FileHash -LiteralPath (Join-Path $run $name) -Algorithm SHA256).Hash.ToLowerInvariant()})
                }
            }
        }
    }
}
Require ($records.Count -eq 96) 'Incomplete three-seed grid'
Require (@($records | Group-Object dataset,split,share,attack,seed | Where-Object Count -ne 1).Count -eq 0) 'Repeated configuration'
$snapshotHashes = @{}
foreach ($sourceName in $referenceHashes.Keys) {
    $snapshotPath = Join-Path $PSScriptRoot "evidence/source/$sourceName"
    $rawHash = (Get-FileHash -LiteralPath $snapshotPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $snapshotText = [IO.File]::ReadAllText($snapshotPath)
    $normalizedBytes = [Text.Encoding]::UTF8.GetBytes($snapshotText.Replace("`r`n", "`n"))
    $lfHash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($normalizedBytes)).ToLowerInvariant()
    Require ($rawHash -eq $referenceHashes[$sourceName] -or $lfHash -eq $referenceHashes[$sourceName]) "Evidence snapshot mismatch: $sourceName"
    $snapshotHashes[$sourceName] = @{raw_sha256=$rawHash;lf_sha256=$lfHash;recorded_sha256=$referenceHashes[$sourceName]}
}
$groups = [Collections.Generic.List[object]]::new()
foreach ($dataset in $datasets) {
    foreach ($split in @('iid','noniid')) {
        foreach ($share in @(30,40)) {
            $runs = @($records | Where-Object { $_.dataset -eq $dataset -and $_.split -eq $split -and $_.share -eq $share })
            Require ($runs.Count -eq 12) 'Incomplete table group'
            $perSeed = foreach ($seed in $seeds) {
                $replication = @($runs | Where-Object seed -eq $seed)
                Require ($replication.Count -eq 4 -and (@($replication.attack | Sort-Object) -join ',') -eq ($attacks -join ',')) 'Incomplete attack group'
                $tp = ($replication | Measure-Object tp -Sum).Sum
                $fp = ($replication | Measure-Object fp -Sum).Sum
                $fn = ($replication | Measure-Object fn -Sum).Sum
                [pscustomobject]@{precision=$tp/($tp+$fp);recall=$tp/($tp+$fn)}
            }
            $group = [ordered]@{dataset=$dataset;split=$split;share=$share;seed_count=$seeds.Count;precision=Mean $perSeed.precision;recall=Mean $perSeed.recall;mean_round_seconds=Mean $runs.mean_round_seconds}
            foreach ($attack in $attacks) {
                $values = @($runs | Where-Object attack -eq $attack | ForEach-Object final_accuracy)
                Require ($values.Count -eq 3) 'Incomplete accuracy replication'
                $group["accuracy_$attack"] = Mean $values
                $group["accuracy_${attack}_sd"] = SampleSd $values
            }
            $groups.Add([pscustomobject]$group)
        }
    }
}
$totalTp = ($records | Measure-Object tp -Sum).Sum
$totalFp = ($records | Measure-Object fp -Sum).Sum
$totalFn = ($records | Measure-Object fn -Sum).Sum
$statistics = [ordered]@{
    seeds=$seeds;validated_runs=$records.Count;tp=$totalTp;fp=$totalFp;fn=$totalFn
    honest=($records | Measure-Object honest -Sum).Sum
    precision=$totalTp/($totalTp+$totalFp);recall=$totalTp/($totalTp+$totalFn)
    f1=2*$totalTp/(2*$totalTp+$totalFp+$totalFn)
    honest_ever_quarantined=($records | Measure-Object honest_ever_quarantined -Sum).Sum
    completion_min=($records | Measure-Object completion_round -Minimum).Minimum
    completion_max=($records | Measure-Object completion_round -Maximum).Maximum
    completion_exceptions=@($records | Where-Object completion_round -ne 30)
    false_removal_cases=@($records | Where-Object fp -gt 0)
    aggregation='Precision/recall pool attacks within each seed before arithmetic averaging across seeds. Accuracy averages seeds separately for each attack. Round time averages all seeds and attacks equally.'
}
New-Item -ItemType Directory -Path $exportDir -Force | Out-Null
$records | Export-Csv -LiteralPath (Join-Path $exportDir 'per_run.csv') -NoTypeInformation -Encoding utf8
$groups | Export-Csv -LiteralPath (Join-Path $exportDir 'table1_means.csv') -NoTypeInformation -Encoding utf8
$statistics | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $exportDir 'summary.json') -Encoding utf8
@{inputs=$inputs;implementation_sha256=$referenceHashes;evidence_snapshot_hashes=$snapshotHashes;policy=($referencePolicy | ConvertFrom-Json)} | ConvertTo-Json -Depth 35 | Set-Content -LiteralPath (Join-Path $exportDir 'provenance.json') -Encoding utf8
$lines = [Collections.Generic.List[string]]::new()
@('\begin{table*}[t]', '\centering\footnotesize\setlength{\tabcolsep}{4pt}',
'\caption{Free-rider detection performance and global model utility.}\label{tab:performance}',
'\begin{tabular}{llrrrrrrrr}', '\toprule',
'\multirow{2}{*}{Dataset} & \multirow{2}{*}{Partition} & \multirow{2}{*}{FR (\%)} & \multicolumn{2}{c}{Detection (\%)} & \multicolumn{4}{c}{Final test accuracy (\%)} & \multirow{2}{*}{\shortstack{Round time\\(s)}} \\',
'\cmidrule(lr){4-5}\cmidrule(lr){6-9}',
'& & & Precision & Recall & FR1 & FR2 & FR3 & FR4 & \\', '\midrule') | ForEach-Object { $lines.Add($_) }
foreach ($dataset in $datasets) {
    if ($dataset -eq 'cifar10') { $lines.Add('\midrule') }
    $datasetLabel = if ($dataset -eq 'mnist') { 'MNIST' } else { 'CIFAR-10' }
    $datasetRow = 0
    foreach ($split in @('iid','noniid')) {
        $splitLabel = if ($split -eq 'iid') { 'IID' } else { 'Non-IID' }
        $splitRow = 0
        foreach ($share in @(30,40)) {
            $group = $groups | Where-Object { $_.dataset -eq $dataset -and $_.split -eq $split -and $_.share -eq $share }
            $cells = @(
                $(if ($datasetRow -eq 0) { "\multirow{4}{*}{$datasetLabel}" } else { '' }),
                $(if ($splitRow -eq 0) { "\multirow{2}{*}{$splitLabel}" } else { '' }),
                [string]$share, (FormatNumber (100*$group.precision)), (FormatNumber (100*$group.recall))
            )
            foreach ($attack in $attacks) { $cells += FormatNumber (100*$group.("accuracy_$attack")) }
            $cells += FormatNumber $group.mean_round_seconds
            $lines.Add(($cells -join ' & ') + ' \\')
            $datasetRow++; $splitRow++
        }
    }
}
@('\bottomrule', '\end{tabular}',
'\par\smallskip\begin{minipage}{0.96\textwidth}\scriptsize Values are averaged across seeds. Precision and recall pool permanent removals across FR1--FR4 within each seed. Test accuracy is averaged separately for each attack. Round time averages the four attack types and includes local training, aggregation, evaluation, and detection.\end{minipage}',
'\end{table*}') | ForEach-Object { $lines.Add($_) }
[IO.File]::WriteAllLines((Join-Path $PSScriptRoot 'generated/performance.tex'), $lines, [Text.UTF8Encoding]::new($false))
$macros = [Collections.Generic.List[string]]::new()
foreach ($pair in @(@('MultiTP',$totalTp), @('MultiFP',$totalFp), @('MultiFN',$totalFn), @('MultiHonest',$statistics.honest), @('MultiQuarantined',$statistics.honest_ever_quarantined), @('MultiCompletionMin',$statistics.completion_min), @('MultiCompletionMax',$statistics.completion_max))) {
    $macros.Add('\newcommand{\' + $pair[0] + '}{' + ([int]$pair[1]).ToString($culture) + '}')
}
foreach ($pair in @(@('MultiPrecision',$statistics.precision), @('MultiRecall',$statistics.recall), @('MultiFone',$statistics.f1))) {
    $macros.Add('\newcommand{\' + $pair[0] + '}{' + (FormatNumber (100*$pair[1])) + '}')
}
foreach ($dataset in $datasets) {
    $values = foreach ($group in ($groups | Where-Object dataset -eq $dataset)) { foreach ($attack in $attacks) { $group.("accuracy_$attack") } }
    $prefix = if ($dataset -eq 'mnist') { 'MultiMnistAccuracy' } else { 'MultiCifarAccuracy' }
    $macros.Add('\newcommand{\' + $prefix + 'Min}{' + (FormatNumber (100*($values | Measure-Object -Minimum).Minimum)) + '}')
    $macros.Add('\newcommand{\' + $prefix + 'Max}{' + (FormatNumber (100*($values | Measure-Object -Maximum).Maximum)) + '}')
}
[IO.File]::WriteAllLines((Join-Path $exportDir 'summary.tex'), $macros, [Text.UTF8Encoding]::new($false))
$statistics | ConvertTo-Json -Depth 12
