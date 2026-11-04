$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$out=Join-Path $PSScriptRoot 'generated'
$culture=[Globalization.CultureInfo]::InvariantCulture
function N($v){[double]::Parse([string]$v,$culture)}
function F($v){([double]$v).ToString('F7',$culture)}
function Q($values,$q){
 $ordered=@($values|Sort-Object);$pos=($ordered.Count-1)*$q
 $lo=[int][Math]::Floor($pos);$hi=[int][Math]::Ceiling($pos)
 $ordered[$lo]+($pos-$lo)*($ordered[$hi]-$ordered[$lo])
}
$runs=@(Import-Csv (Join-Path $out 'multiseed/per_run.csv'))
$clients=[Collections.Generic.List[object]]::new()
$boxes=[Collections.Generic.List[object]]::new()
$inputs=[Collections.Generic.List[object]]::new()
foreach($dataset in @('mnist','cifar10')){foreach($attack in @('FR1','FR2','FR3','FR4')){
 $run=@($runs|Where-Object {$_.dataset -eq $dataset -and $_.split -eq 'noniid' -and $_.share -eq '40' -and $_.seed -eq '42' -and $_.attack -eq $attack})
 if($run.Count -ne 1){throw 'Representative diagnostic case missing'}
 $relative=$run[0].source+'/client_metrics.csv';$path=Join-Path $root $relative
 $inputs.Add([pscustomobject]@{path=$relative;sha256=(Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant()})
 $rows=@(Import-Csv $path|Where-Object {[int]$_.round -ge 11 -and [int]$_.round -le 20})
 if($rows.Count -ne 1000){throw 'Incomplete initial-coverage diagnostic'}
 foreach($g in $rows|Group-Object client_id,was_trapped){
  $first=$g.Group[0];$trap=[int]$first.was_trapped
  if($g.Count -ne $(if($trap){2}else{8})){throw 'Unexpected first-cycle challenge coverage'}
  $values=@($g.Group|ForEach-Object {N $_.delta_norm})
  foreach($v in $values){if(-not [double]::IsFinite($v) -or $v -lt 0){throw 'Invalid update norm'}}
  $mean=($values|Measure-Object -Average).Average
  $clients.Add([pscustomobject]@{dataset=$dataset;attack=$attack;client_id=$first.client_id;is_free_rider=[int]$first.is_free_rider;trap=$trap;observations=$g.Count;mean_norm=$mean;asinh_mean_norm=[Math]::Asinh($mean)})
 }
 foreach($label in @(0,1)){foreach($trap in @(0,1)){
  $v=@($clients|Where-Object {$_.dataset -eq $dataset -and $_.attack -eq $attack -and $_.is_free_rider -eq $label -and $_.trap -eq $trap}|ForEach-Object asinh_mean_norm)
  if($v.Count -ne $(if($label){40}else{60})){throw 'Incorrect diagnostic population'}
  $boxes.Add([pscustomobject]@{dataset=$dataset;attack=$attack;label=$label;trap=$trap;clients=$v.Count;minimum=Q $v 0;q25=Q $v .25;median=Q $v .5;q75=Q $v .75;maximum=Q $v 1})
 }}
}}
$clients|Export-Csv (Join-Path $out 'comparison/ordinary_trap_clients.csv') -NoTypeInformation -Encoding utf8
$boxes|Export-Csv (Join-Path $out 'comparison/ordinary_trap_boxes.csv') -NoTypeInformation -Encoding utf8
@{selection='Non-IID, 40%, seed 42, both datasets and all four attacks';window='Initial paired cycle, rounds 11-20';unit='Per-client mean norm within ordinary/challenge condition, then asinh transform';caveat='Different starting states and round positions; observational, not a matched ablation';inputs=$inputs}|ConvertTo-Json -Depth 5|Set-Content (Join-Path $out 'comparison/reviewer_diagnostic_provenance.json') -Encoding utf8
# Pair the same client's two condition summaries for the publication figure.
$paired=foreach($g in $clients|Group-Object dataset,attack,client_id){
 if($g.Count -ne 2){throw 'Missing client response condition'}
 $ordinary=@($g.Group|Where-Object trap -eq 0);$challenge=@($g.Group|Where-Object trap -eq 1)
 if($ordinary.Count -ne 1 -or $challenge.Count -ne 1 -or $ordinary[0].is_free_rider -ne $challenge[0].is_free_rider){throw 'Unmatched client diagnostic'}
 [pscustomobject]@{dataset=$ordinary[0].dataset;attack=$ordinary[0].attack;client_id=$ordinary[0].client_id;is_free_rider=$ordinary[0].is_free_rider;ordinary_norm=$ordinary[0].mean_norm;challenge_norm=$challenge[0].mean_norm;x=$ordinary[0].asinh_mean_norm;y=$challenge[0].asinh_mean_norm}
}
if(@($paired).Count -ne 800){throw 'Incomplete paired client diagnostic'}
$paired|Export-Csv (Join-Path $out 'comparison/ordinary_trap_pairs.csv') -NoTypeInformation -Encoding utf8
# Empirical cumulative distributions: exact ranks, with no bins or smoothing.
$lines=[Collections.Generic.List[string]]::new()
foreach($line in @('\begin{figure*}[tp]\centering\begin{tikzpicture}',
'\begin{groupplot}[group style={group size=4 by 2,horizontal sep=0.7cm,vertical sep=1.1cm},scale only axis,width=0.195\textwidth,height=0.195\textwidth,ymin=0,ymax=103,ytick={0,25,50,75,100},grid=major,grid style={black!7},axis line style={black!45},tick label style={font=\scriptsize},title style={font=\small},label style={font=\scriptsize},scaled ticks=false]')){$lines.Add($line)}
$cdfRows=[Collections.Generic.List[object]]::new()
foreach($dataset in @('mnist','cifar10')){
 $values=@($clients|Where-Object dataset -eq $dataset|ForEach-Object asinh_mean_norm)
 $maximum=($values|Measure-Object -Maximum).Maximum
 $limit=1.08*$maximum;$padding=-.025*$maximum
 foreach($attack in @('FR1','FR2','FR3','FR4')){
  $d=if($dataset -eq 'mnist'){'MNIST'}else{'CIFAR-10'}
  $axis=if($attack -eq 'FR1'){',ylabel={Clients at or below (\%)}'}else{''}
  if($dataset -eq 'cifar10'){$axis+=',xlabel={Response size}'}
  $lines.Add('\nextgroupplot[title={'+$d+' '+$attack+'},xmin='+(F $padding)+',xmax='+(F $limit)+$axis+']')
  foreach($label in @(0,1)){foreach($trap in @(0,1)){
   $data=@($clients|Where-Object {$_.dataset -eq $dataset -and $_.attack -eq $attack -and $_.is_free_rider -eq $label -and $_.trap -eq $trap})
   if($data.Count -ne $(if($label){40}else{60})){throw 'Incorrect distribution population'}
   $series=[Collections.Generic.List[object]]::new()
   $series.Add([pscustomobject]@{x=$padding;percent=0.})
   $seen=0
   foreach($g in $data|Group-Object asinh_mean_norm|Sort-Object {[double]$_.Name}){
    $seen+=$g.Count;$x=[double]$g.Name;$pct=100.*$seen/$data.Count
    $series.Add([pscustomobject]@{x=$x;percent=$pct})
    $cdfRows.Add([pscustomobject]@{dataset=$dataset;attack=$attack;label=$label;trap=$trap;response_size=$x;cumulative_clients=$seen;class_clients=$data.Count;percent=$pct})
   }
   if($seen -ne $data.Count -or $series[$series.Count-1].percent -ne 100){throw 'Incomplete empirical distribution'}
   $series.Add([pscustomobject]@{x=$limit;percent=100.})
   $file="comparison/ordinary_trap_cdf_$($dataset)_$($attack)_$($label)_$trap.csv"
   $series|Export-Csv (Join-Path $out $file) -NoTypeInformation -UseQuotes Never -Encoding utf8
   $color=if($label){'riderorange'}else{'honestblue'}
   $stroke=if($trap){'very thick'}else{'densely dashed,thick'}
   $lines.Add('\addplot[const plot,no marks,'+$color+','+$stroke+'] table[col sep=comma,x=x,y=percent] {generated/'+$file+'};')
  }}
 }
}
$cdfRows|Export-Csv (Join-Path $out 'comparison/ordinary_trap_cdf_values.csv') -NoTypeInformation -Encoding utf8
foreach($line in @('\end{groupplot}\end{tikzpicture}',
'\par\medskip{\scriptsize',
'\tikz[baseline=-0.5ex]\draw[honestblue,densely dashed,thick] (0,0)--(0.45,0);\ Honest, ordinary\quad',
'\tikz[baseline=-0.5ex]\draw[honestblue,very thick] (0,0)--(0.45,0);\ Honest, challenge\quad',
'\tikz[baseline=-0.5ex]\draw[riderorange,densely dashed,thick] (0,0)--(0.45,0);\ Free rider, ordinary\quad',
'\tikz[baseline=-0.5ex]\draw[riderorange,very thick] (0,0)--(0.45,0);\ Free rider, challenge}',
'\caption{Cumulative distributions of ordinary and challenge response sizes in seed-42 non-IID executions with 40\% free riders. Curve height is the percentage of clients in that class at or below a response size. Each client contributes its mean norm from eight ordinary responses or two challenges. Response size is asinh(mean norm), preserving exact zero. Dashed curves denote ordinary models and solid curves challenges.}\label{fig:ordinary-trap-norms}',
'\end{figure*}')){$lines.Add($line)}
[IO.File]::WriteAllLines((Join-Path $out 'ordinary_trap_norms.tex'),$lines,[Text.UTF8Encoding]::new($false))
# A standalone vector preview makes the revised figure easy to inspect/export.
$preview=@('\documentclass[border=6pt]{standalone}',
'\usepackage{amsmath,amssymb,pgfplots,mathptmx}',
'\usepgfplotslibrary{groupplots}',
'\pgfplotsset{compat=1.18}',
'\definecolor{honestblue}{HTML}{2878A5}',
'\definecolor{riderorange}{HTML}{D66B27}',
'\setlength{\textwidth}{18.2cm}',
'\begin{document}\begin{minipage}{18.2cm}\centering')
$preview+=@($lines|ForEach-Object {$_ -replace '^\\begin\{figure\*\}\[tp\]\\centering',''}|Where-Object {$_ -notmatch '^\\caption|^\\end\{figure\*\}'})
$preview+=@('\end{minipage}\end{document}')
[IO.File]::WriteAllLines((Join-Path $PSScriptRoot 'build/figure5_preview.tex'),$preview,[Text.UTF8Encoding]::new($false))
