# Export the current full manuscript without external project-file dependencies.
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($PSScriptRoot)
$utf8 = New-Object System.Text.UTF8Encoding($false)
$sources = @{}
$dataRows = @{}
$numbers = @{}
$numberFiles = @(
    'generated/numbers.tex', 'generated/multiseed/summary.tex',
    'generated/comparison/instrumented_mnist_numbers.tex',
    'generated/comparison/instrumented_cifar10_numbers.tex',
    'generated/comparison/baseline_numbers.tex', 'generated/review2/numbers.tex'
)

function Read-Source([string]$relative) {
    $absolute = [IO.Path]::GetFullPath((Join-Path $root $relative))
    if (-not $absolute.StartsWith($root + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase)) { throw "Outside export root: $relative" }
    $sources[$relative] = (Get-FileHash -LiteralPath $absolute -Algorithm SHA256).Hash
    return [IO.File]::ReadAllText($absolute).Replace("`r`n", "`n")
}

function Strip-Comments([string]$content) {
    $lines = foreach ($line in ($content -split "`n")) {
        $cut = -1
        for ($i = 0; $i -lt $line.Length; $i++) {
            if ($line[$i] -ne '%') { continue }
            $slashes = 0
            for ($j = $i - 1; $j -ge 0 -and $line[$j] -eq '\'; $j--) { $slashes++ }
            if ($slashes % 2 -eq 0) { $cut = $i; break }
        }
        if ($cut -lt 0) { $line; continue }
        $prefix = $line.Substring(0, $cut)
        if ($prefix.Trim().Length -gt 0) { $prefix + '%' }
    }
    return $lines -join "`n"
}

foreach ($file in $numberFiles) {
    $text = Strip-Comments (Read-Source $file)
    foreach ($match in [regex]::Matches($text, '\\newcommand\{\\(?<name>[A-Za-z]+)\}\{(?<value>[^{}\r\n]*)\}')) {
        $numbers[$match.Groups['name'].Value] = $match.Groups['value'].Value
    }
}

function Expand-Inputs([string]$content) {
    return [regex]::Replace($content, '\\(?:input|include)\s*\{([^{}]+)\}', [Text.RegularExpressions.MatchEvaluator]{
        param($match)
        $relative = $match.Groups[1].Value
        if ($numberFiles -contains $relative) { return '' }
        $expanded = Expand-Inputs (Strip-Comments (Read-Source $relative))
        return "`n% BEGIN SOURCE: $relative`n$expanded`n% END SOURCE: $relative`n"
    })
}

function Expand-PlotData([string]$content) {
    $pattern = '(?s)\btable\s*\[(?<options>[^\]]*)\]\s*\{(?<path>(?:generated|figures)/[^{}]+\.(?:csv|dat))\}'
    return [regex]::Replace($content, $pattern, [Text.RegularExpressions.MatchEvaluator]{
        param($match)
        $relative = $match.Groups['path'].Value
        $lines = @((Read-Source $relative) -split "`n" | Where-Object { $_.Trim().Length -gt 0 })
        $dataRows[$relative] = $lines.Count - 1
        $table = ($lines | ForEach-Object { $_.TrimEnd() + ' \\' }) -join "`n"
        $options = $match.Groups['options'].Value
        return "table[$options,row sep=\\] {% PLOT DATA: $relative ($($lines.Count - 1) data rows)`n$table`n}"
    })
}

$originalTexHash = (Get-FileHash -LiteralPath (Join-Path $root 'paper_v7_3.tex')).Hash
$originalPdfHash = (Get-FileHash -LiteralPath (Join-Path $root 'paper_v7_3.pdf')).Hash
$content = Expand-Inputs (Strip-Comments (Read-Source 'paper_v7_3.tex'))

# Replace numeric macros with their values. Do not export unused historical macros.
foreach ($name in @($numbers.Keys | Sort-Object Length -Descending)) {
    $pattern = '\\' + [regex]::Escape($name) + '(?![A-Za-z])(?:\{\})?'
    $literal = $numbers[$name]
    $content = [regex]::Replace($content, $pattern, [Text.RegularExpressions.MatchEvaluator]{ param($match) $literal })
}

# Embed the actual diagram code, keeping its styles local to that diagram.
$graphicsPattern = '\\includegraphics\[(?<options>[^\]]+)\]\{(?<path>figures/[^{}]+)\.pdf\}'
$content = [regex]::Replace($content, $graphicsPattern, [Text.RegularExpressions.MatchEvaluator]{
    param($match)
    $relative = $match.Groups['path'].Value + '.tex'
    $diagram = Expand-Inputs (Strip-Comments (Read-Source $relative))
    $diagram = [regex]::Replace($diagram, '(?m)^\\documentclass(?:\[[^\]]*\])?\{[^}]+\}\s*', '')
    $diagram = [regex]::Replace($diagram, '(?m)^\\usepackage(?:\[[^\]]*\])?\{[^}]+\}\s*', '')
    $diagram = [regex]::Replace($diagram, '\\usetikzlibrary\{[^}]+\}', '')
    $diagram = $diagram.Replace('\begin{document}', '').Replace('\end{document}', '')
    $options = $match.Groups['options'].Value
    $width = [regex]::Match($options, '(?:^|,)width=([^,]+)').Groups[1].Value
    if (-not $width) { throw "No graphic width in $relative" }
    $adjust = "max width=$width"
    $height = [regex]::Match($options, '(?:^|,)height=([^,]+)').Groups[1].Value
    if ($height) { $adjust += ",max totalheight=$height" }
    return "`n% BEGIN SOURCE: $relative (embedded vector drawing)`n\adjustbox{$adjust}{\begingroup`n$diagram`n\endgroup}`n% END SOURCE: $relative`n"
})
$content = Expand-PlotData $content
$content = $content.Replace('\usepackage{cite}', @'
\usepackage{cite}
\usepackage{tikz,adjustbox}
\usetikzlibrary{arrows.meta,positioning,calc,shapes.geometric}
'@)
$content = [regex]::Replace($content, '\\bibliographystyle\{[^}]+\}', '')
$bibliography = Strip-Comments (Read-Source 'build/paper_v7_3.bbl')
$content = [regex]::Replace($content, '\\bibliography\{refs\}', [Text.RegularExpressions.MatchEvaluator]{
    param($match) "`n% BEGIN SOURCE: build/paper_v7_3.bbl`n$bibliography`n% END SOURCE: build/paper_v7_3.bbl`n"
})

if ($content -match '\\(?:input|include|includegraphics|bibliography|bibliographystyle)\s*(?:\[|\{)') {
    throw 'Unexpanded project dependency remains.'
}
if ($content -match '(?s)\btable\s*\[[^\]]*\]\s*\{\s*(?:generated|figures)/') {
    throw 'External plot data remains.'
}

$output = Join-Path $root 'paper_v7_3_all_in_one.tex'
[IO.File]::WriteAllText($output, $content, $utf8)

foreach ($item in @(@{Path='paper_v7_3.tex';Hash=$originalTexHash}, @{Path='paper_v7_3.pdf';Hash=$originalPdfHash})) {
    if ((Get-FileHash -LiteralPath (Join-Path $root $item.Path)).Hash -ne $item.Hash) {
        throw "Original changed during export: $($item.Path)"
    }
}
$manifest = [ordered]@{
    export = 'paper_v7_3_all_in_one.tex'
    sha256 = (Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash
    original_tex_sha256 = $originalTexHash
    original_pdf_sha256 = $originalPdfHash
    bibliography_entries = [regex]::Matches($bibliography, '\\bibitem(?:\[[^\]]*\])?\{').Count
    project_files_embedded = $sources.Count
    plot_files_embedded = $dataRows.Count
    plot_data_rows = ($dataRows.Values | Measure-Object -Sum).Sum
    plot_rows_by_source = $dataRows
    source_sha256 = $sources
}
[IO.File]::WriteAllText((Join-Path $root 'export_manifest.json'), ($manifest | ConvertTo-Json -Depth 5), $utf8)
[pscustomobject]$manifest | Select-Object export,bibliography_entries,project_files_embedded,plot_files_embedded,plot_data_rows | Format-List
