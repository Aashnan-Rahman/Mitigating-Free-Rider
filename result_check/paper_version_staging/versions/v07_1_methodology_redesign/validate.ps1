$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $base = Get-Content -Raw BASE_VERSION.json | ConvertFrom-Json
    $baseDirectory = Join-Path (Split-Path $PSScriptRoot -Parent) $base.base_version
    foreach ($file in $base.original_files) {
        $path = Join-Path $baseDirectory $file.path
        if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $file.sha256) {
            throw "Original file changed: $($file.path)"
        }
    }
    $exports = @(Get-ChildItem -LiteralPath generated -File -Recurse)
    foreach ($file in $exports) {
        $relative = [IO.Path]::GetRelativePath($PSScriptRoot,$file.FullName)
        if ((Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash -ne
            (Get-FileHash -LiteralPath (Join-Path $baseDirectory $relative) -Algorithm SHA256).Hash) {
            throw "Reporting export changed: $relative"
        }
    }
    if ((Get-FileHash refs.bib -Algorithm SHA256).Hash -ne
        (Get-FileHash (Join-Path $baseDirectory 'refs.bib') -Algorithm SHA256).Hash) {
        throw 'Bibliography changed'
    }
    $accuracySource = (Get-Content -Raw generated/accuracy_comparison.tex).Replace("`r`n","`n").TrimEnd()
    $accuracyLayout = (Get-Content -Raw figures/accuracy_comparison_layout.tex).Replace("`r`n","`n").TrimEnd()
    if ($accuracyLayout -ne $accuracySource.Replace('\begin{figure*}[!t]','\begin{figure*}[t]')) {
        throw 'Accuracy layout variant changed more than float placement'
    }
    $log = Get-Content -Raw build/paper_v7_1.log
    if ($log -match 'Overfull|undefined references|Citation .* undefined|Float too large') {
        throw 'Manuscript has a reference or overflow problem'
    }
    & pdftotext -layout paper_v7_1.pdf build/paper_v7_1.txt
    if ($LASTEXITCODE -ne 0) { throw 'PDF text extraction failed' }
    $pages = (Get-Content -Raw build/paper_v7_1.txt).Split([char]12).Count - 1
    $aux = Get-Content -Raw build/paper_v7_1.aux
    $references = [regex]::Matches($aux,'\\bibcite\{').Count
    if ($references -ne 31) { throw 'Expected 31 retained references' }
    $source = Get-Content -Raw paper_v7_1.tex
    if ($source -match 'fig:baitfl-methodology|figures/baitfl_methodology.pdf') {
        throw 'Obsolete methodology reference remains'
    }
    $figures = foreach ($name in @('free_rider_attack','audit_schedule','challenge_path','challenge_scores','client_states')) {
        $imageList = @(& pdfimages -list "figures/$name.pdf")
        if ($LASTEXITCODE -ne 0 -or $imageList.Count -gt 2) {
            throw "Unexpected raster content in vector diagram: $name"
        }
        $fonts = @(& pdffonts "figures/$name.pdf")
        if ($LASTEXITCODE -ne 0 -or ($fonts -join "`n") -match 'Type 3') {
            throw "Unexpected font type in diagram: $name"
        }
        $diagramLog = Get-Content -Raw "build/diagrams/$name.log"
        if ($diagramLog -match 'Overfull') { throw "Diagram text overflow: $name" }
        [pscustomobject]@{name=$name;sha256=(Get-FileHash "figures/$name.pdf" -Algorithm SHA256).Hash;raster_images=0}
    }
    @{version='7.1';date='2026-11-11';pages=$pages;references=$references;unchanged_reporting_exports=$exports.Count;original_files_unchanged=$base.original_files.Count;figures=@($figures);pdf_sha256=(Get-FileHash paper_v7_1.pdf -Algorithm SHA256).Hash} |
        ConvertTo-Json -Depth 5 | Set-Content build/validation.json -Encoding utf8
    Write-Output "Validated v7.1: $pages pages, $references references, $($exports.Count) unchanged reporting exports."
    Write-Output 'Five vector panels in four figures; original full paper, short paper and former figure preserved.'
} finally { Pop-Location }
