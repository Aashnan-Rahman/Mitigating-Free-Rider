$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$out=Join-Path $PSScriptRoot 'generated'
$export=Join-Path $out 'comparison'
$culture=[Globalization.CultureInfo]::InvariantCulture
function N($v){[double]::Parse([string]$v,$culture)}
function Mean($v){[double](($v|Measure-Object -Average).Average)}
function F($v){([double]$v).ToString('F5',$culture)}
$study=@(Import-Csv (Join-Path $out 'multiseed/per_run.csv'))
$matched=@(Import-Csv (Join-Path $export 'paired_trajectories.csv'))
$matchedCases=@(Import-Csv (Join-Path $export 'paired_results.csv'))
if($study.Count -ne 96 -or $matched.Count -ne 100*$matchedCases.Count){throw 'Incomplete accuracy inputs'}
$rows=[Collections.Generic.List[object]]::new();$hashes=[Collections.Generic.List[object]]::new()
foreach($run in $study){
 $relative=$run.source+'/global_metrics.csv';$path=Join-Path $root $relative
 $global=@(Import-Csv $path)
 if($global.Count -ne 100){throw 'Incomplete primary accuracy trajectory'}
 if([Math]::Abs((N $global[-1].global_accuracy)-(N $run.final_accuracy)) -gt 1e-10){throw 'Final accuracy mismatch'}
 $hashes.Add([pscustomobject]@{path=$relative;sha256=(Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant()})
 for($i=0;$i -lt 100;$i++){
  if([int]$global[$i].round -ne $i+1){throw 'Unordered accuracy rounds'}
  $value=N $global[$i].global_accuracy
  if(-not [double]::IsFinite($value) -or $value -lt 0 -or $value -gt 1){throw 'Invalid accuracy'}
  $rows.Add([pscustomobject]@{dataset=$run.dataset;split=$run.split;share=$run.share;attack=$run.attack;seed=$run.seed;round=$i+1;accuracy=$value})
 }
}
$attackMeans=[Collections.Generic.List[object]]::new()
foreach($g in $rows|Group-Object dataset,split,share,attack,round){
 if($g.Count -ne 3 -or @($g.Group.seed|Select-Object -Unique).Count -ne 3){throw 'Primary curve is not a three-seed mean'}
 $r=$g.Group[0];$attackMeans.Add([pscustomobject]@{method='bait';dataset=$r.dataset;split=$r.split;share=$r.share;attack=$r.attack;round=$r.round;replications=$g.Count;accuracy=100*(Mean $g.Group.accuracy)})
}
foreach($g in $matched|Group-Object dataset,split,share,attack,round){
 $r=$g.Group[0];$values=@($g.Group|ForEach-Object {N $_.baseline_accuracy})
 $attackMeans.Add([pscustomobject]@{method='baseline';dataset=$r.dataset;split=$r.split;share=$r.share;attack=$r.attack;round=[int]$r.round;replications=$g.Count;accuracy=100*(Mean $values)})
}
$curves=foreach($g in $attackMeans|Group-Object method,dataset,split,share,round){
 if($g.Count -ne 4){throw 'Missing attack in accuracy panel'}
 $r=$g.Group[0]
 [pscustomobject]@{method=$r.method;dataset=$r.dataset;split=$r.split;share=$r.share;round=$r.round;accuracy=Mean $g.Group.accuracy;minimum_replications=($g.Group|Measure-Object replications -Minimum).Minimum;maximum_replications=($g.Group|Measure-Object replications -Maximum).Maximum}
}
$curves|Export-Csv (Join-Path $export 'accuracy_population_means.csv') -NoTypeInformation -Encoding utf8
$attackMeans|Export-Csv (Join-Path $export 'accuracy_population_attack_means.csv') -NoTypeInformation -Encoding utf8
$tablePrimary=@(Import-Csv (Join-Path $out 'multiseed/table1_means.csv'))
$tableBaseline=@(Import-Csv (Join-Path $export 'baseline_group_means.csv'))
foreach($g in $curves|Where-Object round -eq 100){
 $expected=if($g.method -eq 'bait'){
  $r=@($tablePrimary|Where-Object {$_.dataset -eq $g.dataset -and $_.split -eq $g.split -and $_.share -eq $g.share})[0]
  100*(Mean @('FR1','FR2','FR3','FR4'|ForEach-Object {N $r.("accuracy_$_")}))
 }else{
  $r=@($tableBaseline|Where-Object {$_.dataset -eq $g.dataset -and $_.split -eq $g.split -and $_.share -eq $g.share})[0]
  100*(N $r.baseline_accuracy)
 }
 if([Math]::Abs($expected-$g.accuracy) -gt 1e-8){throw 'Accuracy endpoint/table mismatch'}
}
$coverage=foreach($g in $matchedCases|Group-Object dataset,split,share,attack){$r=$g.Group[0];[pscustomobject]@{dataset=$r.dataset;split=$r.split;share=$r.share;attack=$r.attack;replications=$g.Count}}
$coverage|Export-Csv (Join-Path $export 'accuracy_baseline_coverage.csv') -NoTypeInformation -Encoding utf8
$labels=@{}
foreach($dataset in @('mnist','cifar10')){
 $v=@($coverage|Where-Object dataset -eq $dataset|ForEach-Object replications)
 $min=($v|Measure-Object -Minimum).Minimum;$max=($v|Measure-Object -Maximum).Maximum
 $labels[$dataset]=if($min -eq $max){[string]$min}else{"$min--$max"}
}
$lines=[Collections.Generic.List[string]]::new()
$lines.Add('\begin{figure*}[!t]\centering\begin{tikzpicture}')
$lines.Add('\begin{groupplot}[group style={group size=4 by 2,horizontal sep=0.7cm,vertical sep=1.1cm},scale only axis,width=0.195\textwidth,height=0.195\textwidth,xmin=20,xmax=100,xtick={20,60,100},grid=major,grid style={black!8},axis line style={black!45},tick label style={font=\scriptsize},title style={font=\small},label style={font=\scriptsize},scaled ticks=false,yticklabel style={/pgf/number format/fixed,/pgf/number format/precision=1}]')
foreach($dataset in @('mnist','cifar10')){
 $range=@($curves|Where-Object {$_.dataset -eq $dataset -and $_.round -ge 20}|ForEach-Object accuracy)
 $pad=if($dataset -eq 'mnist'){.06}else{.3}
 $lo=($range|Measure-Object -Minimum).Minimum-$pad;$hi=($range|Measure-Object -Maximum).Maximum+$pad
 foreach($share in @(30,40)){foreach($split in @('iid','noniid')){
  $d=if($dataset -eq 'mnist'){'MNIST'}else{'CIFAR-10'};$s=if($split -eq 'iid'){'IID'}else{'non-IID'}
  $axis=if($share -eq 30 -and $split -eq 'iid'){',ylabel={Test accuracy (\%)}'}else{',yticklabels=\empty'}
  if($dataset -eq 'cifar10'){$axis+=',xlabel={Round}'}
  $lines.Add('\nextgroupplot[title={'+$d+', '+$share+'\% '+$s+'},ymin='+(F $lo)+',ymax='+(F $hi)+$axis+']')
  foreach($method in @('baseline','bait')){
   $data=@($curves|Where-Object {$_.dataset -eq $dataset -and $_.split -eq $split -and $_.share -eq $share -and $_.method -eq $method}|Sort-Object round)
   if($data.Count -ne 100){throw 'Incomplete rendered curve'}
   $file="comparison/accuracy_all_$($method)_$($dataset)_$($split)_$share.csv"
   $data|Export-Csv (Join-Path $out $file) -NoTypeInformation -UseQuotes Never -Encoding utf8
   $style=if($method -eq 'bait'){'baitteal,thick,mark=*,mark size=1pt,mark repeat=10'}else{'stdorange,dashed,thick,mark=square*,mark size=1pt,mark repeat=10'}
   $lines.Add('\addplot['+$style+'] table[col sep=comma,x=round,y=accuracy] {generated/'+$file+'};')
  }
 }}
}
$lines.Add('\end{groupplot}\end{tikzpicture}')
$lines.Add('\par\smallskip{\small\textcolor{baitteal}{\rule{0.4cm}{0.8pt}}\ BaitFL\qquad\textcolor{stdorange}{-- --}\ No defense}')
$lines.Add('\caption{Mean global test accuracy during training. BaitFL uses three replications per setting. No-defense coverage is one replication per setting on MNIST and two to three on CIFAR-10.}\label{fig:accuracy-comparison}')
$lines.Add('\end{figure*}')
[IO.File]::WriteAllLines((Join-Path $out 'accuracy_comparison.tex'),$lines,[Text.UTF8Encoding]::new($false))
@{primary_runs=$study.Count;baseline_runs=$matchedCases.Count;primary_replications_per_attack=3;baseline_coverage=$coverage;averaging='Mean replications within attack, then four attacks equally; primary uses all three, baseline all completed matched records';display_rounds='20-100';comparison_scope='Descriptive unbalanced-coverage curves; paired utility estimates remain in baseline table';primary_inputs=$hashes;baseline_provenance='generated/comparison/provenance.json'}|ConvertTo-Json -Depth 7|Set-Content (Join-Path $export 'accuracy_population_provenance.json') -Encoding utf8
$preview=@('\documentclass[border=6pt]{standalone}','\usepackage{amsmath,amssymb,pgfplots,mathptmx}','\usepgfplotslibrary{groupplots}','\pgfplotsset{compat=1.18}','\definecolor{baitteal}{HTML}{187F8C}','\definecolor{stdorange}{HTML}{D87A30}','\setlength{\textwidth}{18.2cm}','\begin{document}\begin{minipage}{18.2cm}\centering')
$preview+=@($lines|ForEach-Object {$_ -replace '^\\begin\{figure\*\}\[tp\]\\centering',''}|Where-Object {$_ -notmatch '^\\caption|^\\end\{figure\*\}'})
$preview+=@('\par\smallskip{\scriptsize BaitFL: all three study replications. Baseline: available completed replications; coverage remains unequal.}','\end{minipage}\end{document}')
[IO.File]::WriteAllLines((Join-Path $PSScriptRoot 'build/figure5_preview.tex'),$preview,[Text.UTF8Encoding]::new($false))
