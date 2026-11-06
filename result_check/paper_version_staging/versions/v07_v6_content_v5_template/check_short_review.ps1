$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $culture = [Globalization.CultureInfo]::InvariantCulture
    $repository = (Resolve-Path '../../../..').Path
    function Num($Value) { [double]::Parse([string]$Value, $culture) }
    function Require([bool]$Condition, [string]$Message) {
        if (-not $Condition) { throw $Message }
    }
    $output = 'build_short'
    New-Item -ItemType Directory -Path $output -Force | Out-Null
    $provenance = Get-Content -Raw generated/comparison/provenance.json | ConvertFrom-Json
    $trajectories = @(Import-Csv generated/comparison/paired_trajectories.csv)
    $timeRows = foreach ($attack in @('FR1','FR2','FR3','FR4')) {
        $relative = "results/v15_4_mnist_seed42_fr40/v15_4_mnist_noniid_$($attack)_seed42/global_metrics.csv"
        $sourcePath = Join-Path $repository $relative
        $record = @($provenance.inputs | Where-Object path -eq $relative)
        $hash = (Get-FileHash $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
        Require ($record.Count -eq 1 -and $hash -eq $record[0].sha256) "Changed MNIST source: $attack"
        $raw = @(Import-Csv $sourcePath | Sort-Object { [int]$_.round })
        $paired = @($trajectories | Where-Object {
            $_.dataset -eq 'mnist' -and $_.split -eq 'noniid' -and
            $_.share -eq '40' -and $_.attack -eq $attack -and $_.seed -eq '42'
        } | Sort-Object { [int]$_.round })
        Require ($raw.Count -eq 100 -and $paired.Count -eq 100) "Incomplete MNIST trajectory: $attack"
        $elapsed = 0.0
        $firstHit = $null
        for ($index=0; $index -lt 100; $index++) {
            Require ([int]$raw[$index].round -eq $index+1) 'Unordered raw trajectory'
            Require ([math]::Abs((Num $raw[$index].global_accuracy) - (Num $paired[$index].bait_accuracy)) -lt 1e-12) 'Accuracy export mismatch'
            Require ([math]::Abs((Num $raw[$index].round_time_seconds) - (Num $paired[$index].bait_seconds)) -lt 1e-10) 'Timing export mismatch'
            $elapsed += Num $raw[$index].round_time_seconds
            if ($null -eq $firstHit -and (Num $raw[$index].global_accuracy) -ge .98) {
                $firstHit = [pscustomobject]@{attack=$attack;seed=42;target=.98;round=$index+1;seconds=$elapsed;minutes=$elapsed/60;source=$relative;sha256=$hash}
            }
        }
        Require ($null -ne $firstHit) "Target not reached: $attack"
        $firstHit
    }
    $minutes = ($timeRows | Measure-Object minutes -Average).Average
    $savedMean = @(Import-Csv generated/comparison/time_target_means.csv | Where-Object {
        $_.dataset -eq 'mnist' -and $_.split -eq 'noniid' -and $_.share -eq '40' -and $_.method -eq 'bait'
    })
    Require ($savedMean.Count -eq 1 -and [math]::Abs($minutes-(Num $savedMean[0].minutes)) -lt 1e-10) 'Time-to-target mean mismatch'
    Require ([math]::Round($minutes,2) -eq 16.48) 'Unexpected manuscript timing value'
    $timeRows | Export-Csv (Join-Path $output 'review_time_target_check.csv') -NoTypeInformation -Encoding utf8

    $scatterChecks = foreach ($attack in @('FR2','FR3')) {
        $relative = "results/v15_4_cifar10_seed42_fr40/v15_4_cifar10_noniid_$($attack)_seed42/cycle_signals.csv"
        $sourcePath = Join-Path $repository $relative
        $signals = @(Import-Csv $sourcePath | Where-Object round -eq '20')
        Require ($signals.Count -eq 200) 'Expected 100 complete challenge pairs'
        $points = foreach ($group in ($signals | Group-Object client_id)) {
            Require ($group.Count -eq 2 -and @($group.Group.trap_id | Sort-Object -Unique).Count -eq 2) 'Incomplete challenge pair'
            $norm = ($group.Group | ForEach-Object { Num $_.norm_z } | Measure-Object -Average).Average
            $profile = ($group.Group | ForEach-Object { Num $_.profile_z } | Measure-Object -Average).Average
            [pscustomobject]@{label=$group.Group[0].is_free_rider;x=[math]::Asinh($norm);y=[math]::Asinh($profile)}
        }
        foreach ($label in @('0','1')) {
            $plotPath = "generated/visuals/scatter_cifar10_40_noniid_$($attack)_$($label).dat"
            $saved = @(Get-Content $plotPath | Select-Object -Skip 1 | ForEach-Object {
                $coordinates = $_ -split '\s+'
                [pscustomobject]@{x=Num $coordinates[0];y=Num $coordinates[1]}
            } | Sort-Object x,y)
            $expected = @($points | Where-Object label -eq $label | Sort-Object x,y)
            $expectedCount = if ($label -eq '0') {60} else {40}
            Require ($saved.Count -eq $expectedCount -and $expected.Count -eq $expectedCount) 'Incorrect plotted population'
            for ($index=0; $index -lt $expectedCount; $index++) {
                Require ([math]::Abs($saved[$index].x-$expected[$index].x) -lt 1e-10 -and [math]::Abs($saved[$index].y-$expected[$index].y) -lt 1e-10) 'Scatter point mismatch'
                Require ($saved[$index].x -ge -1.2 -and $saved[$index].x -le 2.6 -and $saved[$index].y -ge -1.8 -and $saved[$index].y -le 3.2) 'Scatter axis clips a point'
            }
            [pscustomobject]@{attack=$attack;label=$label;points=$expectedCount;round=20;seed=42;source=$relative;source_sha256=(Get-FileHash $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant();plot=$plotPath;plot_sha256=(Get-FileHash $plotPath -Algorithm SHA256).Hash.ToLowerInvariant()}
        }
    }
    $study = @(Import-Csv generated/multiseed/per_run.csv)
    Require ($study.Count -eq 96 -and @($study.seed | Sort-Object -Unique).Count -eq 3) 'Study replication count mismatch'
    $configurations = @($study | Group-Object dataset,split,share,attack)
    Require ($configurations.Count -eq 32 -and @($configurations | Where-Object { $_.Count -ne 3 -or @($_.Group.seed | Sort-Object -Unique).Count -ne 3 }).Count -eq 0) 'Expected three distinct seeds per configuration'
    $matched = @(Import-Csv generated/comparison/paired_results.csv)
    $mnistPairs = @($matched | Where-Object dataset -eq 'mnist')
    Require ($mnistPairs.Count -eq 16 -and @($matched | Where-Object dataset -eq 'cifar10').Count -eq 47) 'Baseline coverage mismatch'
    Require (@($mnistPairs | Group-Object split,share,attack | Where-Object Count -ne 1).Count -eq 0) 'Expected one matched MNIST seed per setting'
    $fullHash = (Get-FileHash paper_v7.pdf -Algorithm SHA256).Hash
    Require ($fullHash -eq 'B074FED69AC10E886F16AA114DA4DCA54662264BD842E913C75C98350F52933F') 'Full PDF changed'
    @{review_date='2026-11-06';study_runs=96;study_seeds=3;mnist_noniid40_target98_minutes=$minutes;rounding=16.48;time_averaging='One matched seed per attack, then all four attacks equally';scatter_checks=@($scatterChecks);full_pdf_sha256=$fullHash} |
        ConvertTo-Json -Depth 6 | Set-Content (Join-Path $output 'review_evidence_check.json') -Encoding utf8
    Write-Output "Verified raw MNIST target time: $minutes minutes (16.48 rounded)."
    Write-Output 'Verified 200 plotted clients from 400 selected trap responses, three seeds and 96 runs; full PDF unchanged.'
} finally {
    Pop-Location
}
