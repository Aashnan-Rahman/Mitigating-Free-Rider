# SPARC-FL v7.4: reframed manuscript

**SPARC-FL: Statistical Peer Auditing with Repeated Confirmation for Free-Rider
Detection in Federated Learning.** It succeeds BaitFL v7.3.

- [Main paper PDF](paper_v7_4.pdf) and [LaTeX source](paper_v7_4.tex)
- [Self-contained PDF](paper_v7_4_all_in_one.pdf) and [source](paper_v7_4_all_in_one.tex)
- [Supplement](paper_v7_4_supplement.pdf)
- [Response to the reviewer](response_to_reviewer.pdf), covering the v7.1 review

## What changed from v7.3

- New name and title. The contribution is the per-slot peer statistics plus the
  repeated-certificate confirmation rule. Perturbed models are described as an
  optional **challenge dispatch** mode; **ordinary dispatch** sends the global model.
- The passive ablation is now Section V-H, "Ordinary versus Challenge Dispatch". Its
  full-width Table VI adds final accuracy for both modes.
- "Trap" wording is replaced throughout by slot or challenge, including generated
  tables, algorithm text and plot legends.
- Fig. 2 (round schedule) and Fig. 3(a) (audit slots) are redrawn around the audit
  slots, which work in both dispatch modes. A new Fig. 6 shows honest withholding
  under each mode.
- The affiliation sits under the author name instead of in a footnote.
- All in-progress and queue language is removed. Only completed runs are reported:
  96 main, 4 honest-only, 48 lower-prevalence and 16 ordinary-dispatch runs.
  The oracle, 30% ordinary-dispatch, published-attack and held-out runs are not
  included.

## Build

From this directory, run `./build.ps1 -SkipFigures`, then `./export.ps1`. Compile
`paper_v7_4_all_in_one.tex` in `build/isolated/` with
`latexmk -pdf -interaction=nonstopmode -halt-on-error`. Then run
`python validate_revision.py`, which writes `VALIDATION.json`.

`refresh_evidence.py` regenerates `generated/saudi/` from completed results only.
It writes no prose.
