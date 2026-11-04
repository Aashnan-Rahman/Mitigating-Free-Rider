$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$out=Join-Path $PSScriptRoot 'generated/review2'
New-Item -ItemType Directory -Path $out -Force | Out-Null
function Require([bool]$Condition,[string]$Message){if(-not $Condition){throw $Message}}
$runs=@(Import-Csv (Join-Path $PSScriptRoot 'generated/multiseed/per_run.csv'))
Require ($runs.Count -eq 96) 'Expected the complete detection grid'
$audits=[Collections.Generic.List[object]]::new();$inputs=[Collections.Generic.List[object]]::new()
$sourceHashes=Get-Content (Join-Path $PSScriptRoot 'generated/multiseed/provenance.json') -Raw | ConvertFrom-Json
foreach($property in $sourceHashes.implementation_sha256.psobject.Properties){
    $text=[IO.File]::ReadAllText((Join-Path $root $property.Name)).Replace("`r`n","`n")
    $hash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($text))).ToLowerInvariant()
    Require ($hash -eq $property.Value) "Study source differs: $($property.Name)"
}
foreach($run in $runs){
    $directory=Join-Path $root $run.source
    $config=Get-Content (Join-Path $directory 'run_config.json') -Raw | ConvertFrom-Json
    $metrics=@(Import-Csv (Join-Path $directory 'global_metrics.csv'))
    $decisions=@(Import-Csv (Join-Path $directory 'cycle_decisions.csv'))
    $events=@(Import-Csv (Join-Path $directory 'candidate_events.csv'))
    $policies=@(Import-Csv (Join-Path $directory 'cycle_policy.csv'))
    Require ($metrics.Count -eq 100) 'Incomplete audit trace'
    $cycles=@{};foreach($group in $decisions|Group-Object round){$cycles[[int]$group.Name]=@($group.Group)}
    $eventRounds=@{};foreach($group in $events|Group-Object round){$eventRounds[[int]$group.Name]=@($group.Group)}
    $auditPolicies=@{}
    foreach($row in $policies){
        if($row.policy -notmatch '"mode"'){continue}
        $policy=$row.policy|ConvertFrom-Json
        if($policy.mode -eq 'single_audit'){$auditPolicies[[int]$row.round]=$policy}
    }
    # The frozen state machine changes cooldown only at a fresh S result,
    # an unconfirmed release/follow-up expiry, or an audit decrement.
    $cooldown=@{};$active=[Collections.Generic.HashSet[int]]::new()
    for($client=0;$client -lt $config.num_clients;$client++){$cooldown[$client]=0;[void]$active.Add($client)}
    foreach($round in $metrics){
        $t=[int]$round.round
        if($cycles.ContainsKey($t)){
            $rows=$cycles[$t]
            Require ($rows.Count -eq $active.Count) 'Incomplete active-client cycle'
            foreach($decision in $rows){
                $client=[int]$decision.client_id
                Require ($active.Contains($client)) 'Decision for inactive client'
                if($decision.state -eq 'S'){$cooldown[$client]=0}
                if([int]$decision.removed -eq 1){[void]$active.Remove($client)}
            }
            foreach($event in @($eventRounds[$t])){
                if($event.event -in @('release_unconfirmed','end_unconfirmed_followup')){$cooldown[[int]$event.client_id]=[int]$config.v15_candidate_cooldown_audits}
            }
        }
        if($round.phase -eq 'single_audit'){
            Require ($auditPolicies.ContainsKey($t)) 'Audit has no policy record'
            $findings=[int]$auditPolicies[$t].escalations
            $cooling=@($active|Where-Object {$cooldown[$_] -gt 0}).Count
            Require ($findings -ge 0 -and $findings -le $active.Count) 'Invalid raw finding count'
            $eligibleLowerBound=[math]::Max(0,$findings-$cooling)
            # No finding identities are needed: if findings outnumber cooling
            # clients, at least one finding necessarily starts review.
            $proven=($findings -eq 0 -or $eligibleLowerBound -gt 0)
            $audits.Add([pscustomobject]@{source=$run.source;round=$t;active_clients=$active.Count;raw_findings=$findings;cooldown_clients_before=$cooling;eligible_findings_lower_bound=$eligibleLowerBound;guards_equivalent=$proven;proof=$(if($findings -eq 0){'empty finding set'}elseif($eligibleLowerBound -gt 0){'findings exceed cooling clients'}else{'membership check required'})})
            foreach($client in @($cooldown.Keys)){$cooldown[$client]=[math]::Max(0,$cooldown[$client]-1)}
            if($findings -gt 0 -and $proven -and $t -lt 100){Require ($metrics[$t].phase -in @('double_probe','confirmation')) 'Recorded follow-up does not agree with eligibility bound'}
        }else{Require (-not $auditPolicies.ContainsKey($t)) 'Audit policy attached to an ordinary round'}
        Require ($active.Count -eq [int]$round.num_active_clients) 'Active population differs from logged removals'
    }
    foreach($name in @('run_config.json','global_metrics.csv','cycle_decisions.csv','candidate_events.csv','cycle_policy.csv')){
        $inputs.Add([pscustomobject]@{path=$run.source+'/'+$name;sha256=(Get-FileHash (Join-Path $directory $name) -Algorithm SHA256).Hash.ToLowerInvariant()})
    }
}
$audits|Export-Csv (Join-Path $out 'audit_clock_checks.csv') -NoTypeInformation -Encoding utf8
Require (@($audits|Where-Object {-not $_.guards_equivalent}).Count -eq 0) 'Clock guards disagree on a recorded audit'
$flagDiagnostics=[Collections.Generic.List[object]]::new()
foreach($dataset in @('mnist','cifar10')){
    $relative="evidence/timing_${dataset}_20261103/std/segment_timings.csv"
    $path=Join-Path $PSScriptRoot $relative;$rows=@(Import-Csv $path)
    Require ($rows.Count -eq 100) 'Incomplete STD flag trace'
    foreach($row in $rows){
        Require ([int]$row.active_clients -eq 100 -and [int]$row.honest_training_clients -eq 60 -and [int]$row.permanent_removals -eq 0) 'Unexpected STD observational workflow'
        Require ([int]$row.flagged_free_riders+[int]$row.missed_free_riders -eq 40) 'Invalid STD truth accounting'
    }
    $tp=($rows|Measure-Object flagged_free_riders -Sum).Sum;$fp=($rows|Measure-Object flagged_honest -Sum).Sum;$fn=($rows|Measure-Object missed_free_riders -Sum).Sum
    $flagDiagnostics.Add([pscustomobject]@{dataset=$dataset;rounds=100;attacker_responses=4000;honest_responses=6000;tp=$tp;fp=$fp;fn=$fn;precision=$tp/($tp+$fp);recall=$tp/($tp+$fn);endpoint='per-round observational flags';detector_epochs=5;source=$relative})
    $inputs.Add([pscustomobject]@{path=$relative;sha256=(Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant()})
}
$flagDiagnostics|Export-Csv (Join-Path $out 'std_flag_diagnostics.csv') -NoTypeInformation -Encoding utf8
$summary=[ordered]@{runs=$runs.Count;honest_removals=($runs|Measure-Object fp -Sum).Sum;affected_runs=@($runs|Where-Object {[int]$_.fp -gt 0}).Count;honest_client_cases=($runs|Measure-Object honest -Sum).Sum;audits=$audits.Count;empty_audits=@($audits|Where-Object raw_findings -eq 0).Count;nonempty_audits=@($audits|Where-Object raw_findings -gt 0).Count;unproven_audits=0;correction='Restart quiet clock when no finding survives pre-decrement cooldown filtering';scope='Agreement on all recorded audits only; no new training, screening or attack responses generated';std_flags=$flagDiagnostics}
$summary|ConvertTo-Json -Depth 6|Set-Content (Join-Path $out 'summary.json') -Encoding utf8
@{inputs=$inputs;implementation_sha256=$sourceHashes.implementation_sha256;proof='For empty raw findings both guards restart the clock. For each nonempty audit the raw count exceeds the reconstructed active cooldown count, so both guards open review and unset the clock.'}|ConvertTo-Json -Depth 8|Set-Content (Join-Path $out 'provenance.json') -Encoding utf8
$macros=[Collections.Generic.List[string]]::new()
foreach($pair in @(@('ReviewRunCount',$summary.runs),@('ReviewAffectedRuns',$summary.affected_runs),@('ReviewHonestCases',$summary.honest_client_cases),@('ReviewAuditCount',$summary.audits),@('ReviewEmptyAudits',$summary.empty_audits),@('ReviewNonemptyAudits',$summary.nonempty_audits))){$macros.Add('\newcommand{\'+$pair[0]+'}{'+$pair[1]+'}')}
[IO.File]::WriteAllLines((Join-Path $out 'numbers.tex'),[string[]]$macros,[Text.UTF8Encoding]::new($false))
$summary|ConvertTo-Json -Depth 5
