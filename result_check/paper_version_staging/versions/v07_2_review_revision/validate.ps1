$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
    function Require([bool]$condition,[string]$message){if(-not $condition){throw $message}}
    $root=(Resolve-Path '../../../..').Path
    $base=Get-Content VERSION_PROVENANCE.json -Raw|ConvertFrom-Json
    foreach($file in $base.files){
        $path=Join-Path (Join-Path '..' $base.base) $file.path
        Require ((Get-FileHash $path).Hash.ToLowerInvariant() -eq $file.sha256) "v7.1 changed: $($file.path)"
    }
    $registration=Get-Content (Join-Path $root 'configs/review2_registration.json') -Raw|ConvertFrom-Json
    foreach($field in @('source_sha256','plan_sha256')){
        foreach($entry in $registration.$field.psobject.Properties){
            Require ((Get-FileHash (Join-Path $root $entry.Name)).Hash.ToLowerInvariant() -eq $entry.Value) "Live registered file changed: $($entry.Name)"
        }
    }
    $summary=Get-Content generated/revision/summary.json -Raw|ConvertFrom-Json
    Require ($summary.primary_runs -eq 96 -and $summary.honest_only_completed -eq 4 -and $summary.honest_only_removals -eq 0) 'Unexpected evidence inventory'
    Require ($summary.norm_matching_cases -eq 72) 'Incomplete norm-matching diagnostic'
    $cases=@(Import-Csv generated/revision/norm_matching_cases.csv)
    Require ($cases.Count -eq 432) 'Expected 72 cases x two views x three channels'
    $low=@(Import-Csv generated/revision/completed_review_runs.csv|Where-Object {$_.split -eq 'noniid' -and $_.share -in @('5','10','20')})
    Require ($low.Count -eq 24) 'Incomplete displayed non-IID grid'
    $baseline=Get-Content generated/comparison/summary.json -Raw|ConvertFrom-Json
    Require ($baseline.matched_cases -eq 81) 'Baseline snapshot changed; update the manuscript deliberately'
    $source=Get-Content paper_v7_2.tex -Raw
    foreach($match in [regex]::Matches($source,'\\label\{(eq:[^}]+)\}')){
        $label=$match.Groups[1].Value
        Require ([regex]::IsMatch($source,'\\(?:eqref|ref)\{'+[regex]::Escape($label)+'\}')) "Unreferenced equation: $label"
    }
    Require ($source -notmatch '\\color\{black\}|zhao2019veriml|g>0|q_\{\\rm confirm\}|P_\{\\rm ref\}') 'Requested source cleanup incomplete'
    $export=Get-Content paper_v7_2_all_in_one.tex -Raw
    Require ($export.TrimStart().StartsWith('\documentclass[journal]{IEEEtran}')) 'Review header remains'
    Require ($export -notmatch 'BEGIN FIGURE REVIEW GUIDE|END REVIEW HEADER|Original manuscript SHA256|Code version:|\\(?:input|include)\s*\{|\\includegraphics|\\bibliography\{refs\}') 'Standalone export retains a project dependency or review metadata'
    $abstract=[regex]::Match($export,'(?s)\\begin\{abstract\}(.*?)\\end\{abstract\}').Groups[1].Value
    $abstract=[regex]::Replace($abstract,'\\[A-Za-z]+','')
    $abstractWords=[regex]::Matches($abstract,'\b[A-Za-z0-9]+(?:[-][A-Za-z0-9]+)*\b').Count
    Require ($abstractWords -ge 150 -and $abstractWords -le 250) "Abstract length outside journal bounds: $abstractWords"
    $pages=@{}; $figures=@{}
    foreach($stem in @('paper_v7_2','paper_v7_2_supplement','paper_v7_2_all_in_one')){
        $build=if($stem -eq 'paper_v7_2_all_in_one'){'build/isolated'}else{'build'}
        $log=Get-Content "$build/$stem.log" -Raw
        Require ($log -notmatch 'Overfull|Float too large|undefined references|Citation .* undefined|multiply defined|^!') "Build issue: $stem"
        $info=@(& pdfinfo "$stem.pdf")
        Require ($LASTEXITCODE -eq 0) "Invalid PDF: $stem"
        $pageLine=$info|Where-Object {$_ -match '^Pages:'}
        $pages[$stem]=[int]($pageLine -replace '^Pages:\s*','')
        if($stem -ne 'paper_v7_2_supplement'){
            $aux=Get-Content "$build/$stem.aux" -Raw
            Require ([regex]::Matches($aux,'\\bibcite\{').Count -eq 31) "Reference count changed: $stem"
        }
    }
    Require ($pages.paper_v7_2 -eq $pages.paper_v7_2_all_in_one) 'Modular/standalone pagination differs'
    foreach($name in @('free_rider_attack','audit_schedule','client_states','challenge_path','challenge_scores')){
        $images=@(& pdfimages -list "figures/$name.pdf")
        Require ($LASTEXITCODE -eq 0 -and $images.Count -le 2) "Raster image found in $name"
        $fonts=@(& pdffonts "figures/$name.pdf")
        Require ($LASTEXITCODE -eq 0 -and ($fonts -join "`n") -notmatch 'Type 3') "Unembedded raster font in $name"
    }
    $class=(& kpsewhich IEEEtran.cls).Trim()
    $validation=[ordered]@{version='7.2';date='2026-11-11';pages=$pages;references=31;abstract_words=$abstractWords;
        ieee_class=$class;ieee_class_sha256=(Get-FileHash $class).Hash.ToLowerInvariant();template='IEEEtran journal, local TeX Live';
        base_files_preserved=$base.files.Count;registered_sources_preserved=@($registration.source_sha256.psobject.Properties).Count;
        primary_runs=96;completed_prospective_runs=$summary.completed_review_runs;matched_baselines=$baseline.matched_cases;
        norm_matching_cases=72;standalone_pdf_sha256=(Get-FileHash paper_v7_2_all_in_one.pdf).Hash.ToLowerInvariant();
        scope='Recorded trial outcomes plus a one-cycle oracle feature diagnostic; pending experiments are not evidence'}
    $validation|ConvertTo-Json -Depth 7|Set-Content build/validation.json -Encoding utf8
    $validation|ConvertTo-Json -Depth 7|Set-Content VALIDATION.json -Encoding utf8
    Write-Output "Validated v7.2: $($pages.paper_v7_2_all_in_one) main pages, $($pages.paper_v7_2_supplement) supplement pages, 31 references, $abstractWords abstract words."
} finally {Pop-Location}
