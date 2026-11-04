$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$out=Join-Path $PSScriptRoot 'generated'
$export=Join-Path $out 'comparison'
$culture=[Globalization.CultureInfo]::InvariantCulture
function Num($v){[double]::Parse([string]$v,$culture)}
function Mean($v){[double](($v|Measure-Object -Average).Average)}
function F([double]$v,[int]$digits=2){$v.ToString("F$digits",$culture)}
function SaveTex($name,$lines){[IO.File]::WriteAllLines((Join-Path $out "$name.tex"),[string[]]$lines,[Text.UTF8Encoding]::new($false))}
function Add($lines,$values){foreach($v in $values){$lines.Add($v)}}
$pairs=@(Import-Csv (Join-Path $export 'paired_results.csv'))
$trajectories=@(Import-Csv (Join-Path $export 'paired_trajectories.csv'))
if($trajectories.Count -ne 100*$pairs.Count){throw 'Incomplete matched trajectory export'}
# Each attack has equal weight after averaging its available matched seeds.
$attackRounds=foreach($g in $trajectories|Group-Object dataset,split,share,attack,round){
 $r=$g.Group[0]
 [pscustomobject]@{dataset=$r.dataset;split=$r.split;share=[int]$r.share;attack=$r.attack;round=[int]$r.round;baseline=100*(Mean @($g.Group|ForEach-Object {Num $_.baseline_accuracy}));bait=100*(Mean @($g.Group|ForEach-Object {Num $_.bait_accuracy}))}
}
$accuracy=foreach($g in $attackRounds|Group-Object dataset,split,share,round){
 if($g.Count -ne 4){throw 'Attack missing from accuracy panel'}
 $r=$g.Group[0]
 [pscustomobject]@{dataset=$r.dataset;split=$r.split;share=$r.share;round=$r.round;baseline=Mean $g.Group.baseline;bait=Mean $g.Group.bait}
}
foreach($dataset in @('mnist','cifar10')){foreach($share in @(30,40)){foreach($split in @('iid','noniid')){
 @($accuracy|Where-Object {$_.dataset -eq $dataset -and $_.share -eq $share -and $_.split -eq $split}|Sort-Object round)|Export-Csv (Join-Path $export "accuracy_$($dataset)_$($split)_$share.csv") -NoTypeInformation -UseQuotes Never -Encoding utf8
}}}
foreach($view in @('late','full')){
 $lines=[Collections.Generic.List[string]]::new()
 Add $lines @('\begin{figure*}[tp]\centering\begin{tikzpicture}',
 '\begin{groupplot}[group style={group size=4 by 2,horizontal sep=0.70cm,vertical sep=1.25cm},scale only axis,width=0.197\textwidth,height=3.65cm,grid=major,grid style={black!8},axis line style={black!40},tick label style={font=\scriptsize},label style={font=\scriptsize},title style={font=\scriptsize},scaled y ticks=false,yticklabel style={/pgf/number format/fixed,/pgf/number format/precision=2}]')
 foreach($dataset in @('mnist','cifar10')){foreach($share in @(30,40)){foreach($split in @('iid','noniid')){
  $d=if($dataset -eq 'mnist'){'MNIST'}else{'CIFAR-10'};$s=if($split -eq 'iid'){'IID'}else{'Non-IID'}
  $range=if($view -eq 'full'){'xmin=1,xmax=100,ymin=0,ymax=100,xtick={1,50,100}'}else{
   $v=@($accuracy|Where-Object {$_.dataset -eq $dataset -and $_.share -eq $share -and $_.split -eq $split -and $_.round -ge 60}|ForEach-Object {$_.baseline;$_.bait})
   $pad=if($dataset -eq 'mnist'){.035}else{.12}
   'xmin=60,xmax=100,xtick={60,80,100},ymin='+(F (($v|Measure-Object -Minimum).Minimum-$pad) 4)+',ymax='+(F (($v|Measure-Object -Maximum).Maximum+$pad) 4)
  }
  $axis=if($share -eq 30 -and $split -eq 'iid'){',ylabel={Test accuracy (\%)}'}else{''}
  if($dataset -eq 'cifar10'){$axis+=',xlabel={Round}'}
  $lines.Add('\nextgroupplot[title={'+$d+', '+$share+'\% '+$s+'},'+$range+$axis+']')
  $path="generated/comparison/accuracy_$($dataset)_$($split)_$share.csv"
  $lines.Add('\addplot[black!65,dashed,thick,mark=square*,mark size=1.1pt,mark repeat=10] table[col sep=comma,x=round,y=baseline] {'+$path+'};')
  $lines.Add('\addplot[violet!85!black,thick,mark=*,mark size=1.1pt,mark repeat=10] table[col sep=comma,x=round,y=bait] {'+$path+'};')
 }}}
 Add $lines @('\end{groupplot}\end{tikzpicture}','\par\smallskip{\scriptsize\textcolor{violet!85!black}{\rule{0.4cm}{0.8pt}}\ BaitFL\qquad\textcolor{black!65}{\textbf{-- --}}\ No defense}')
 if($view -eq 'late'){$lines.Add('\caption{Late-training accuracy from available completed, seed-matched runs. Panels separate partition and free-rider proportion, with independent vertical scales. Curves average matched seeds within each attack, then weight the four attacks equally.}\label{fig:accuracy}');$name='accuracy_figure'}
 else{$lines.Add('\caption{Full training trajectories for the same completed matched cases used in Figure~\ref{fig:accuracy}.}\label{fig:accuracy-overview}');$name='accuracy_overview_figure'}
 $lines.Add('\end{figure*}');SaveTex $name $lines
}
# Replace the histogram with a direct, representative certificate/removal timeline.
$lines=[Collections.Generic.List[string]]::new()
Add $lines @('\begin{figure*}[tp]\centering\begin{tikzpicture}',
'\begin{groupplot}[group style={group size=2 by 1,horizontal sep=1cm},width=0.445\textwidth,height=5cm,ymin=0,xmin=15,xmax=85,xtick={20,30,40,50,60,70,80},ymajorgrids=true,grid style={black!8},tick label style={font=\scriptsize},title style={font=\small},label style={font=\scriptsize},xlabel={Completed cycle (round)},ylabel={Clients}]')
foreach($share in @(40,30)){
 $run=Join-Path $root "results/v15_4_cifar10_seed42_fr$share/v15_4_cifar10_noniid_FR3_seed42"
 $decisions=@(Import-Csv (Join-Path $run 'cycle_decisions.csv'));$removals=@(Import-Csv (Join-Path $run 'removals.csv'))
 $last=($removals|Where-Object is_free_rider -eq '1'|Measure-Object round -Maximum).Maximum
 $rows=foreach($g in $decisions|Group-Object round|Sort-Object {[int]$_.Name}){
  $round=[int]$g.Name;if($round -gt $last){continue}
  $fresh=@($g.Group|Where-Object {($_.strong_channels -split ',') -contains 'norm_low'})
  [pscustomobject]@{round=$round;honest=@($fresh|Where-Object is_free_rider -eq '0').Count;rider=@($fresh|Where-Object is_free_rider -eq '1').Count;removed=@($removals|Where-Object {[int]$_.round -eq $round -and $_.is_free_rider -eq '1'}).Count}
 }
 $rows|Export-Csv (Join-Path $export "evidence_timeline_$share.csv") -NoTypeInformation -UseQuotes Never -Encoding utf8
 $path="generated/comparison/evidence_timeline_$share.csv"
 $lines.Add('\nextgroupplot[title={CIFAR-10 non-IID FR3, '+$share+'\%},ymax='+($share+8)+']')
 $lines.Add('\addplot[ybar,/pgf/bar width=6pt,/pgf/bar shift=-4pt,fill=honestblue!60,draw=honestblue] table[col sep=comma,x=round,y=honest] {'+$path+'};')
 $lines.Add('\addplot[ybar,/pgf/bar width=6pt,/pgf/bar shift=4pt,fill=riderorange!65,draw=riderorange] table[col sep=comma,x=round,y=rider] {'+$path+'};')
 $coords=@($rows|Where-Object removed -gt 0|ForEach-Object {'('+ $_.round+','+$_.removed+')'})
 $lines.Add('\addplot[only marks,black,mark=diamond*,mark size=3.2pt] coordinates {'+($coords -join ' ')+'};')
}
Add $lines @('\end{groupplot}\end{tikzpicture}',
'\par\smallskip{\scriptsize\textcolor{honestblue}{\rule{0.25cm}{0.15cm}}\ Honest: fresh certificates\quad\textcolor{riderorange}{\rule{0.25cm}{0.15cm}}\ Free riders: fresh certificates\quad$\blacklozenge$\ Newly removed free riders}',
'\caption{How fresh evidence leads to removal in representative executions. Bars count fresh norm certificates on both traps in a completed cycle. Diamonds mark new free-rider removals. A first certificate can precede removal by several cycles.}\label{fig:evidence-timeline}','\end{figure*}')
SaveTex 'evidence_timeline' $lines
# All four attacks, both datasets: seed-averaged paired norm-z, no shaded bands.
$study=@(Import-Csv (Join-Path $out 'multiseed/per_run.csv'))
$seedScores=[Collections.Generic.List[object]]::new()
foreach($run in $study|Where-Object {$_.split -eq 'noniid' -and [int]$_.share -eq 40}){
 $rows=@(Import-Csv (Join-Path $root ($run.source+'/cycle_signals.csv')))
 $clientPairs=foreach($g in $rows|Group-Object round,client_id){
  if($g.Count -ne 2 -or @($g.Group.trap_id|Select-Object -Unique).Count -ne 2){continue}
  $v=@();foreach($r in $g.Group){$number=0.;if([double]::TryParse([string]$r.norm_z,[Globalization.NumberStyles]::Float,$culture,[ref]$number) -and [double]::IsFinite($number)){$v+=$number}}
  if($v.Count -eq 2){[pscustomobject]@{round=[int]$g.Group[0].round;label=[int]$g.Group[0].is_free_rider;value=Mean $v}}
 }
 foreach($g in $clientPairs|Group-Object round,label){
  $r=$g.Group[0];$seedScores.Add([pscustomobject]@{dataset=$run.dataset;attack=$run.attack;seed=$run.seed;round=$r.round;label=$r.label;value=Mean $g.Group.value;clients=$g.Count})
 }
}
$seedScores|Export-Csv (Join-Path $export 'norm_trend_seed_means.csv') -NoTypeInformation -Encoding utf8
$trends=foreach($g in $seedScores|Group-Object dataset,attack,round,label){$r=$g.Group[0];[pscustomobject]@{dataset=$r.dataset;attack=$r.attack;round=$r.round;label=$r.label;value=Mean $g.Group.value;available_seed_means=$g.Count}}
$lines=[Collections.Generic.List[string]]::new()
Add $lines @('\begin{figure*}[tp]\centering\begin{tikzpicture}',
'\begin{groupplot}[group style={group size=4 by 2,horizontal sep=0.50cm,vertical sep=1.25cm},scale only axis,width=0.207\textwidth,height=3.55cm,xmin=18,xmax=102,xtick={20,60,100},grid=major,grid style={black!8},axis line style={black!40},tick label style={font=\scriptsize},title style={font=\scriptsize},label style={font=\scriptsize},scaled ticks=false,unbounded coords=jump]')
foreach($dataset in @('mnist','cifar10')){foreach($attack in @('FR1','FR2','FR3','FR4')){
 $d=if($dataset -eq 'mnist'){'MNIST'}else{'CIFAR-10'}
 $axis=if($attack -eq 'FR1'){',ylabel={Mean paired norm-z}'}else{''};if($dataset -eq 'cifar10'){$axis+=',xlabel={Decision round}'}
 $lastRound=($trends|Where-Object {$_.dataset -eq $dataset -and $_.attack -eq $attack}|Measure-Object round -Maximum).Maximum
 $ticks=if($lastRound -le 40){'20,30,40'}elseif($lastRound -le 80){'20,40,60,80'}else{'20,60,100'}
 $axis+=',xmax='+($lastRound+2)+',xtick={'+$ticks+'}'
 $lines.Add('\nextgroupplot[title={'+$d+' '+$attack+'}'+$axis+']')
 foreach($label in @(0,1)){
  $data=@($trends|Where-Object {$_.dataset -eq $dataset -and $_.attack -eq $attack -and $_.label -eq $label}|Sort-Object round)
  $name="norm_trend_$($dataset)_$($attack)_$label.csv"
  if(-not $data.Count){throw 'Missing class from score trajectory'}
  $data|Export-Csv (Join-Path $export $name) -NoTypeInformation -UseQuotes Never -Encoding utf8
  $style=if($label -eq 0){'honestblue,mark=o'}else{'riderorange,mark=triangle*'}
  $lines.Add('\addplot['+$style+',thick,mark size=1.8pt] table[col sep=comma,x=round,y=value] {generated/comparison/'+$name+'};')
 }
}}
Add $lines @('\end{groupplot}\end{tikzpicture}',
'\par\smallskip{\scriptsize\textcolor{honestblue}{$\circ$}\ Honest\qquad\textcolor{riderorange}{$\blacktriangle$}\ Free rider}',
'\caption{Paired norm-z across all four attacks under non-IID data and 40\% free riders. Client scores are averaged within each seed, then across available seed means. Only finite, complete pairs are used. Contributing populations can change after removal or missing measurements. Panel scales are independent.}\label{fig:score-trends}','\end{figure*}')
SaveTex 'score_trends' $lines
# Publication timing summaries use per-round sums before computing sample SD.
function Sd($values){
 $v=@($values);if($v.Count -lt 2){return 0.}
 $m=Mean $v;$ss=0.;foreach($x in $v){$ss+=([double]$x-$m)*([double]$x-$m)}
 [Math]::Sqrt($ss/($v.Count-1))
}
function RoundSum($row,$fields){$sum=0.;foreach($field in $fields){$sum+=Num $row.$field};$sum}
function MeanSd($mean,$sd){
 if($mean -eq 0 -and $sd -eq 0){return '$0$'}
 $digits=if($mean -gt 0 -and $mean -lt .01){4}elseif($mean -gt 0 -and $mean -lt 1){3}else{2}
 '$'+(F $mean $digits)+' \pm '+(F $sd $digits)+'$'
}
$stats=@{};$summaries=@{};$native=@{}
foreach($dataset in @('mnist','cifar10')){
 $stats[$dataset]=@(Import-Csv (Join-Path $export "$($dataset)_stage_statistics.csv"))
 $summaries[$dataset]=Get-Content (Join-Path $export "instrumented_$($dataset)_summary.json") -Raw|ConvertFrom-Json
 $evidence=Join-Path $PSScriptRoot "evidence/timing_$($dataset)_20261103"
 $native[$dataset]=@{
  ours=@(Import-Csv (Join-Path $evidence 'ours/round_timings.csv'))
  std=@(Import-Csv (Join-Path $evidence 'std/segment_timings.csv'))
 }
 foreach($method in @('ours','std')){if($native[$dataset][$method].Count -ne 100){throw 'Incomplete native timing series'}}
}
$fields=@{
 training=@{ours=@('honest_training_seconds');std=@('honest_training_seconds')}
 responses=@{ours=@('fabrication_seconds');std=@('fabrication_seconds')}
 client_eval=@{ours=@('client_evaluation_seconds');std=@()}
 traps=@{ours=@('trap_generation_seconds');std=@()}
 scheduling=@{ours=@('scheduling_seconds');std=@()}
 features=@{ours=@('feature_seconds','model_preparation_seconds');std=@('preparation_seconds')}
 fitting=@{ours=@();std=@('fit_seconds')}
 decision=@{ours=@('decision_seconds');std=@('inference_seconds','decision_seconds')}
 aggregation=@{ours=@('aggregation_seconds');std=@('aggregation_seconds')}
 evaluation=@{ours=@('evaluation_seconds');std=@('evaluation_seconds')}
 publication=@{ours=@('response_bookkeeping_seconds','reporting_seconds','checkpoint_seconds');std=@('reporting_seconds','checkpoint_seconds')}
 unassigned=@{ours=@('unassigned_seconds');std=@('unassigned_seconds')}
}
$definitions=@(
 @('Honest local training',@('training')),@('Fabricated responses',@('responses')),
 @('Client diagnostic evaluation',@('client_eval')),@('Traps and scheduling',@('traps','scheduling')),
 @('Response features and preparation',@('features')),@('Auxiliary detector fitting',@('fitting')),
 @('Scoring and state decisions',@('decision')),@('Aggregation',@('aggregation')),@('Global evaluation',@('evaluation')),
 @('Logging and checkpoints',@('publication')),@('Unassigned runtime',@('unassigned')))
$tableStats=[Collections.Generic.List[object]]::new()
$lines=[Collections.Generic.List[string]]::new()
Add $lines @('\begin{table*}[t]\centering\footnotesize\setlength{\tabcolsep}{4pt}',
'\caption{Round-time breakdown.}\label{tab:std-segments}',
'\begin{tabular}{lrrrr}\toprule',
'\multirow{2}{*}{Stage} & \multicolumn{2}{c}{MNIST} & \multicolumn{2}{c}{CIFAR-10} \\',
'\cmidrule(lr){2-3}\cmidrule(lr){4-5}',
' & BaitFL & STD-DAGMM & BaitFL & STD-DAGMM \\ \midrule')
foreach($definition in $definitions){
 if($definition[0] -eq 'Logging and checkpoints'){$lines.Add('\midrule')}
 $cells=@($definition[0])
 foreach($dataset in @('mnist','cifar10')){foreach($method in @('ours','std')){
  $sumFields=@();$expected=0.
  foreach($stage in $definition[1]){
   $sumFields+=@($fields[$stage][$method])
   $stageRow=@($stats[$dataset]|Where-Object {$_.method -eq $method -and $_.stage -eq $stage})[0]
   $expected+=Num $stageRow.mean_seconds
  }
  $values=@($native[$dataset][$method]|ForEach-Object {RoundSum $_ $sumFields})
  $mean=Mean $values;$sd=Sd $values
  if([Math]::Abs($mean-$expected) -gt 1e-8){throw 'Stage mean mismatch'}
  $tableStats.Add([pscustomobject]@{dataset=$dataset;method=$method;stage=$definition[0];rounds=$values.Count;mean_seconds=$mean;sample_sd_seconds=$sd})
  $cells+=MeanSd $mean $sd
 }}
 $lines.Add(($cells -join ' & ')+' \\')
}
$lines.Add('\midrule')
$cells=@('Checking subtotal (included above)')
foreach($dataset in @('mnist','cifar10')){foreach($method in @('ours','std')){
 $checkingStages=if($method -eq 'ours'){@('traps','scheduling','features','decision')}else{@('features','fitting','decision')}
 $sumFields=@();foreach($stage in $checkingStages){$sumFields+=@($fields[$stage][$method])}
 $values=@($native[$dataset][$method]|ForEach-Object {RoundSum $_ $sumFields})
 $mean=Mean $values;$sd=Sd $values
 $expected=if($method -eq 'ours'){$summaries[$dataset].ours_auditing_mean}else{$summaries[$dataset].std_detector_mean}
 if([Math]::Abs($mean-$expected) -gt 1e-8){throw 'Checking subtotal mismatch'}
 $tableStats.Add([pscustomobject]@{dataset=$dataset;method=$method;stage='Checking subtotal';rounds=$values.Count;mean_seconds=$mean;sample_sd_seconds=$sd})
 $cells+=MeanSd $mean $sd
}}
$lines.Add(($cells -join ' & ')+' \\')
$cells=@('Checking share of computation (\%)')
foreach($dataset in @('mnist','cifar10')){$s=$summaries[$dataset];$cells+=F (100*$s.ours_auditing_mean/$s.bait_mean);$cells+=F (100*$s.std_detector_mean/$s.std_mean)}
$lines.Add(($cells -join ' & ')+' \\')
$lines.Add('\midrule')
$lines.Add('\multicolumn{5}{l}{\textit{BaitFL time saved relative to STD-DAGMM}} \\')
foreach($definition in @(@('Computation saved: s/round (\%)','gap_mean','bait_reduction_pct'),@('Elapsed saved: s/round (\%)','wall_gap_mean','wall_reduction_pct'))){
 $cells=@($definition[0])
 foreach($dataset in @('mnist','cifar10')){
  $s=$summaries[$dataset]
  $cells+='\multicolumn{2}{c}{'+(F $s.($definition[1]))+' ('+(F $s.($definition[2]))+'\%)}'
 }
 $lines.Add(($cells -join ' & ')+' \\')
}
Add $lines @('\bottomrule\end{tabular}',
'\par\smallskip\parbox{0.94\textwidth}{\scriptsize Times are mean $\pm$ sample SD in seconds per round over 100 rounds. Combined stages are summed per round before calculating SD. Checking subtotals are included in the preceding stages. Shares and savings use complete-horizon means, relative to STD-DAGMM for savings.}',
'\end{table*}')
SaveTex 'timing_compact_table' $lines
$tableStats|Export-Csv (Join-Path $export 'timing_table_statistics.csv') -NoTypeInformation -Encoding utf8

# Compare methods within each metric, using adjacent bars and method colors.
$lines=[Collections.Generic.List[string]]::new()
Add $lines @('\begin{figure*}[t]\centering\begin{tikzpicture}',
'\begin{groupplot}[group style={group size=2 by 1,horizontal sep=1.1cm},scale only axis,width=0.405\textwidth,height=4.6cm,ybar,/pgf/bar width=15pt,xmin=0.5,xmax=2.5,ymin=0,xtick={1,2},xticklabels={{Computation},{Elapsed}},axis x line*=bottom,axis y line*=left,ymajorgrids=true,grid style={black!8},tick label style={font=\small},label style={font=\small},title style={font=\small},scaled y ticks=false,nodes near coords,every node near coord/.append style={font=\scriptsize,/pgf/number format/fixed,/pgf/number format/precision=2,/pgf/number format/fixed zerofill}]')
foreach($dataset in @('mnist','cifar10')){
 $s=$summaries[$dataset];$d=if($dataset -eq 'mnist'){'MNIST'}else{'CIFAR-10'}
 $ymax=1.18*[Math]::Max($s.std_wall_mean,$s.bait_wall_mean)
 $lines.Add('\nextgroupplot[title={'+$d+'},ylabel={Mean seconds per round},ymax='+(F $ymax 4)+']')
 $lines.Add('\addplot[/pgf/bar shift=-9pt,fill=baitteal!85,draw=baitteal] coordinates {(1,'+(F $s.bait_mean 6)+') (2,'+(F $s.bait_wall_mean 6)+')};')
 $lines.Add('\addplot[/pgf/bar shift=9pt,fill=stdorange!85,draw=stdorange] coordinates {(1,'+(F $s.std_mean 6)+') (2,'+(F $s.std_wall_mean 6)+')};')
}
Add $lines @('\end{groupplot}\end{tikzpicture}',
'\par\smallskip{\small\textcolor{baitteal}{\rule{0.35cm}{0.18cm}}\ BaitFL\qquad\textcolor{stdorange}{\rule{0.35cm}{0.18cm}}\ STD-DAGMM}',
'\caption{Average computation and elapsed time per round.}\label{fig:timing-phases}',
'\end{figure*}')
SaveTex 'timing_phases_figure' $lines

# Detection completion adds information beyond final recall, over the whole study.
$completion=foreach($g in $study|Group-Object dataset,split,share,attack){
 $r=$g.Group[0];$values=@($g.Group|ForEach-Object {Num $_.completion_round})
 if(@($values|Where-Object {$_ -lt 1 -or $_ -gt 100}).Count){throw 'Cannot summarize an incomplete detection as a completion time'}
 $mean=Mean $values;$min=($values|Measure-Object -Minimum).Minimum;$max=($values|Measure-Object -Maximum).Maximum
 [pscustomobject]@{dataset=$r.dataset;split=$r.split;share=[int]$r.share;attack=$r.attack;replications=$g.Count;mean=$mean;minimum=$min;maximum=$max;lower=$mean-$min;upper=$max-$mean}
}
$completion|Export-Csv (Join-Path $export 'completion_round_groups.csv') -NoTypeInformation -Encoding utf8
$lines=[Collections.Generic.List[string]]::new()
Add $lines @('\begin{figure*}[tp]\centering\begin{tikzpicture}',
'\begin{groupplot}[group style={group size=2 by 1,horizontal sep=1.1cm},scale only axis,width=0.405\textwidth,height=4.7cm,xmin=0.5,xmax=4.5,ymin=20,ymax=100,xtick={1,2,3,4},xticklabels={FR1,FR2,FR3,FR4},ytick={30,50,70,90},axis x line*=bottom,axis y line*=left,ymajorgrids=true,grid style={black!8},tick label style={font=\small},label style={font=\small},title style={font=\small},scaled y ticks=false]')
$configs=@(
 @{split='iid';share=30;offset=-.27;style='baitteal,mark=o,mark options={fill=white}'},
 @{split='iid';share=40;offset=-.09;style='baitteal,mark=square*,mark options={fill=baitteal}'},
 @{split='noniid';share=30;offset=.09;style='violet!80!black,mark=o,mark options={fill=white}'},
 @{split='noniid';share=40;offset=.27;style='violet!80!black,mark=square*,mark options={fill=violet!80!black}'})
foreach($dataset in @('mnist','cifar10')){
 $d=if($dataset -eq 'mnist'){'MNIST'}else{'CIFAR-10'}
 $lines.Add('\nextgroupplot[title={'+$d+'},ylabel={Complete-removal round}]')
 foreach($cfg in $configs){
  $coords=foreach($attack in @('FR1','FR2','FR3','FR4')){
   $r=@($completion|Where-Object {$_.dataset -eq $dataset -and $_.split -eq $cfg.split -and $_.share -eq $cfg.share -and $_.attack -eq $attack})[0]
   $x=[int]$attack.Substring(2)+$cfg.offset
   '('+(F $x 3)+','+(F $r.mean 5)+') += (0,'+(F $r.upper 5)+') -= (0,'+(F $r.lower 5)+')'
  }
  $lines.Add('\addplot[only marks,'+$cfg.style+',mark size=2.5pt,thick,error bars/.cd,y dir=both,y explicit,error bar style={line width=0.8pt},error mark options={rotate=90,mark size=2.4pt}] coordinates {'+($coords -join ' ')+'};')
 }
}
Add $lines @('\end{groupplot}\end{tikzpicture}',
'\par\smallskip{\small\textcolor{baitteal}{$\circ$}\ 30\% IID\quad\textcolor{baitteal}{$\blacksquare$}\ 40\% IID\quad\textcolor{violet!80!black}{$\circ$}\ 30\% non-IID\quad\textcolor{violet!80!black}{$\blacksquare$}\ 40\% non-IID}',
'\caption{Free-rider removal completion rounds.}\label{fig:completion-rounds}',
'\end{figure*}')
SaveTex 'completion_rounds_figure' $lines

