$ErrorActionPreference = 'Stop'
$repository = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$culture = [Globalization.CultureInfo]::InvariantCulture
$export = Join-Path $PSScriptRoot 'generated/comparison'
function Num($Value) { [double]::Parse([string]$Value,$culture) }
function F([double]$Value,[int]$Digits=2) { $Value.ToString("F$Digits",$culture) }
function Mean($Values) { [double](($Values | Measure-Object -Average).Average) }
function Require([bool]$Condition,[string]$Message) { if (-not $Condition) { throw $Message } }
function WriteFigure([string]$Name,$Lines) {
    $normalized=@($Lines | ForEach-Object { $_.Replace('bar width=','/pgf/bar width=').Replace('bar shift=','/pgf/bar shift=') })
    [IO.File]::WriteAllLines((Join-Path $PSScriptRoot "generated/$Name.tex"),[string[]]$normalized,[Text.UTF8Encoding]::new($false))
}
function AddLines($Lines,[string[]]$Values) { foreach ($value in $Values) { $Lines.Add($value) } }
function Quantile($Values,[double]$Fraction) {
    $ordered=@($Values | Sort-Object); $position=($ordered.Count-1)*$Fraction; $lower=[int][math]::Floor($position); $upper=[int][math]::Ceiling($position)
    $ordered[$lower]+($position-$lower)*($ordered[$upper]-$ordered[$lower])
}
Require (Test-Path (Join-Path $export 'paired_results.csv')) 'Run baseline validation before generating figures'

foreach ($dataset in @('mnist','cifar10')) {
    $datasetLabel=if ($dataset -eq 'mnist') {'MNIST'} else {'CIFAR-10'}
    $lines=[Collections.Generic.List[string]]::new()
    AddLines $lines @('\begin{figure*}[p]\centering', '\begin{tikzpicture}',
    '\begin{groupplot}[group style={group name=geometry,group size=4 by 4,horizontal sep=0.45cm,vertical sep=1.05cm},scale only axis,width=0.212\textwidth,height=3.55cm,axis line style={black!40},grid=major,grid style={black!8},tick label style={font=\scriptsize},title style={font=\scriptsize},label style={font=\scriptsize},scaled ticks=false,unbounded coords=jump]')
    foreach ($share in @(30,40)) {
        foreach ($split in @('iid','noniid')) {
            $splitLabel=if ($split -eq 'iid') {'IID'} else {'Non-IID'}
            for ($attackIndex=1; $attackIndex -le 4; $attackIndex++) {
                $options='title={'+$share+'\% '+$splitLabel+', FR'+$attackIndex+'}'
                if ($attackIndex -eq 1) {$options+=',ylabel={Profile score}'}
                if ($share -eq 40 -and $split -eq 'noniid') {$options+=',xlabel={Norm score}'}
                $lines.Add('\nextgroupplot['+$options+']')
                foreach ($class in @(0,1)) {
                    $path="generated/visuals/scatter_${dataset}_${share}_${split}_FR${attackIndex}_${class}.dat"
                    $expected=if ($class -eq 0) {100-$share} else {$share}
                    Require (@(Get-Content (Join-Path $PSScriptRoot $path) | Select-Object -Skip 1).Count -eq $expected) "Incomplete geometry $path"
                    $style=if ($class -eq 0) {'only marks,mark=o,mark size=1.1pt,draw=honestblue,opacity=0.7'} else {'only marks,mark=triangle*,mark size=1.4pt,draw=riderorange,fill=riderorange,opacity=0.8'}
                    $lines.Add('\addplot['+$style+'] table[x=x,y=y] {'+$path+'};')
                }
            }
        }
    }
    AddLines $lines @('\end{groupplot}',
    '\node[font=\small] at ([yshift=0.85cm]current bounding box.north) {\textcolor{honestblue}{$\circ$}\ Honest clients\qquad\textcolor{riderorange}{$\blacktriangle$}\ Free riders};',
    '\end{tikzpicture}', ('\caption{'+$datasetLabel+' client response scores.}\label{fig:geometry-'+$dataset+'}'), '\end{figure*}')
    WriteFigure "geometry_$dataset" $lines
}

# Both datasets use separately instrumented 100-round pairs, pinned to study commits.
$timingStages=@{};$timingEvidence=@{}
$phaseNames=@{warmup='Warmup';trap='Trap response';screen='Screening round';removal='Removal round';audit='Audit round';ordinary='Ordinary round'}
$phaseRows=[Collections.Generic.List[object]]::new()
$stdRows=@{};$timeSeries=@{};$timingSummary=[Collections.Generic.List[object]]::new()
foreach ($dataset in @('mnist','cifar10')) {
    & (Join-Path $PSScriptRoot 'build_instrumented_timing.ps1') -Dataset $dataset | Out-Null
    if (-not $?) {throw "Instrumented timing validation failed: $dataset"}
    $timingEvidence[$dataset]=Join-Path $PSScriptRoot "evidence/timing_$($dataset)_20261103"
    $timingStages[$dataset]=@(Import-Csv (Join-Path $export "$($dataset)_stage_statistics.csv"))
    foreach ($phase in @(Import-Csv (Join-Path $export "instrumented_$($dataset)_phases.csv"))) {
        $phaseRows.Add([pscustomobject]@{dataset=$dataset;phase=$phase.phase;label=$phaseNames[$phase.phase];rounds=[int]$phase.rounds;mean_seconds=Num $phase.mean_seconds;mean_wall_seconds=Num $phase.mean_wall_seconds;mean_decision_seconds=Num $phase.mean_decision_seconds;total_seconds=Num $phase.total_seconds;amortized_seconds=Num $phase.amortized_seconds})
    }
    $stdRows[$dataset]=@(Import-Csv (Join-Path $timingEvidence[$dataset] 'std/segment_timings.csv'))
    $timeSeries[$dataset]=@(Import-Csv (Join-Path $export "instrumented_$($dataset)_rounds.csv"))
    $timeSeries[$dataset] | Export-Csv (Join-Path $export "timing_$($dataset).csv") -NoTypeInformation -UseQuotes Never -Encoding utf8
    $summary=Get-Content (Join-Path $export "instrumented_$($dataset)_summary.json") -Raw | ConvertFrom-Json
    $timingSummary.Add([pscustomobject]@{dataset=$dataset;bait_mean=$summary.bait_mean;std_mean=$summary.std_mean;bait_wall_mean=$summary.bait_wall_mean;std_wall_mean=$summary.std_wall_mean;gap_mean=$summary.gap_mean;wall_gap_mean=$summary.wall_gap_mean;bait_reduction_pct=$summary.bait_reduction_pct})
}
$phaseRows | Export-Csv (Join-Path $export 'bait_phase_times.csv') -NoTypeInformation -Encoding utf8
$timingSummary | Export-Csv (Join-Path $export 'timing_means.csv') -NoTypeInformation -Encoding utf8

# One table gives identical measured stages for both datasets, with sample SDs.
$lines=[Collections.Generic.List[string]]::new()
AddLines $lines @('\begin{table*}[t]\centering\footnotesize\setlength{\tabcolsep}{5pt}',
'\caption{Measured computation and elapsed time (mean $\pm$ sample SD, s per round).}\label{tab:std-segments}',
'\begin{tabular}{lrrrr}\toprule',
'\multirow{2}{*}{Stage} & \multicolumn{2}{c}{MNIST} & \multicolumn{2}{c}{CIFAR-10} \\',
'\cmidrule(lr){2-3}\cmidrule(lr){4-5}',
' & BaitFL & STD-DAGMM & BaitFL & STD-DAGMM \\ \midrule')
$previousKind='compute'
foreach ($definition in @($timingStages.mnist | Where-Object method -eq 'ours')) {
    if ($definition.kind -ne $previousKind) {$lines.Add('\midrule');$previousKind=$definition.kind}
    $cells=@($definition.label)
    foreach ($dataset in @('mnist','cifar10')) {
        foreach ($method in @('ours','std')) {
            $row=@($timingStages[$dataset] | Where-Object {$_.stage -eq $definition.stage -and $_.method -eq $method})[0]
            $mean=Num $row.mean_seconds;$sd=Num $row.sample_sd_seconds
            $digits=if ($mean -gt 0 -and $mean -lt .01) {6} elseif ($mean -gt 0 -and $mean -lt 1) {4} else {3}
            $cells+=(F $mean $digits)+' $\pm$ '+(F $sd $digits)
        }
    }
    $lines.Add(($cells -join ' & ')+' \\')
}
AddLines $lines @('\bottomrule\end{tabular}\end{table*}')
WriteFigure 'timing_component_table' $lines

$lines=[Collections.Generic.List[string]]::new()
AddLines $lines @('\begin{figure*}[tp]\centering\begin{tikzpicture}',
'\begin{groupplot}[group style={group size=2 by 2,horizontal sep=2.4cm,vertical sep=1.65cm},width=0.40\textwidth,height=7.8cm,xbar,bar width=8pt,xmin=0,axis x line*=bottom,axis y line*=left,xmajorgrids=true,grid style={black!9},tick label style={font=\scriptsize},yticklabel style={font=\scriptsize,align=right},label style={font=\scriptsize},title style={font=\small},scaled x ticks=false,nodes near coords,every node near coord/.append style={font=\scriptsize,/pgf/number format/fixed,/pgf/number format/precision=4},enlarge y limits=0.10]')
foreach ($dataset in @('mnist','cifar10')) {
    $datasetLabel=if ($dataset -eq 'mnist') {'MNIST'} else {'CIFAR-10'}
    $rows=@($timingStages[$dataset] | Where-Object {$_.method -eq 'ours' -and $_.kind -eq 'compute'})
    $ticks=@();$labels=@();$coordinates=@()
    for ($index=0;$index -lt $rows.Count;$index++) {
        $ticks+=$index+1
        $label=$rows[$index].label.Replace('Honest training','Local training').Replace('Fabricated responses','FR responses').Replace('Features and preparation','Features/preparation').Replace('Decisions and scoring','Decision/scoring')
        $labels+='{'+$label+'}'
        $coordinates+='('+(F (Num $rows[$index].mean_seconds) 6)+','+($index+1)+')'
    }
    $max=1.25*($timingStages[$dataset] | Where-Object kind -eq 'compute' | Measure-Object mean_seconds -Maximum).Maximum
    $kind='stages'
    $axisLabel='Mean seconds per round'
    $precisionOption=''
    $lines.Add('\nextgroupplot[title={BaitFL: '+$datasetLabel+' '+$kind+'},xmax='+(F $max 4)+',ytick={'+($ticks -join ',')+'},yticklabels={'+($labels -join ',')+'},y dir=reverse,xlabel={'+$axisLabel+'}'+$precisionOption+']')
    $lines.Add('\addplot[fill=honestblue!75,draw=honestblue] coordinates {'+($coordinates -join ' ')+'};')
    $ticks=@();$labels=@();$coordinates=@();$means=@()
    $rows=@($timingStages[$dataset] | Where-Object {$_.method -eq 'std' -and $_.kind -eq 'compute'})
    for ($index=0;$index -lt $rows.Count;$index++) {
        $label=$rows[$index].label.Replace('Honest training','Local training').Replace('Fabricated responses','FR responses').Replace('Features and preparation','Features/preparation').Replace('Decisions and scoring','Decision/scoring')
        $mean=Num $rows[$index].mean_seconds;$means+=$mean;$ticks+=$index+1;$labels+='{'+$label+'}';$coordinates+='('+(F $mean 6)+','+($index+1)+')'
    }
    $max=1.25*($timingStages[$dataset] | Where-Object kind -eq 'compute' | Measure-Object mean_seconds -Maximum).Maximum
    Require ([math]::Abs(($means | Measure-Object -Sum).Sum-($timingSummary | Where-Object dataset -eq $dataset).std_mean) -lt 1e-7) 'STD components do not sum to round compute'
    $lines.Add('\nextgroupplot[title={STD-DAGMM: '+$datasetLabel+'},xmax='+(F $max 4)+',ytick={'+($ticks -join ',')+'},yticklabels={'+($labels -join ',')+'},y dir=reverse,xlabel={Mean seconds per round}'+$precisionOption+']')
    $lines.Add('\addplot[fill=riderorange!75,draw=riderorange] coordinates {'+($coordinates -join ' ')+'};')
}
AddLines $lines @('\end{groupplot}\end{tikzpicture}', '\caption{Measured timing breakdowns, with a common horizontal scale within each dataset.}\label{fig:timing-segments}', '\end{figure*}')
WriteFigure 'timing_segments_figure' $lines

# Publication timing bars are generated by build_results_visuals.ps1 below.

$lines=[Collections.Generic.List[string]]::new()
AddLines $lines @('\begin{figure*}[tp]\centering\begin{tikzpicture}',
'\begin{groupplot}[group style={group size=2 by 2,horizontal sep=1.1cm,vertical sep=1.5cm},width=0.44\textwidth,height=5.3cm,xmin=1,xmax=100,xtick={1,20,40,60,80,100},axis line style={black!40},grid=major,grid style={black!8},tick label style={font=\scriptsize},label style={font=\scriptsize},title style={font=\small},scaled y ticks=false]')
foreach ($dataset in @('mnist','cifar10')) {
    $datasetLabel=if ($dataset -eq 'mnist') {'MNIST'} else {'CIFAR-10'}
    $path="generated/comparison/timing_${dataset}.csv"
    $ylabelOption=if ($dataset -eq 'mnist') {',ylabel={Seconds per round}'} else {''}
    $lines.Add('\nextgroupplot[title={'+$datasetLabel+'},ymin=0'+$ylabelOption+']')
    $lines.Add('\addplot[honestblue,thick] table[col sep=comma,x=round,y=bait] {'+$path+'};')
    $lines.Add('\addplot[riderorange,thick] table[col sep=comma,x=round,y=std] {'+$path+'};')
}
foreach ($row in $timingSummary) {
    $datasetLabel=if ($row.dataset -eq 'mnist') {'MNIST'} else {'CIFAR-10'}
    $path='generated/comparison/timing_'+$row.dataset+'.csv'
    $ylabelOption=if ($row.dataset -eq 'mnist') {',ylabel={STD-DAGMM minus BaitFL (s)},ymin=0'} else {''}
    $lines.Add('\nextgroupplot[title={'+$datasetLabel+' timing difference}'+$ylabelOption+',xlabel={Round},extra y ticks={0},extra y tick style={grid=major}]')
    $lines.Add('\addplot[violet!75!black,thick] table[col sep=comma,x=round,y=gap] {'+$path+'};')
    $lines.Add('\addplot[black!55,dashed] table[col sep=comma,x=round,y=wall_gap] {'+$path+'};')
    $lines.Add('\addplot[violet!75!black,densely dotted] coordinates {(1,'+(F $row.gap_mean 6)+') (100,'+(F $row.gap_mean 6)+')};')
    $annotation='Mean computation gap: '+(F $row.gap_mean)+' s'
    $annotation+='\\Mean elapsed gap: '+(F $row.wall_gap_mean)+' s'
    $lines.Add('\node[anchor=north east,font=\scriptsize,align=right,fill=white,inner sep=2pt] at (rel axis cs:0.98,0.98) {'+$annotation+'};')
}
AddLines $lines @('\end{groupplot}\end{tikzpicture}',
'\par\smallskip{\scriptsize\textcolor{honestblue}{\rule{0.4cm}{0.8pt}}\ BaitFL\qquad\textcolor{riderorange}{\rule{0.4cm}{0.8pt}}\ STD-DAGMM\qquad\textcolor{black!55}{\textbf{-- --}}\ Elapsed-time gap}',
'\caption{Round timing trajectories and their measured differences.}\label{fig:timing-traces}', '\end{figure*}')
WriteFigure 'timing_timeline_figure' $lines

$lines=[Collections.Generic.List[string]]::new();$lines.Add('\input{generated/timing_component_table.tex}')
AddLines $lines @('\begin{table*}[t]\centering\footnotesize', '\caption{Round timing over 100 rounds.}\label{tab:timing-horizons}', '\begin{tabular}{llrrrr}\toprule', '\multirow{2}{*}{Dataset} & \multirow{2}{*}{Workflow} & \multicolumn{2}{c}{Mean round time (s)} & \multicolumn{2}{c}{Full horizon (min)} \\', '\cmidrule(lr){3-4}\cmidrule(lr){5-6}', ' & & Computation & Elapsed & Computation & Elapsed \\ \midrule')
foreach ($row in $timingSummary) {
    $datasetLabel=if ($row.dataset -eq 'mnist') {'MNIST'} else {'CIFAR-10'}
    if ($row.dataset -eq 'cifar10') {$lines.Add('\midrule')}
    $firstMethod=$true
    foreach ($method in @(@('BaitFL','bait_mean','bait_wall_mean'),@('STD-DAGMM','std_mean','std_wall_mean'))) {
        $elapsed=F $row.($method[2])
        $elapsedMinutes=F ($row.($method[2])*100/60)
        $datasetCell=if ($firstMethod) {'\multirow{2}{*}{'+$datasetLabel+'}'} else {''}
        $lines.Add(($datasetCell,$method[0],(F $row.($method[1])),$elapsed,(F ($row.($method[1])*100/60)),$elapsedMinutes -join ' & ')+' \\')
        $firstMethod=$false
    }
}
AddLines $lines @('\bottomrule\end{tabular}\end{table*}', '\begin{table*}[t]\centering\footnotesize', '\caption{BaitFL execution time by round phase.}\label{tab:timing-phases}', '\begin{tabular}{llrrrrr}\toprule Dataset & Round phase & Count & Computation (s) & Elapsed (s) & Decision (ms) & Contribution (s/round) \\ \midrule')
$previousDataset=''
foreach ($row in $phaseRows) {
    $datasetLabel=if ($row.dataset -eq 'mnist') {'MNIST'} else {'CIFAR-10'}
    $datasetCell=''
    if ($row.dataset -ne $previousDataset) {
        if ($previousDataset) {$lines.Add('\midrule')}
        $span=@($phaseRows | Where-Object dataset -eq $row.dataset).Count
        $datasetCell='\multirow{'+$span+'}{*}{'+$datasetLabel+'}'
        $previousDataset=$row.dataset
    }
    $elapsed=F $row.mean_wall_seconds
    $milliseconds=1000*$row.mean_decision_seconds;$decision=F $milliseconds $(if ($milliseconds -lt .01) {3} else {2})
    $lines.Add(($datasetCell,$row.label,$row.rounds,(F $row.mean_seconds),$elapsed,$decision,(F $row.amortized_seconds) -join ' & ')+' \\')
}
AddLines $lines @('\bottomrule\end{tabular}\end{table*}')
WriteFigure 'timing_tables' $lines
$timingSummary | Format-Table -AutoSize | Out-String | Write-Output

& (Join-Path $PSScriptRoot 'build_results_visuals.ps1')
if (-not $?) {throw 'Result visuals failed'}
& (Join-Path $PSScriptRoot 'build_accuracy_comparison.ps1')
if (-not $?) {throw 'Accuracy comparison failed'}
if(-not $?){throw 'Results visual generation failed'}
