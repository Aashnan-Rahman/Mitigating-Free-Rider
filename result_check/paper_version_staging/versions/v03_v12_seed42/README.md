# Paper v3 — SWT-CP v12

Main file: `paper_v3.tex`. This preserves the IEEE conference format and section order of `v02_introduction_draft/masters_paper.tex`. Paper v2 remains unchanged.

Compile with `latexmk -pdf paper_v3.tex`, or upload this directory to Overleaf and select `paper_v3.tex` as the main document. The figures are native PGFPlots and use the bundled CSV files. Keep the data directory beside the TeX file.

Changes: v12 history sketches, cohort confirmation, reference-state transitions, all 16 matched-seed 40% runs, per-round accuracy and removal figures, explicit honest-client false removal, residual candidate states, and revised limitations. Old best-of-seed v8/v9 results and unfinished 30% results are excluded.

`data/summary.csv` contains per-run analytics; `provenance.json` maps figures to original runs. Run `python analyze_v12_fr40_results.py` then `python build_paper_v3.py` from the repository root to regenerate. The bibliography is inherited from v2; no new external references were added or independently re-reviewed.
