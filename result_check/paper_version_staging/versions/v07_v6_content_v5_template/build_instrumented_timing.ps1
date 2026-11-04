param([ValidateSet('mnist','cifar10')][string]$Dataset='mnist')
$ErrorActionPreference='Stop'
$datasetLabel=if ($Dataset -eq 'mnist') {'MNIST'} else {'CIFAR-10'}
$macroPrefix=if ($Dataset -eq 'mnist') {'TimingMnist'} else {'TimingCifar'}
$culture=[Globalization.CultureInfo]::InvariantCulture
$evidence=Join-Path $PSScriptRoot "evidence/timing_${Dataset}_20261103"
$output=Join-Path $PSScriptRoot 'generated/comparison'
function Require([bool]$Condition,[string]$Message) {if (-not $Condition) {throw $Message}}
function Json([string]$Name) {Get-Content -LiteralPath (Join-Path $evidence $Name) -Raw | ConvertFrom-Json}
function Num($Value) {$number=[double]::Parse([string]$Value,$culture); Require ([double]::IsFinite($number)) 'Nonfinite timing measurement';$number}
function Mean($Values) {[double](($Values | Measure-Object -Average).Average)}
function Sd($Values) {$center=Mean $Values;[math]::Sqrt((($Values | ForEach-Object {[math]::Pow($_-$center,2)} | Measure-Object -Sum).Sum)/(@($Values).Count-1))}
function F([double]$Value,[int]$Digits=2) {([decimal]$Value).ToString("F$Digits",$culture)}
function SumFields($Row,$Fields) {$sum=0.;foreach ($field in $Fields) {$sum+=Num $Row.$field};$sum}
function SourceMatches([string]$Path,[string]$Expected) {
    $text=[IO.File]::ReadAllText($Path).Replace("`r`n","`n")
    foreach ($variant in @($text,$text.Replace("`n","`r`n"))) {
        $hash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($variant))).ToLowerInvariant()
        if ($hash -eq $Expected) {return $true}
    }
    return $false
}
$manifest=Json 'import_provenance.json'
foreach ($inputFile in $manifest.files) {
    Require ((Get-FileHash (Join-Path $evidence $inputFile.snapshot) -Algorithm SHA256).Hash.ToLowerInvariant() -eq $inputFile.sha256) "Changed timing evidence: $($inputFile.snapshot)"
}
$batch=Json 'experiment_status.json';$oursSummary=Json 'ours/timing_summary.json';$stdSummary=Json 'std/timing_summary.json';$stdRun=Json 'std/summary.json';$oursConfig=Json 'ours/run_config.json';$stdProtocol=Json 'std/protocol.json'
Require ($batch.state -eq 'completed' -and $batch.completed_experiments -eq 2 -and $batch.failed_experiments -eq 0) 'Incomplete instrumented comparison'
foreach ($summary in @($oursSummary,$stdSummary,$stdRun)) {Require ($summary.state -eq 'completed' -and $summary.completed_rounds -eq 100) 'Incomplete instrumented run'}
Require ((Json 'ours/latest_results.json').completed -eq $true) 'Missing completed BaitFL marker'
foreach ($field in @('dataset','distribution','num_clients','num_rounds','local_epochs','batch_size','optimizer','learning_rate','momentum','dirichlet_alpha','seed','attack_type','free_rider_pct','fr3_window')) {
    Require ($oursConfig.$field -eq $stdProtocol.config.$field) "Instrumented configuration mismatch: $field"
}
Require ($oursConfig.dataset -eq $Dataset -and $oursConfig.distribution -eq 'noniid' -and $oursConfig.attack_type -eq 'FR3' -and $oursConfig.free_rider_pct -eq .4 -and $oursConfig.num_clients -eq 100 -and $oursConfig.local_epochs -eq 3 -and $stdProtocol.threads -eq 6 -and $stdProtocol.detector_epochs -eq 5) 'Unexpected timing scenario'
$studyProvenance=Get-Content (Join-Path $PSScriptRoot 'generated/multiseed/provenance.json') -Raw | ConvertFrom-Json
Require ($oursSummary.protocol.engine_source_sha256 -eq $studyProvenance.implementation_sha256.'train_v15_4.py') 'Instrumented engine differs from the frozen study engine'
Require (SourceMatches (Join-Path $evidence 'source/segment_timing.py') $oursSummary.protocol.instrumentation_sha256) 'Instrumentation source does not match its protocol'
Require (SourceMatches (Join-Path $evidence 'source/run_std_segment_timing.py') $stdSummary.protocol.instrumentation_sha256) 'STD instrumentation does not match its protocol'
Require ($stdSummary.protocol.canonical_source_sha256 -eq $stdProtocol.source_sha256.'run_std_dagmm_long.py') 'STD canonical source mismatch'
$ours=@(Import-Csv (Join-Path $evidence 'ours/round_timings.csv'));$std=@(Import-Csv (Join-Path $evidence 'std/segment_timings.csv'));$global=@(Import-Csv (Join-Path $evidence 'ours/global_metrics.csv'))
Require ($ours.Count -eq 100 -and $std.Count -eq 100 -and $global.Count -eq 100) 'Incomplete timing rows'
$oursFields=@($oursSummary.protocol.compute_segments)
$stdFields=@('honest_training_seconds','fabrication_seconds','aggregation_seconds','evaluation_seconds','preparation_seconds','fit_seconds','inference_seconds','decision_seconds')
$oldRepository=(Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$oldMetrics=@(Import-Csv (Join-Path $oldRepository "results/v15_4_${Dataset}_seed42_fr40/v15_4_${Dataset}_noniid_FR3_seed42/global_metrics.csv"))
$sameAccuracy=0;$series=[Collections.Generic.List[object]]::new()
for ($index=0;$index -lt 100;$index++) {
    $bait=$ours[$index];$detector=$std[$index]
    Require ([int]$bait.round -eq $index+1 -and [int]$detector.round -eq $index+1 -and [int]$global[$index].round -eq $index+1) 'Unordered timing rounds'
    foreach ($row in @($bait,$detector)) {
        foreach ($property in $row.psobject.Properties | Where-Object Name -Match '_seconds$') {Require ((Num $property.Value) -ge -1e-7) "Negative timer $($property.Name)"}
    }
    $baitCompute=SumFields $bait $oursFields;$stdCompute=SumFields $detector $stdFields
    Require ([math]::Abs($baitCompute-(Num $bait.round_compute_seconds)) -lt 1e-7) 'BaitFL exclusive components do not sum to computation'
    Require ([math]::Abs($stdCompute-(Num $detector.round_compute_seconds)) -lt 1e-7) 'STD components do not sum to computation'
    $baitOverhead=SumFields $bait @('response_bookkeeping_seconds','reporting_seconds','checkpoint_seconds','unassigned_seconds')
    $stdOverhead=SumFields $detector @('reporting_seconds','checkpoint_seconds','unassigned_seconds')
    Require ([math]::Abs($baitCompute+$baitOverhead-(Num $bait.observed_round_wall_seconds)) -lt 1e-7) 'BaitFL round-wall accounting mismatch'
    Require ([math]::Abs($stdCompute+$stdOverhead-(Num $detector.observed_round_wall_seconds)) -lt 1e-7) 'STD round-wall accounting mismatch'
    Require ([math]::Abs((SumFields $detector @('preparation_seconds','fit_seconds','inference_seconds','decision_seconds'))-(Num $detector.detector_seconds)) -lt 1e-7) 'STD detector total mismatch'
    Require ((SumFields $detector @('joint_training_seconds','mixture_finalization_seconds')) -le (Num $detector.fit_seconds)+1e-7) 'Nested fit timers exceed parent fitting time'
    Require ([int]$detector.detector_epochs -eq 5 -and [int]$detector.active_clients -eq 100 -and [int]$detector.permanent_removals -eq 0) 'STD workflow mismatch'
    Require ([math]::Abs((Num $bait.global_accuracy)-(Num $global[$index].global_accuracy)) -lt 1e-10) 'Instrumented accuracy differs from canonical log'
    if ([math]::Abs((Num $bait.global_accuracy)-(Num $oldMetrics[$index].global_accuracy)) -lt 1e-10) {$sameAccuracy++}
    if ($index -lt 10) {Require ([math]::Abs((Num $bait.global_accuracy)-(Num $detector.global_accuracy)) -lt 1e-10) 'Initial trajectories do not match'}
    $series.Add([pscustomobject]@{round=$index+1;bait=$baitCompute;std=$stdCompute;gap=$stdCompute-$baitCompute;bait_wall=Num $bait.observed_round_wall_seconds;std_wall=Num $detector.observed_round_wall_seconds;wall_gap=(Num $detector.observed_round_wall_seconds)-(Num $bait.observed_round_wall_seconds)})
}
$definitions=@(
    @{id='training';label='Honest training';kind='compute';ours=@('honest_training_seconds');std=@('honest_training_seconds')},
    @{id='responses';label='Fabricated responses';kind='compute';ours=@('fabrication_seconds');std=@('fabrication_seconds')},
    @{id='client_eval';label='Client evaluation';kind='compute';ours=@('client_evaluation_seconds');std=@()},
    @{id='traps';label='Trap construction';kind='compute';ours=@('trap_generation_seconds');std=@()},
    @{id='scheduling';label='Scheduling';kind='compute';ours=@('scheduling_seconds');std=@()},
    @{id='features';label='Features and preparation';kind='compute';ours=@('feature_seconds','model_preparation_seconds');std=@('preparation_seconds')},
    @{id='fitting';label='Detector fitting';kind='compute';ours=@();std=@('fit_seconds')},
    @{id='decision';label='Decisions and scoring';kind='compute';ours=@('decision_seconds');std=@('inference_seconds','decision_seconds')},
    @{id='aggregation';label='Aggregation';kind='compute';ours=@('aggregation_seconds');std=@('aggregation_seconds')},
    @{id='evaluation';label='Global evaluation';kind='compute';ours=@('evaluation_seconds');std=@('evaluation_seconds')},
    @{id='publication';label='Logging and checkpoints';kind='other';ours=@('response_bookkeeping_seconds','reporting_seconds','checkpoint_seconds');std=@('reporting_seconds','checkpoint_seconds')},
    @{id='unassigned';label='Unassigned and harness';kind='other';ours=@('unassigned_seconds');std=@('unassigned_seconds')},
    @{id='compute';label='Total computation';kind='total';ours=@('round_compute_seconds');std=@('round_compute_seconds')},
    @{id='wall';label='Elapsed round time';kind='total';ours=@('observed_round_wall_seconds');std=@('observed_round_wall_seconds')}
)
$statistics=[Collections.Generic.List[object]]::new()
foreach ($definition in $definitions) {
    foreach ($method in @('ours','std')) {
        $rows=if ($method -eq 'ours') {$ours} else {$std}
        $values=@($rows | ForEach-Object {SumFields $_ $definition[$method]})
        $statistics.Add([pscustomobject]@{stage=$definition.id;label=$definition.label;kind=$definition.kind;method=$method;mean_seconds=Mean $values;sample_sd_seconds=Sd $values;total_seconds=($values | Measure-Object -Sum).Sum})
    }
}
$phases=[Collections.Generic.List[object]]::new()
foreach ($phase in @('warmup','trap','screen','removal','audit','ordinary')) {
    $indices=@(for ($index=0;$index -lt 100;$index++) {
        $row=$ours[$index]
        $category=if ($row.phase -eq 'warmup') {'warmup'} elseif ([int]$global[$index].new_removals -gt 0) {'removal'} elseif ($row.phase -eq 'single_audit') {'audit'} elseif ([int]$row.decision_boundary -eq 1) {'screen'} elseif ($row.phase -in @('double_probe','confirmation')) {'trap'} else {'ordinary'}
        if ($category -eq $phase) {$index}
    })
    if ($indices.Count -eq 0) {continue}
    $compute=@($indices | ForEach-Object {Num $ours[$_].round_compute_seconds});$wall=@($indices | ForEach-Object {Num $ours[$_].observed_round_wall_seconds})
    $phases.Add([pscustomobject]@{phase=$phase;rounds=$indices.Count;mean_seconds=Mean $compute;mean_wall_seconds=Mean $wall;mean_decision_seconds=Mean @($indices | ForEach-Object {Num $ours[$_].decision_seconds});total_seconds=($compute | Measure-Object -Sum).Sum;amortized_seconds=($compute | Measure-Object -Sum).Sum/100})
}
Require (($phases | Measure-Object rounds -Sum).Sum -eq 100) 'Phase classification loses rounds'
$summary=[ordered]@{source_commit=$manifest.commit;rounds=100;code_version='v15.4';bait_mean=Mean $series.bait;std_mean=Mean $series.std;bait_wall_mean=Mean $series.bait_wall;std_wall_mean=Mean $series.std_wall;gap_mean=Mean $series.gap;wall_gap_mean=Mean $series.wall_gap;bait_reduction_pct=100*(1-(Mean $series.bait)/(Mean $series.std));wall_reduction_pct=100*(1-(Mean $series.bait_wall)/(Mean $series.std_wall));earlier_accuracy_matches=$sameAccuracy}
foreach ($stage in @('traps','scheduling','features','decision','fitting','publication','unassigned')) {
    foreach ($method in @('ours','std')) {$summary["${method}_${stage}_mean"]=($statistics | Where-Object {$_.stage -eq $stage -and $_.method -eq $method}).mean_seconds}
}
$summary.std_detector_mean=Mean @($std | ForEach-Object {Num $_.detector_seconds})
$summary.std_joint_training_mean=Mean @($std | ForEach-Object {Num $_.joint_training_seconds})
$summary.std_mixture_mean=Mean @($std | ForEach-Object {Num $_.mixture_finalization_seconds})
$summary.ours_auditing_mean=$summary.ours_traps_mean+$summary.ours_scheduling_mean+$summary.ours_features_mean+$summary.ours_decision_mean
New-Item -ItemType Directory -Path $output -Force | Out-Null
$statistics | Export-Csv (Join-Path $output "${Dataset}_stage_statistics.csv") -NoTypeInformation -Encoding utf8
$series | Export-Csv (Join-Path $output "instrumented_${Dataset}_rounds.csv") -NoTypeInformation -UseQuotes Never -Encoding utf8
$phases | Export-Csv (Join-Path $output "instrumented_${Dataset}_phases.csv") -NoTypeInformation -Encoding utf8
$summary | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $output "instrumented_${Dataset}_summary.json") -Encoding utf8
$lines=[Collections.Generic.List[string]]::new()
foreach ($mapping in @(@('TimingMnistBait','bait_mean'),@('TimingMnistStd','std_mean'),@('TimingMnistBaitWall','bait_wall_mean'),@('TimingMnistStdWall','std_wall_mean'),@('TimingMnistGap','gap_mean'),@('TimingMnistWallGap','wall_gap_mean'),@('TimingMnistReduction','bait_reduction_pct'),@('TimingMnistWallReduction','wall_reduction_pct'),@('TimingMnistFitting','std_fitting_mean'),@('TimingMnistDetector','std_detector_mean'),@('TimingMnistJointTraining','std_joint_training_mean'),@('TimingMnistMixture','std_mixture_mean'),@('TimingMnistOursLogs','ours_publication_mean'),@('TimingMnistStdLogs','std_publication_mean'),@('TimingMnistStdHarness','std_unassigned_mean'))) {
    $lines.Add('\newcommand{\'+$mapping[0].Replace('TimingMnist',$macroPrefix)+'}{'+(F $summary[$mapping[1]])+'}')
}
foreach ($mapping in @(@('TimingMnistTrapsMs',(1000*($summary.ours_traps_mean+$summary.ours_scheduling_mean))),@('TimingMnistFeaturesMs',(1000*$summary.ours_features_mean)),@('TimingMnistDecisionMs',(1000*$summary.ours_decision_mean)),@('TimingMnistAuditingMs',(1000*$summary.ours_auditing_mean)))) {$lines.Add('\newcommand{\'+$mapping[0].Replace('TimingMnist',$macroPrefix)+'}{'+(F $mapping[1])+'}')}
[IO.File]::WriteAllLines((Join-Path $output "instrumented_${Dataset}_numbers.tex"),$lines,[Text.UTF8Encoding]::new($false))
$lines=[Collections.Generic.List[string]]::new()
@('\begin{table*}[t]\centering\footnotesize\setlength{\tabcolsep}{8pt}', ('\caption{Measured '+$datasetLabel+' computation and elapsed time (s per round).}\label{tab:std-segments-'+$Dataset+'}'), '\begin{tabular}{lrr}\toprule Stage & BaitFL & STD-DAGMM \\ \midrule') | ForEach-Object {$lines.Add($_)}
$previousKind='compute'
foreach ($definition in $definitions) {
    if ($definition.kind -ne $previousKind) {$lines.Add('\midrule');$previousKind=$definition.kind}
    $cells=@($definition.label)
    foreach ($method in @('ours','std')) {
        $row=$statistics | Where-Object {$_.stage -eq $definition.id -and $_.method -eq $method}
        $digits=if ($row.mean_seconds -gt 0 -and $row.mean_seconds -lt .01) {6} elseif ($row.mean_seconds -gt 0 -and $row.mean_seconds -lt 1) {4} else {3}
        $cells+=(F $row.mean_seconds $digits)+' $\pm$ '+(F $row.sample_sd_seconds $digits)
    }
    $lines.Add(($cells -join ' & ')+' \\')
}
@('\bottomrule\end{tabular}\end{table*}') | ForEach-Object {$lines.Add($_)}
[IO.File]::WriteAllLines((Join-Path $PSScriptRoot "generated/${Dataset}_component_table.tex"),$lines,[Text.UTF8Encoding]::new($false))
$summary | ConvertTo-Json -Depth 6
