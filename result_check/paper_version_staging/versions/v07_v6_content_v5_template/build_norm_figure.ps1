$ErrorActionPreference = 'Stop'
$repository = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$panels = @(
    @{share=40;round=20;honest=9;riders=40}, @{share=40;round=30;honest=0;riders=0}, @{share=40;round=60;honest=0;riders=40},
    @{share=30;round=20;honest=0;riders=0}, @{share=30;round=40;honest=0;riders=30}, @{share=30;round=80;honest=1;riders=30}
)
$lines = [Collections.Generic.List[string]]::new()
@('\begin{figure*}[tp]\centering', '\begin{tikzpicture}',
'\pgfplotsset{normpanel/.style={width=0.31\textwidth,height=4.15cm,xmin=0,xmax=25,ymin=0,ymax=70,xtick={0,5,10,15,20,25},ytick={0,20,40,60},axis line style={black!40},ymajorgrids=true,grid style={black!10},tick label style={font=\scriptsize},title style={font=\small},label style={font=\scriptsize},xlabel={Update norm (trap A)},scaled ticks=false}}'
) | ForEach-Object { $lines.Add($_) }
foreach ($share in @(40,30)) {
    $decisions = @(Import-Csv (Join-Path $repository "results/v15_4_cifar10_seed42_fr$share/v15_4_cifar10_noniid_FR3_seed42/cycle_decisions.csv"))
    $groupName = if ($share -eq 40) { 'upper' } else { 'lower' }
    if ($share -eq 30) { $lines.Add('\begin{scope}[yshift=-7.25cm]') }
    $lines.Add('\begin{groupplot}[normpanel,group style={group name=' + $groupName + ',group size=3 by 1,horizontal sep=0.45cm}]')
    $column = 0
    foreach ($panel in @($panels | Where-Object share -eq $share)) {
        $column++
        $fresh = @($decisions | Where-Object { [int]$_.round -eq $panel.round -and $_.strong_channels -match 'norm' })
        if (@($fresh | Where-Object is_free_rider -eq '0').Count -ne $panel.honest -or @($fresh | Where-Object is_free_rider -eq '1').Count -ne $panel.riders) { throw 'Figure certificate count mismatch' }
        $ylabel = if ($column -eq 1) { ',ylabel={Client count}' } else { '' }
        $lines.Add('\nextgroupplot[title={' + $share + '\% free riders, round ' + $panel.round + '}' + $ylabel + ']')
        foreach ($label in @(0,1)) {
            $path = "generated/visuals/hist_${share}_$($panel.round)_${label}.dat"
            $values = @(Get-Content (Join-Path $PSScriptRoot $path) | Select-Object -Skip 1 | ForEach-Object { [double](($_ -split '\s+')[1]) })
            $expected = if ($label -eq 0) { 100-$share } else { $share }
            if (($values | Measure-Object -Sum).Sum -ne $expected) { throw 'Histogram population mismatch' }
            $style = if ($label -eq 0) { 'ybar interval,fill=honestblue!25,draw=honestblue,line width=0.6pt' } else { 'ybar interval,fill=none,draw=riderorange,line width=1.25pt' }
            $lines.Add('\addplot[' + $style + '] table[x=x,y=y] {' + $path + '};')
        }
    }
    $lines.Add('\end{groupplot}')
    if ($share -eq 30) { $lines.Add('\end{scope}') }
    $column = 0
    foreach ($panel in @($panels | Where-Object share -eq $share)) {
        $column++
        $lines.Add('\node[font=\scriptsize,align=center] at ([yshift=-1.0cm]' + $groupName + ' c' + $column + 'r1.south) {Fresh paired norm evidence\\' + $panel.honest + ' honest, ' + $panel.riders + ' free riders};')
    }
}
@(
'\node[anchor=west,font=\small] at ([xshift=-3.6cm,yshift=1.0cm]upper c2r1.north) {\tikz\draw[draw=honestblue,fill=honestblue!25] (0,0) rectangle (0.36,0.16);\ Honest clients\qquad\tikz\draw[draw=riderorange,line width=1.25pt] (0,0) rectangle (0.36,0.16);\ Free riders};',
'\node[font=\small\bfseries] at (7.5cm,-2.0cm) {How evidence leads to removal};',
'\node[draw=honestblue!55,fill=honestblue!6,rounded corners=2pt,text width=3.0cm,minimum height=0.85cm,align=center,font=\scriptsize] (first) at (1.5cm,-2.9cm) {First certificate\\on both challenges};',
'\node[draw=black!35,fill=black!3,rounded corners=2pt,text width=3.0cm,minimum height=0.85cm,align=center,font=\scriptsize] (retain) at (5.5cm,-2.9cm) {Retain evidence\\across ambiguous cycles};',
'\node[draw=honestblue!55,fill=honestblue!6,rounded corners=2pt,text width=3.0cm,minimum height=0.85cm,align=center,font=\scriptsize] (fresh) at (9.5cm,-2.9cm) {Fresh certificate\\for the same component};',
'\node[draw=riderorange!70,fill=riderorange!8,rounded corners=2pt,text width=2.3cm,minimum height=0.85cm,align=center,font=\scriptsize] (remove) at (13.2cm,-2.9cm) {Permanent\\removal};',
'\draw[->,thick,black!55] (first) -- (retain);\draw[->,thick,black!55] (retain) -- (fresh);\draw[->,thick,black!55] (fresh) -- (remove);',
'\end{tikzpicture}',
'\caption{Update norm evolution and repeated confirmation in CIFAR-10 non-IID FR3.}\label{fig:norm-hist}',
'\end{figure*}'
) | ForEach-Object { $lines.Add($_) }
[IO.File]::WriteAllLines((Join-Path $PSScriptRoot 'generated/norm_histograms.tex'), $lines, [Text.UTF8Encoding]::new($false))
