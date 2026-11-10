$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $diagramOutput = Join-Path $PSScriptRoot 'build/diagrams'
    New-Item -ItemType Directory -Force -Path $diagramOutput | Out-Null
    foreach ($name in @('free_rider_attack','audit_schedule','client_states','challenge_path','challenge_scores')) {
        & pdflatex -interaction=nonstopmode -halt-on-error "-output-directory=$diagramOutput" "figures/$name.tex" *> (Join-Path $diagramOutput "$name.compile.log")
        if ($LASTEXITCODE -ne 0) {
            Get-Content (Join-Path $diagramOutput "$name.compile.log") -Tail 25
            throw "Diagram build failed: $name"
        }
        Copy-Item -LiteralPath (Join-Path $diagramOutput "$name.pdf") -Destination "figures/$name.pdf"
    }
    & latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=build paper_v7_1.tex
    if ($LASTEXITCODE -ne 0) { throw 'V7.1 compilation failed.' }
    Copy-Item -LiteralPath build/paper_v7_1.pdf -Destination paper_v7_1.pdf
    $base = Get-Content -Raw BASE_VERSION.json | ConvertFrom-Json
    foreach ($file in $base.original_files) {
        $originalPath = Join-Path (Join-Path '../' $base.base_version) $file.path
        if ((Get-FileHash -LiteralPath $originalPath -Algorithm SHA256).Hash -ne $file.sha256) {
            throw "Original version changed: $($file.path)"
        }
    }
} finally {
    Pop-Location
}
