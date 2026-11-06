# BaitFL short paper

Created 5 November 2026 from the current full v7 manuscript and its v15.4 study.
Revised 6 November 2026 after citation, reporting and figure review.

- PDF: `paper_v7_short.pdf` (six pages including references).
- Source: `paper_v7_short.tex`.
- Build: run `./build_short.ps1` in this directory with TeX Live available.

The short paper retains the four contributions, threat model, four fabrication
strategies, central scoring and certification equations, one overall algorithm,
the complete grouped accuracy/detection table, honest-client costs, no-defense
comparison, instrumented timing, complexity and limitations. A compact workflow
and a two-panel challenge-score figure replace the extensive diagnostic panels.
Seventeen relevant references
are selected automatically from the corrected shared `refs.bib`.

`generated/performance.tex` is shared with the full manuscript so its published
measurements are reused without retyping. The compact timing table uses the
existing instrumented measurements. `generated/short_score_figure.tex` reads four
existing score files in `generated/visuals/`. Builds write to `build_short/` and copy
only the short PDF to this directory. The full `paper_v7.tex` and `paper_v7.pdf`
are preserved. No training, experiment settings or study code are changed.

The short algorithm retains the implemented raw-finding audit-clock guard.
Its cooldown edge case and the limits of recorded trace agreement remain
explicit. Timing is a comparison of particular native workflows, not a matched
detection benchmark or an isolated audit-overhead estimate.

The short paper explicitly reports three seeds and 96 runs, identifies baseline
coverage, and links the repository while noting the outstanding immutable
archive. `SHORT_REVIEW_RESPONSE.md` records the 6 November changes and primary
sources. Run `./check_short_review.ps1` to reproduce the disputed 16.48-minute
result from the original MNIST logs and check plotted coordinates against the
original CIFAR-10 client records. It writes verification artifacts to
`build_short/` without changing measurements or launching training.
