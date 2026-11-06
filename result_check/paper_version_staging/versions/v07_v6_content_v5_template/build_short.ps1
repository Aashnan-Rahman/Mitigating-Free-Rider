$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=build_short paper_v7_short.tex
    if ($LASTEXITCODE -ne 0) { throw 'Short-paper compilation failed.' }
    Copy-Item -LiteralPath 'build_short/paper_v7_short.pdf' -Destination 'paper_v7_short.pdf'
} finally {
    Pop-Location
}
