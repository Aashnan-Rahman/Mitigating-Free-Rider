# BaitFL v7.3 — Azom review revision

- [Main paper PDF, with both 4×4 geometry grids in Appendix A](paper_v7_3.pdf)
- [Editable LaTeX source](paper_v7_3.tex)
- [Self-contained PDF](paper_v7_3_all_in_one.pdf) and [source](paper_v7_3_all_in_one.tex)
- [Supplement](paper_v7_3_supplement.pdf): detailed tables and expanded procedures
- **[Review response, assessment and experiment inventory](REVIEW_RESPONSE.md)**
- [Original reviewer document](Peer%20review_Azom.docx)

This revision preserves v7.1 and v7.2. It adds a completed-only snapshot of 35
low-prevalence runs plus four honest-only runs. Existing 96-run primary evidence,
81 matched baseline pairs and the feature-level norm-matching diagnostic retain
their prior snapshots. Queued work is not presented as completed evidence.

From this directory, run `./build.ps1` (`-SkipFigures` if diagrams are unchanged),
then `./export.ps1`. Compile `paper_v7_3_all_in_one.tex` independently with
`latexmk -pdf -interaction=nonstopmode -halt-on-error` in `build/isolated/`.
The standard IEEEtran journal template and TeX packages are required.
Run `python validate_revision.py` with the repository's Python environment after
building. It checks the PDFs, references, external link targets, completed-run
inventory and frozen experiment source hashes. The resulting `VALIDATION.json`
records 19 pages in each main-paper build and four pages in the supplement.

`prepare_revision.py` records the one-time editorial construction from v7.2.
It overwrites the derived manuscript when run, so do not rerun it after manual
editing without reconciling the changes. Normal builds do not refresh evidence
or overwrite writing. `generated/saudi/snapshot.json` records the evidence cutoff.

The review still identifies experimental gaps. This revision does not establish
that traps beat passive statistics or that BaitFL beats a successful baseline.
No live experiment code or registered plan was modified.
