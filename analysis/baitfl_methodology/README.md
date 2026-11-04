# BaitFL methodology diagram

The diagram describes the v15.4 workflow without round numbers. Clear is a
cycle outcome, not proof of honest training.
Statistical confirmation retains component-specific evidence across ambiguous
cycles; exact send-back has its separate consecutive paired confirmation rule.
Sparse audits can initiate review but cannot authorize removal. Quarantine and
review are bounded, and eligible ordinary responses continue to aggregate.

The editable source is `baitfl_methodology.tex`. The PDF is vector output;
the PNG is a preview. The internal title and subtitle are omitted for insertion
into the manuscript. The paper keeps a self-contained copy under `figures/`.
Phase I–IV labels now match Section IV's four algorithms. The feedback arrow
describes repeated paired coverage while review or probation is pending.
The figure has the same thin outer border as the attack illustration. Weak
candidates receive paired follow-up when enrolled in review; unconfirmed review
expires. The frozen engine's cooldown-only clock edge case is documented in the
manuscript and its `METHODOLOGY_REVIEW.md` audit, not presented as a guaranteed
continuous-auditing property of this conceptual diagram.

From this directory, build with:

```powershell
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=build baitfl_methodology.tex
Copy-Item build/baitfl_methodology.pdf baitfl_methodology.pdf
pdftoppm -png -singlefile -scale-to 2400 baitfl_methodology.pdf baitfl_methodology
latex -interaction=nonstopmode -halt-on-error -output-directory=build baitfl_methodology.tex
dvisvgm --no-fonts --output=baitfl_methodology.svg build/baitfl_methodology.dvi
```
