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
$pairs=@(Import-Csv (Join-Path $export 'paired_results.csv') | Where-Object primary -eq 'True')
$trajectories=@(Import-Csv (Join-Path $export 'paired_trajectories.csv') | Where-Object seed -eq '42')
Require ($pairs.Count -eq 32 -and $trajectories.Count -eq 3200) 'Run baseline validation before generating figures'

foreach ($dataset in @('mnist','cifar10')) {
    $datasetLabel=if ($dataset -eq 'mnist') {'MNIST'} else {'CIFAR-10'}
    $lines=[Collections.Generic.List[string]]::new()
    AddLines $lines @('\begin{figure*}[p]\centering', '\begin{tikzpicture}',
    '\begin{groupplot}[group style={group name=geometry,group size=4 by 4,horizontal sep=0.6cm,vertical sep=1.0cm},width=0.22\textwidth,height=4.55cm,axis line style={black!40},grid=major,grid style={black!8},tick label style={font=\scriptsize},title style={font=\scriptsize},label style={font=\scriptsize},scaled ticks=false,unbounded coords=jump]')
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
    '\node[font=\small] at ([xshift=2.0cm,yshift=0.85cm]geometry c2r1.north) {\textcolor{honestblue}{$\circ$}\ Honest clients\qquad\textcolor{riderorange}{$\blacktriangle$}\ Free riders};',
    '\end{tikzpicture}', ('\caption{'+$datasetLabel+' client response scores.}\label{fig:geometry-'+$dataset+'}'), '\end{figure*}')
    WriteFigure "geometry_$dataset" $lines
}

$accuracyRows=[Collections.Generic.List[object]]::new()
foreach ($dataset in @('mnist','cifar10')) {
    foreach ($share in @(30,40)) {
        $caseRows=@($trajectories | Where-Object {$_.dataset -eq $dataset -and [int]$_.share -eq $share})
        for ($round=1;$round -le 100;$round++) {
            $roundRows=@($caseRows | Where-Object {[int]$_.round -eq $round})
            Require ($roundRows.Count -eq 8) 'Incomplete matched accuracy average'
            $baseline=@($roundRows | ForEach-Object {100*(Num $_.baseline_accuracy)})
            $bait=@($roundRows | ForEach-Object {100*(Num $_.bait_accuracy)})
            $accuracyRows.Add([pscustomobject]@{dataset=$dataset;share=$share;round=$round;baseline=Mean $baseline;bait=Mean $bait;baseline_q1=Quantile $baseline .25;baseline_q3=Quantile $baseline .75;bait_q1=Quantile $bait .25;bait_q3=Quantile $bait .75})
        }
        $accuracyRows | Where-Object {$_.dataset -eq $dataset -and $_.share -eq $share} | Export-Csv (Join-Path $export "accuracy_${dataset}_${share}.csv") -NoTypeInformation -UseQuotes Never -Encoding utf8
    }
}
foreach ($view in @('late','full')) {
    $lines=[Collections.Generic.List[string]]::new()
    AddLines $lines @('\begin{figure*}[tp]\centering\begin{tikzpicture}',
    '\begin{groupplot}[group style={group size=2 by 2,horizontal sep=0.8cm,vertical sep=1.4cm},width=0.455\textwidth,height=5.25cm,axis line style={black!40},grid=major,grid style={black!8},tick label style={font=\scriptsize},label style={font=\scriptsize},title style={font=\small},scaled y ticks=false]')
    foreach ($dataset in @('mnist','cifar10')) {
        foreach ($share in @(30,40)) {
            $datasetLabel=if ($dataset -eq 'mnist') {'MNIST'} else {'CIFAR-10'}
            $range=if ($view -eq 'full') {'xmin=1,xmax=100,ymin=0,ymax=100,xtick={1,20,40,60,80,100}'} else {'xmin=60,xmax=100,xtick={60,70,80,90,100}'}
            $ylabel=if ($share -eq 30) {',ylabel={Test accuracy (\%)}'} else {''}
            $lines.Add('\nextgroupplot[title={'+$datasetLabel+', '+$share+'\%},'+$range+$ylabel+',xlabel={Round}]')
            $path="generated/comparison/accuracy_${dataset}_${share}.csv"
            foreach ($method in @('baseline','bait')) {
                $color=if ($method -eq 'bait') {'honestblue'} else {'riderorange'}
                $lineStyle=if ($method -eq 'bait') {'thick'} else {'thick,dashed'}
                $lines.Add('\addplot[draw=none,name path=lower] table[col sep=comma,x=round,y='+$method+'_q1] {'+$path+'};')
                $lines.Add('\addplot[draw=none,name path=upper] table[col sep=comma,x=round,y='+$method+'_q3] {'+$path+'};')
                $lines.Add('\addplot[fill='+$color+',fill opacity=0.10,draw=none] fill between[of=lower and upper];')
                $lines.Add('\addplot['+$color+','+$lineStyle+'] table[col sep=comma,x=round,y='+$method+'] {'+$path+'};')
            }
        }
    }
    AddLines $lines @('\end{groupplot}\end{tikzpicture}', '\par\smallskip{\scriptsize\textcolor{honestblue}{\rule{0.45cm}{0.8pt}}\ BaitFL\qquad\textcolor{riderorange}{\textbf{-- --}}\ No defense}')
    if ($view -eq 'late') { $lines.Add('\caption{Late-training accuracy with and without BaitFL.}\label{fig:accuracy}');$name='accuracy_figure' }
    else { $lines.Add('\caption{Full-horizon accuracy with and without BaitFL.}\label{fig:accuracy-overview}');$name='accuracy_overview_figure' }
    $lines.Add('\end{figure*}'); WriteFigure $name $lines
}

$conditions=@(@{share=30;split='iid';color='honestblue';label='30\% IID'},@{share=30;split='noniid';color='violet!75!black';label='30\% Non-IID'},@{share=40;split='iid';color='teal!75!black';label='40\% IID'},@{share=40;split='noniid';color='riderorange';label='40\% Non-IID'})
$lines=[Collections.Generic.List[string]]::new()
AddLines $lines @('\begin{figure*}[tp]\centering\begin{tikzpicture}', '\begin{groupplot}[group style={group size=2 by 2,horizontal sep=1.1cm,vertical sep=1.6cm},width=0.44\textwidth,height=5.0cm,ybar,bar width=4pt,xmin=0.45,xmax=4.55,xtick={1,2,3,4},xticklabels={FR1,FR2,FR3,FR4},axis line style={black!40},ymajorgrids=true,grid style={black!8},tick label style={font=\scriptsize},label style={font=\scriptsize},title style={font=\small},scaled y ticks=false,enlarge y limits=0.12]')
foreach ($metric in @('accuracy_change_pp','time_change_pct')) {
    foreach ($dataset in @('mnist','cifar10')) {
        $datasetLabel=if ($dataset -eq 'mnist') {'MNIST'} else {'CIFAR-10'}
        $ylabel=if ($metric -eq 'accuracy_change_pp') {'Accuracy change (pp)'} else {'Round-time change (\%)'}
        $ylabelOption=if ($dataset -eq 'mnist') {',ylabel={'+$ylabel+'}'} else {''}
        $lines.Add('\nextgroupplot[title={'+$datasetLabel+'}'+$ylabelOption+']')
        for ($conditionIndex=0;$conditionIndex -lt 4;$conditionIndex++) {
            $condition=$conditions[$conditionIndex];$coordinates=@()
            for ($attackIndex=1;$attackIndex -le 4;$attackIndex++) {
                $row=@($pairs | Where-Object {$_.dataset -eq $dataset -and [int]$_.share -eq $condition.share -and $_.split -eq $condition.split -and $_.attack -eq "FR$attackIndex"})
                Require ($row.Count -eq 1) 'Missing baseline change bar'
                $coordinates+='('+$attackIndex+','+(F (Num $row[0].$metric) 6)+')'
            }
            $shift=($conditionIndex-1.5)*5
            $lines.Add('\addplot[bar shift='+(F $shift 1)+'pt,fill='+$condition.color+',draw='+$condition.color+'] coordinates {'+($coordinates -join ' ')+'};')
        }
        $lines.Add('\draw[black!60,thin] (axis cs:0.5,0) -- (axis cs:4.5,0);')
    }
}
AddLines $lines @('\end{groupplot}\end{tikzpicture}', '\par\smallskip{\scriptsize')
foreach ($condition in $conditions) {$lines.Add('\textcolor{'+$condition.color+'}{\rule{0.25cm}{0.15cm}}\ '+$condition.label+'\quad')}
AddLines $lines @('}', '\caption{Changes relative to federated averaging without a defense.}\label{fig:baseline-effects}', '\end{figure*}')
WriteFigure 'resource_figure' $lines

# Validate and use the separately instrumented MNIST pair; retain the recorded CIFAR-10 study case.
& (Join-Path $PSScriptRoot 'build_instrumented_mnist_timing.ps1') | Out-Null
if (-not $?) {throw 'Instrumented MNIST timing validation failed'}
$mnistEvidence=Join-Path $PSScriptRoot 'evidence/timing_mnist_20261103'
$mnistStages=@(Import-Csv (Join-Path $export 'mnist_stage_statistics.csv'))
$mnistPhases=@(Import-Csv (Join-Path $export 'instrumented_mnist_phases.csv'))
$phaseNames=@{warmup='Warmup';trap='Trap response';screen='Screening round';removal='Removal round';audit='Audit round';ordinary='Ordinary round'}
$phaseOrder=@('warmup','trap','screen','removal','audit','ordinary')
$phaseRows=[Collections.Generic.List[object]]::new()
$stdRows=@{}; $timeSeries=@{}; $timingSummary=[Collections.Generic.List[object]]::new()
foreach ($dataset in @('mnist','cifar10')) {
    $match=@($pairs | Where-Object {$_.dataset -eq $dataset -and $_.split -eq 'noniid' -and [int]$_.share -eq 40 -and $_.attack -eq 'FR3'})[0]
    $baitDir=if ($dataset -eq 'mnist') {Join-Path $mnistEvidence 'ours'} else {Join-Path $repository $match.bait_source}
    $baitRows=@(Import-Csv (Join-Path $baitDir 'global_metrics.csv'))
    $decisions=@(Import-Csv (Join-Path $baitDir 'cycle_decisions.csv'))
    $decisionRounds=@($decisions.round | Select-Object -Unique)
    $buckets=@{};foreach ($phase in $phaseOrder) {$buckets[$phase]=[Collections.Generic.List[double]]::new()}
    foreach ($round in $baitRows) {
        $phase=if ($round.phase -eq 'warmup') {'warmup'} elseif ([int]$round.new_removals -gt 0) {'removal'} elseif ($round.round -in $decisionRounds) {'screen'} elseif ($round.phase -eq 'single_audit') {'audit'} elseif ($round.phase -in @('double_probe','confirmation')) {'trap'} else {'ordinary'}
        if ($dataset -ne 'mnist') {$buckets[$phase].Add((Num $round.round_time_seconds))}
    }
    foreach ($phase in $phaseOrder) {
        if ($dataset -eq 'mnist') {
            $measured=$mnistPhases | Where-Object phase -eq $phase
            if ($measured) {$phaseRows.Add([pscustomobject]@{dataset=$dataset;phase=$phase;label=$phaseNames[$phase];rounds=[int]$measured.rounds;mean_seconds=Num $measured.mean_seconds;mean_wall_seconds=Num $measured.mean_wall_seconds;mean_decision_seconds=Num $measured.mean_decision_seconds;total_seconds=Num $measured.total_seconds;amortized_seconds=Num $measured.amortized_seconds})}
        } else {
            $values=$buckets[$phase]
            if ($values.Count -gt 0) { $phaseRows.Add([pscustomobject]@{dataset=$dataset;phase=$phase;label=$phaseNames[$phase];rounds=$values.Count;mean_seconds=Mean $values;mean_wall_seconds=$null;mean_decision_seconds=$null;total_seconds=($values | Measure-Object -Sum).Sum;amortized_seconds=($values | Measure-Object -Sum).Sum/100}) }
        }
    }
    $stdPath=if ($dataset -eq 'mnist') {Join-Path $mnistEvidence 'std/segment_timings.csv'} else {Join-Path $repository "results/std_dagmm_100_seed42_fr40/std_dagmm_${dataset}_noniid_FR3_seed42/round_timings.csv"}
    $stdRows[$dataset]=@(Import-Csv $stdPath)
    Require ($stdRows[$dataset].Count -eq 100) 'Incomplete STD timing'
    if ($dataset -eq 'mnist') {$baitSegments=@(Import-Csv (Join-Path $mnistEvidence 'ours/round_timings.csv'))}
    $series=[Collections.Generic.List[object]]::new()
    for ($index=0;$index -lt 100;$index++) {
        $std=Num $stdRows[$dataset][$index].round_compute_seconds
        $bait=if ($dataset -eq 'mnist') {Num $baitSegments[$index].round_compute_seconds} else {Num $baitRows[$index].round_time_seconds}
        $baitWall=if ($dataset -eq 'mnist') {Num $baitSegments[$index].observed_round_wall_seconds} else {$null}
        $stdWall=if ($dataset -eq 'mnist') {Num $stdRows[$dataset][$index].observed_round_wall_seconds} else {$null}
        $series.Add([pscustomobject]@{round=$index+1;bait=$bait;std=$std;gap=$std-$bait;bait_wall=$baitWall;std_wall=$stdWall;wall_gap=$(if ($dataset -eq 'mnist') {$stdWall-$baitWall} else {$null})})
    }
    $timeSeries[$dataset]=$series
    $series | Export-Csv (Join-Path $export "timing_${dataset}.csv") -NoTypeInformation -UseQuotes Never -Encoding utf8
    $timingSummary.Add([pscustomobject]@{dataset=$dataset;bait_mean=Mean $series.bait;std_mean=Mean $series.std;bait_wall_mean=$(if ($dataset -eq 'mnist') {Mean $series.bait_wall} else {$null});std_wall_mean=$(if ($dataset -eq 'mnist') {Mean $series.std_wall} else {$null});gap_mean=Mean $series.gap;wall_gap_mean=$(if ($dataset -eq 'mnist') {Mean $series.wall_gap} else {$null});bait_reduction_pct=100*(1-(Mean $series.bait)/(Mean $series.std))})
}
$phaseRows | Export-Csv (Join-Path $export 'bait_phase_times.csv') -NoTypeInformation -Encoding utf8
$timingSummary | Export-Csv (Join-Path $export 'timing_means.csv') -NoTypeInformation -Encoding utf8

$stdComponents=@(@{name='Local training';fields=@('honest_training_seconds')},@{name='FR responses';fields=@('fabrication_seconds')},@{name='Aggregation';fields=@('aggregation_seconds')},@{name='Evaluation';fields=@('evaluation_seconds')},@{name='Preparation';fields=@('preparation_seconds')},@{name='Detector fitting';fields=@('fit_seconds')},@{name='Scoring and flags';fields=@('inference_seconds','decision_seconds')})
$lines=[Collections.Generic.List[string]]::new()
AddLines $lines @('\begin{figure*}[tp]\centering\begin{tikzpicture}',
'\begin{groupplot}[group style={group size=2 by 2,horizontal sep=2.4cm,vertical sep=1.65cm},width=0.40\textwidth,height=7.8cm,xbar,bar width=8pt,xmin=0,axis x line*=bottom,axis y line*=left,xmajorgrids=true,grid style={black!9},tick label style={font=\scriptsize},yticklabel style={font=\scriptsize,align=right},label style={font=\scriptsize},title style={font=\small},scaled x ticks=false,nodes near coords,every node near coord/.append style={font=\scriptsize,/pgf/number format/fixed,/pgf/number format/precision=4},enlarge y limits=0.10]')
foreach ($dataset in @('mnist','cifar10')) {
    $datasetLabel=if ($dataset -eq 'mnist') {'MNIST'} else {'CIFAR-10'}
    $rows=if ($dataset -eq 'mnist') {@($mnistStages | Where-Object {$_.method -eq 'ours' -and $_.kind -eq 'compute'})} else {@($phaseRows | Where-Object dataset -eq $dataset)}
    $ticks=@();$labels=@();$coordinates=@()
    for ($index=0;$index -lt $rows.Count;$index++) {
        $ticks+=$index+1
        $label=$rows[$index].label.Replace('Honest training','Local training').Replace('Fabricated responses','FR responses').Replace('Features and preparation','Features/preparation').Replace('Decisions and scoring','Decision/scoring')
        $labels+='{'+$label+$(if ($dataset -eq 'cifar10') {' ($n='+$rows[$index].rounds+'$)'} else {''})+'}'
        $coordinates+='('+(F (Num $rows[$index].mean_seconds) 6)+','+($index+1)+')'
    }
    $max=1.25*($rows | Measure-Object mean_seconds -Maximum).Maximum
    $kind=if ($dataset -eq 'mnist') {'stages'} else {'phases'}
    $axisLabel=if ($dataset -eq 'mnist') {'Mean seconds per round'} else {'Mean seconds per phase round'}
    $precisionOption=if ($dataset -eq 'cifar10') {',every node near coord/.append style={/pgf/number format/precision=2}'} else {''}
    $lines.Add('\nextgroupplot[title={BaitFL: '+$datasetLabel+' '+$kind+'},xmax='+(F $max 4)+',ytick={'+($ticks -join ',')+'},yticklabels={'+($labels -join ',')+'},y dir=reverse,xlabel={'+$axisLabel+'}'+$precisionOption+']')
    $lines.Add('\addplot[fill=honestblue!75,draw=honestblue] coordinates {'+($coordinates -join ' ')+'};')
    $ticks=@();$labels=@();$coordinates=@();$means=@()
    if ($dataset -eq 'mnist') {
        $rows=@($mnistStages | Where-Object {$_.method -eq 'std' -and $_.kind -eq 'compute'})
        for ($index=0;$index -lt $rows.Count;$index++) {
            $label=$rows[$index].label.Replace('Honest training','Local training').Replace('Fabricated responses','FR responses').Replace('Features and preparation','Features/preparation').Replace('Decisions and scoring','Decision/scoring')
            $mean=Num $rows[$index].mean_seconds;$means+=$mean;$ticks+=$index+1;$labels+='{'+$label+'}';$coordinates+='('+(F $mean 6)+','+($index+1)+')'
        }
    } else { for ($index=0;$index -lt $stdComponents.Count;$index++) {
        $component=$stdComponents[$index]
        $values=foreach ($round in $stdRows[$dataset]) {$total=0.;foreach ($field in $component.fields) {$total+=Num $round.$field};$total}
        $mean=Mean $values;$means+=$mean;$ticks+=$index+1;$labels+='{'+$component.name+'}';$coordinates+='('+(F $mean 6)+','+($index+1)+')'
    } }
    $max=1.25*($means | Measure-Object -Maximum).Maximum
    Require ([math]::Abs(($means | Measure-Object -Sum).Sum-($timingSummary | Where-Object dataset -eq $dataset).std_mean) -lt 1e-7) 'STD components do not sum to round compute'
    $lines.Add('\nextgroupplot[title={STD-DAGMM: '+$datasetLabel+'},xmax='+(F $max 4)+',ytick={'+($ticks -join ',')+'},yticklabels={'+($labels -join ',')+'},y dir=reverse,xlabel={Mean seconds per component}'+$precisionOption+']')
    $lines.Add('\addplot[fill=riderorange!75,draw=riderorange] coordinates {'+($coordinates -join ' ')+'};')
}
AddLines $lines @('\end{groupplot}\end{tikzpicture}', '\caption{Measured timing breakdowns.}\label{fig:timing-segments}', '\end{figure*}')
WriteFigure 'timing_segments_figure' $lines

$lines=[Collections.Generic.List[string]]::new()
AddLines $lines @('\begin{figure*}[tp]\centering\begin{tikzpicture}',
'\begin{groupplot}[group style={group size=2 by 1,horizontal sep=1.0cm},width=0.445\textwidth,height=5.8cm,ybar,bar width=17pt,xmin=0.4,xmax=2.6,ymin=0,xtick={1,2},xticklabels={{BaitFL},{STD-DAGMM}},axis x line*=bottom,axis y line*=left,ymajorgrids=true,grid style={black!9},tick label style={font=\scriptsize},label style={font=\scriptsize},title style={font=\small},scaled y ticks=false,nodes near coords,every node near coord/.append style={font=\small,/pgf/number format/fixed,/pgf/number format/precision=2}]')
foreach ($row in $timingSummary) {
    $datasetLabel=if ($row.dataset -eq 'mnist') {'MNIST'} else {'CIFAR-10'}
    $maximum=if ($row.dataset -eq 'mnist') {$row.std_wall_mean} else {$row.std_mean}
    $shift=if ($row.dataset -eq 'mnist') {-13} else {0}
    $lines.Add('\nextgroupplot[title={'+$datasetLabel+'},ylabel={Mean seconds per round},ymax='+(F (1.2*$maximum) 4)+']')
    $lines.Add('\addplot[bar shift='+$shift+'pt,fill=honestblue!75,draw=honestblue] coordinates {(1,'+(F $row.bait_mean 6)+') (2,'+(F $row.std_mean 6)+')};')
    if ($row.dataset -eq 'mnist') {$lines.Add('\addplot[bar shift=13pt,fill=black!35,draw=black!50] coordinates {(1,'+(F $row.bait_wall_mean 6)+') (2,'+(F $row.std_wall_mean 6)+')};')}
}
AddLines $lines @('\end{groupplot}\end{tikzpicture}', '\par\smallskip{\scriptsize\textcolor{honestblue}{\rule{0.25cm}{0.15cm}}\ Computation\qquad\textcolor{black!45}{\rule{0.25cm}{0.15cm}}\ Elapsed round time}', '\caption{Average round computation and elapsed time.}\label{fig:timing-phases}', '\end{figure*}')
WriteFigure 'timing_phases_figure' $lines

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
    if ($row.dataset -eq 'mnist') {$lines.Add('\addplot[black!55,dashed] table[col sep=comma,x=round,y=wall_gap] {'+$path+'};')}
    $lines.Add('\addplot[violet!75!black,densely dotted] coordinates {(1,'+(F $row.gap_mean 6)+') (100,'+(F $row.gap_mean 6)+')};')
    $annotation='Mean computation gap: '+(F $row.gap_mean)+' s'
    if ($row.dataset -eq 'mnist') {$annotation+='\\Mean elapsed gap: '+(F $row.wall_gap_mean)+' s'}
    $lines.Add('\node[anchor=north east,font=\scriptsize,align=right,fill=white,inner sep=2pt] at (rel axis cs:0.98,0.98) {'+$annotation+'};')
}
AddLines $lines @('\end{groupplot}\end{tikzpicture}',
'\par\smallskip{\scriptsize\textcolor{honestblue}{\rule{0.4cm}{0.8pt}}\ BaitFL\qquad\textcolor{riderorange}{\rule{0.4cm}{0.8pt}}\ STD-DAGMM\qquad\textcolor{black!55}{\textbf{-- --}}\ Elapsed-time gap (MNIST)}',
'\caption{Round timing trajectories and their measured differences.}\label{fig:timing-traces}', '\end{figure*}')
WriteFigure 'timing_timeline_figure' $lines

$lines=[Collections.Generic.List[string]]::new();$lines.Add('\input{generated/mnist_component_table.tex}')
AddLines $lines @('\begin{table*}[t]\centering\footnotesize', '\caption{Round timing over 100 rounds.}\label{tab:timing-horizons}', '\begin{tabular}{llrrrr}\toprule', '\multirow{2}{*}{Dataset} & \multirow{2}{*}{Workflow} & \multicolumn{2}{c}{Mean round time (s)} & \multicolumn{2}{c}{Full horizon (min)} \\', '\cmidrule(lr){3-4}\cmidrule(lr){5-6}', ' & & Computation & Elapsed & Computation & Elapsed \\ \midrule')
foreach ($row in $timingSummary) {
    $datasetLabel=if ($row.dataset -eq 'mnist') {'MNIST'} else {'CIFAR-10'}
    if ($row.dataset -eq 'cifar10') {$lines.Add('\midrule')}
    $firstMethod=$true
    foreach ($method in @(@('BaitFL','bait_mean','bait_wall_mean'),@('STD-DAGMM','std_mean','std_wall_mean'))) {
        $elapsed=if ($row.dataset -eq 'mnist') {F $row.($method[2])} else {'--'}
        $elapsedMinutes=if ($row.dataset -eq 'mnist') {F ($row.($method[2])*100/60)} else {'--'}
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
    $elapsed=if ($row.dataset -eq 'mnist') {F $row.mean_wall_seconds} else {'--'}
    $decision=if ($row.dataset -eq 'mnist') {$milliseconds=1000*$row.mean_decision_seconds;F $milliseconds $(if ($milliseconds -lt .01) {3} else {2})} else {'--'}
    $lines.Add(($datasetCell,$row.label,$row.rounds,(F $row.mean_seconds),$elapsed,$decision,(F $row.amortized_seconds) -join ' & ')+' \\')
}
AddLines $lines @('\bottomrule\end{tabular}\end{table*}')
WriteFigure 'timing_tables' $lines
$timingSummary | Format-Table -AutoSize | Out-String | Write-Output

$trendPath=Join-Path $PSScriptRoot 'generated/score_trends.tex'
$trend=[IO.File]::ReadAllText($trendPath)
$trend=$trend.Replace('horizontal sep=0.8cm','horizontal sep=1.3cm').Replace('width=0.455\textwidth','width=0.435\textwidth')
$trend=[regex]::Replace($trend,'\\caption\{.*?\}\\label\{fig:score-trends\}','\caption{Evolution of paired response scores.}\label{fig:score-trends}')
[IO.File]::WriteAllText($trendPath,$trend,[Text.UTF8Encoding]::new($false))
$recallPath=Join-Path $PSScriptRoot 'generated/recall_figure.tex'
$recall=[IO.File]::ReadAllText($recallPath)
$recall=[regex]::Replace($recall,'\\caption\{.*?\}\\label\{fig:recall\}','\caption{Free-rider removal over training.}\label{fig:recall}')
[IO.File]::WriteAllText($recallPath,$recall,[Text.UTF8Encoding]::new($false))
