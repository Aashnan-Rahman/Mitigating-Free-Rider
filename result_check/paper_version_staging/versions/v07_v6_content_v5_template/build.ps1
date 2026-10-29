$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=build paper_v7.tex
    if ($LASTEXITCODE -ne 0) { throw 'V7 compilation failed.' }
    Copy-Item -LiteralPath 'build/paper_v7.pdf' -Destination 'paper_v7.pdf'
    # Keep bibliography and resolved citation state available for direct editor builds.
    Copy-Item -LiteralPath 'build/paper_v7.bbl' -Destination 'paper_v7.bbl'
    Copy-Item -LiteralPath 'build/paper_v7.aux' -Destination 'paper_v7.aux'
    Copy-Item -LiteralPath 'build/paper_v7.log' -Destination 'paper_v7.log'
} finally {
    Pop-Location
}
