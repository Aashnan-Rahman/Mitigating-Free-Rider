param([switch]$SkipFigures)
$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
    New-Item -ItemType Directory -Path build/diagrams -Force|Out-Null
    if(-not $SkipFigures){
        foreach($name in @('free_rider_attack','audit_schedule','client_states','challenge_path','challenge_scores')){
            & pdflatex -interaction=nonstopmode -halt-on-error -output-directory=build/diagrams "figures/$name.tex" *> "build/diagrams/$name.compile.log"
            if($LASTEXITCODE -ne 0){Get-Content "build/diagrams/$name.compile.log" -Tail 20;throw "Diagram failed: $name"}
            Copy-Item -LiteralPath "build/diagrams/$name.pdf" -Destination "figures/$name.pdf"
        }
    }
    foreach($stem in @('paper_v7_2','paper_v7_2_supplement')){
        & latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=build "$stem.tex" *> "build/$stem.compile.log"
        if($LASTEXITCODE -ne 0){Get-Content "build/$stem.compile.log" -Tail 30;throw "Build failed: $stem"}
        Copy-Item -LiteralPath "build/$stem.pdf" -Destination "$stem.pdf"
    }
    'Built v7.2 main paper and separate supplement.'
} finally {Pop-Location}
