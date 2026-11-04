$ErrorActionPreference='Stop'
$output=Join-Path $PSScriptRoot 'build/diagrams'
New-Item -ItemType Directory -Force -Path $output | Out-Null
Push-Location $PSScriptRoot
try {
    foreach ($name in @('baitfl_methodology','free_rider_attack')) {
        $source=Join-Path $PSScriptRoot "figures/$name.tex"
        $pdf=Join-Path $PSScriptRoot "figures/$name.pdf"
        if ((Test-Path -LiteralPath $pdf) -and (Get-Item -LiteralPath $pdf).LastWriteTimeUtc -ge (Get-Item -LiteralPath $source).LastWriteTimeUtc) {continue}
        & pdflatex -interaction=nonstopmode -halt-on-error "-output-directory=$output" $source *> (Join-Path $output "$name.compile.log")
        if ($LASTEXITCODE -ne 0) {
            Get-Content (Join-Path $output "$name.compile.log") -Tail 25
            throw "Diagram build failed: $name"
        }
        Copy-Item -LiteralPath (Join-Path $output "$name.pdf") -Destination $pdf
    }
} finally {Pop-Location}
