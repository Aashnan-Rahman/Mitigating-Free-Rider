$ErrorActionPreference = 'Stop'
$export = Join-Path $PSScriptRoot 'generated/comparison'
$culture = [Globalization.CultureInfo]::InvariantCulture
function Require([bool]$Condition, [string]$Message) { if (-not $Condition) { throw $Message } }
function Num($Value) { [double]::Parse([string]$Value, $culture) }
function Mean($Values) { [double](($Values | Measure-Object -Average).Average) }
function F([double]$Value) { $Value.ToString('F6', $culture) }
function Key($Row) { @($Row.dataset,$Row.split,$Row.share,$Row.attack,$Row.seed) -join '|' }
$trajectoryPath = Join-Path $export 'paired_trajectories.csv'
$pairPath = Join-Path $export 'paired_results.csv'
$pairs = @(Import-Csv $pairPath)
$trajectories = @(Import-Csv $trajectoryPath)
Require ($pairs.Count -gt 0 -and $trajectories.Count -eq 100*$pairs.Count) 'Incomplete matched target-time inputs'
$repository = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$baselineProvenance = Get-Content (Join-Path $export 'provenance.json') -Raw | ConvertFrom-Json
$sourceLogs = @($baselineProvenance.inputs | Where-Object { $_.path -match '/(global_metrics|round_timings)\.csv$' })
Require ($sourceLogs.Count -eq 2*$pairs.Count) 'Missing raw target-time log provenance'
$missingRawLogs = [Collections.Generic.List[string]]::new()
foreach ($log in $sourceLogs) {
    $logPath = Join-Path $repository $log.path
    if (-not (Test-Path -LiteralPath $logPath)) {
        $logPath = Join-Path $PSScriptRoot ('evidence/completed_baselines/'+$log.path)
    }
    if (-not (Test-Path -LiteralPath $logPath)) {
        $missingRawLogs.Add($log.path)
        continue
    }
    Require ((Get-FileHash $logPath -Algorithm SHA256).Hash.ToLowerInvariant() -eq $log.sha256) 'Raw target-time log changed after baseline matching'
}
$pairMap = @{}
foreach ($pair in $pairs) {
    $key = Key $pair
    Require (-not $pairMap.ContainsKey($key)) 'Duplicate matched target-time case'
    $pairMap[$key] = $pair
}
$caseRows = [Collections.Generic.List[object]]::new()
foreach ($group in $trajectories | Group-Object dataset,split,share,attack,seed) {
    $rounds = @($group.Group | Sort-Object { [int]$_.round })
    Require ($rounds.Count -eq 100) 'Incomplete matched target-time trajectory'
    $first = $rounds[0]
    $key = Key $first
    Require ($pairMap.ContainsKey($key)) 'Unmatched target-time trajectory'
    $pair = $pairMap[$key]
    $targets = if ($first.dataset -eq 'mnist') { @(0.98,0.985,0.99) } else { @(0.70,0.72,0.75) }
    foreach ($method in @('bait','baseline')) {
        $elapsed = 0.0
        $hits = @{}
        for ($index=0; $index -lt 100; $index++) {
            $round = $rounds[$index]
            $accuracy = Num $round.("${method}_accuracy")
            $seconds = Num $round.("${method}_seconds")
            Require ([int]$round.round -eq $index+1) 'Unordered target-time rounds'
            Require ([double]::IsFinite($accuracy) -and $accuracy -ge 0 -and $accuracy -le 1) 'Invalid target-time accuracy'
            Require ([double]::IsFinite($seconds) -and $seconds -gt 0) 'Invalid target-time duration'
            $elapsed += $seconds
            foreach ($target in $targets) {
                $targetKey = F $target
                if ($accuracy -ge $target -and -not $hits.ContainsKey($targetKey)) {
                    $hits[$targetKey] = @{round=$index+1;seconds=$elapsed}
                }
            }
        }
        Require ([Math]::Abs($elapsed/100 - (Num $pair.("${method}_seconds"))) -lt 1e-7) 'Target time disagrees with matched baseline table'
        Require ([Math]::Abs((Num $rounds[-1].("${method}_accuracy")) - (Num $pair.("${method}_accuracy"))) -lt 1e-10) 'Target-time endpoint disagrees with matched baseline table'
        foreach ($target in $targets) {
            $hit = $hits[(F $target)]
            $caseRows.Add([pscustomobject]@{
                dataset=$first.dataset;split=$first.split;share=[int]$first.share;attack=$first.attack;seed=[int]$first.seed
                method=$method;target_accuracy=$target;reached=($null -ne $hit)
                first_round=$(if ($null -ne $hit) { $hit.round } else { $null })
                cumulative_seconds=$(if ($null -ne $hit) { $hit.seconds } else { $null })
                observed_horizon_seconds=$elapsed
            })
        }
    }
}
# Retain non-reached outcomes at higher targets in the case export.
Require ($caseRows.Count -eq 6*$pairs.Count) 'Missing target-time outcomes'
$caseRows | Export-Csv (Join-Path $export 'time_target_cases.csv') -NoTypeInformation -Encoding utf8
$shown = @($caseRows | Where-Object { ($_.dataset -eq 'mnist' -and $_.target_accuracy -eq 0.98) -or ($_.dataset -eq 'cifar10' -and $_.target_accuracy -eq 0.70) })
Require ($shown.Count -eq 2*$pairs.Count -and @($shown | Where-Object { -not $_.reached }).Count -eq 0) 'Illustrative target not reached in every matched execution'
$attackMeans = foreach ($group in $shown | Group-Object dataset,split,share,attack,method) {
    $row = $group.Group[0]
    [pscustomobject]@{dataset=$row.dataset;split=$row.split;share=$row.share;attack=$row.attack;method=$row.method;target_accuracy=$row.target_accuracy;matched_runs=$group.Count;seconds=Mean $group.Group.cumulative_seconds;round=Mean $group.Group.first_round}
}
$means = foreach ($group in $attackMeans | Group-Object dataset,split,share,method) {
    Require ($group.Count -eq 4) 'Missing attack in target-time figure'
    $row = $group.Group[0]
    [pscustomobject]@{dataset=$row.dataset;split=$row.split;share=$row.share;method=$row.method;target_accuracy=$row.target_accuracy;matched_runs=($group.Group | Measure-Object matched_runs -Sum).Sum;minutes=(Mean $group.Group.seconds)/60;round=Mean $group.Group.round}
}
$means | Export-Csv (Join-Path $export 'time_target_means.csv') -NoTypeInformation -Encoding utf8
$attackMeans | Export-Csv (Join-Path $export 'time_target_attack_means.csv') -NoTypeInformation -Encoding utf8
$lines = [Collections.Generic.List[string]]::new()
@('\begin{figure*}[!t]\centering\begin{tikzpicture}',
'\begin{groupplot}[group style={group size=2 by 1,horizontal sep=1.1cm},scale only axis,width=0.405\textwidth,height=4.6cm,ybar,/pgf/bar width=10pt,xmin=0.5,xmax=4.5,ymin=0,xtick={1,2,3,4},xticklabels={{30\% IID},{30\% non-IID},{40\% IID},{40\% non-IID}},axis x line*=bottom,axis y line*=left,ymajorgrids=true,grid style={black!8},tick label style={font=\scriptsize},label style={font=\small},title style={font=\small},scaled y ticks=false,nodes near coords,every node near coord/.append style={font=\scriptsize,/pgf/number format/fixed,/pgf/number format/precision=1}]') | ForEach-Object { $lines.Add($_) }
foreach ($dataset in @('mnist','cifar10')) {
    $title = if ($dataset -eq 'mnist') { 'MNIST, target 98\%' } else { 'CIFAR-10, target 70\%' }
    $panel = @($means | Where-Object dataset -eq $dataset)
    $ymax = 1.2*($panel | Measure-Object minutes -Maximum).Maximum
    $lines.Add('\nextgroupplot[title={'+$title+'},ylabel={Logged time to target (min)},ymax='+(F $ymax)+']')
    foreach ($method in @('bait','baseline')) {
        $coordinates = [Collections.Generic.List[string]]::new()
        $position = 0
        foreach ($share in @(30,40)) { foreach ($split in @('iid','noniid')) {
            $position++
            $row = @($panel | Where-Object { $_.method -eq $method -and $_.share -eq $share -and $_.split -eq $split })
            Require ($row.Count -eq 1) 'Missing target-time plot cell'
            $coordinates.Add('('+$position+','+(F $row[0].minutes)+')')
        } }
        $style = if ($method -eq 'bait') { '/pgf/bar shift=-8pt,fill=baitteal!85,draw=baitteal' } else { '/pgf/bar shift=8pt,fill=stdorange!85,draw=stdorange' }
        $lines.Add('\addplot['+$style+'] coordinates {'+($coordinates -join ' ')+'};')
    }
}
@('\end{groupplot}\end{tikzpicture}',
'\par\smallskip{\small\textcolor{baitteal}{\rule{0.35cm}{0.18cm}}\ BaitFL\qquad\textcolor{stdorange}{\rule{0.35cm}{0.18cm}}\ No defense}',
'\caption{Time to first target-accuracy crossing in matched runs. BaitFL is the left bar and no defense the right bar in each pair.}\label{fig:time-target}',
'\end{figure*}') | ForEach-Object { $lines.Add($_) }
[IO.File]::WriteAllLines((Join-Path $PSScriptRoot 'generated/time_target_figure.tex'),$lines,[Text.UTF8Encoding]::new($false))
$inputs = foreach ($path in @($trajectoryPath,$pairPath,(Join-Path $export 'provenance.json'))) {
    [pscustomobject]@{path=('generated/comparison/'+[IO.Path]::GetFileName($path));sha256=(Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant()}
}
@{matched_pairs=$pairs.Count;mnist_pairs=@($pairs | Where-Object dataset -eq 'mnist').Count;cifar10_pairs=@($pairs | Where-Object dataset -eq 'cifar10').Count;figure_targets=@{mnist=0.98;cifar10=0.70};target_choice='Illustrative thresholds selected for this analysis, not preregistered';endpoint='First round with accuracy at or above target; sum recorded round times through that round';averaging='Matched seeds within attack, then all four attacks equally';timing_scope='BaitFL logged round timer and no-defense component sum; different timer boundaries and host load; descriptive saved executions, not a controlled speedup benchmark';higher_targets='Case export retains higher targets with non-reached outcomes and observed horizon durations; no successful crossing imputed';available_raw_logs_verified=$sourceLogs.Count-$missingRawLogs.Count;missing_raw_logs=@($missingRawLogs);data_basis='Complete saved paired exports; round order, values, duration means and accuracy endpoints validated against paired summaries. Available raw logs match their recorded hashes. Missing raw files cannot be rechecked from this checkout.';inputs=$inputs} | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $export 'time_target_provenance.json') -Encoding utf8
$means | Sort-Object dataset,share,split,method | Format-Table dataset,split,share,method,minutes,round
