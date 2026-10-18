# Paper v6 — full v15.4 study

Rewritten using v02's paper-style organization, not its old v8 decision rules.
Sections: Abstract, Introduction, Literature Review, Threat Model, Proposed
Methodology, Results, Result Analysis, Security Analysis, Conclusion, appendices.

The scope is all 32 completed v15.4 seed-42 runs: MNIST/CIFAR-10,
IID/non-IID, 30%/40% free riders, FR1–FR4. No older-method observations or
best-seed selection are mixed into the results. Earlier paper versions remain
unchanged. This is a development evaluation, not held-out-seed validation.

From the repository root:

```powershell
.\.venv\Scripts\python.exe build_paper_v6_full_study.py --compile
```

- `paper_v6.tex`, `refs.bib`: authored source.
- `paper_v6.pdf`: compiled manuscript.
- `generated/`: validated tables, eight-panel figures, data, per-run/group
  statistics, full-cycle certificate history, input provenance, build status.
- Visual revision (18 October 2026): grouped detection/FR1--FR4 accuracy/time
  table; run-level honest impact; round-20 client scatter plots for both shares;
  raw-norm histograms and mean/IQR score evolution for difficult non-IID FR3;
  independently zoomed late-accuracy panels; per-attack time and peak-memory bars.
  Repetitive recall and full-accuracy
  trajectories now appear in the appendix. Vector figures use PGFPlots, with no
  clipping, synthetic jitter, smoothing or label-derived decision boundaries.
- `generated/score_statistics.csv`, `paired_score_coordinates.csv`: complete-cycle
  score summaries and untransformed client coordinates; missing values stay missing.
- `generated/model_payload.csv`, `historical_cost.csv`, `visual_provenance.json`:
  calculated payload sizes and separately identified historical whole-process
  cost comparisons. Neither is an isolated detector-overhead benchmark.
- `evidence/source/`: copies matching the six hashes recorded by the experiments;
  not a claim of complete environment attestation.
- `build/`: ignored compilation scratch and visual-inspection previews.
- Timing revision (18 October 2026): enlarged two-column score/accuracy panels;
  native-workflow timing tables and stacked bars from 100 completed STD-DAGMM
  rounds per dataset and the matching 100-round v15.4 histories (non-IID FR3,
  seed 42, 40%). `generated/timing/` retains components, phase summaries, actual
  per-round totals and provenance. Missing historical task timers stay missing;
  phase groups are whole-round totals, not detector-only estimates. STD's
  100-round costs are now actual sums, not projections. Communication is unmeasured.
  A standalone chart report is `analysis/timing_breakdown/timing_report.pdf`.

Permanent removal, weak candidate flags, temporary quarantine, trap exclusion,
model accuracy, and whole-simulator cost are deliberately reported separately.
The security analysis gives protocol invariants and limitations, not a formal
guarantee of detecting arbitrary free riders or avoiding all future false positives.
The complexity section explicitly includes quadratic leave-one-out work, Python
median sorting, bootstrap scratch arrays and the growing research logger. Only
the compact decision state (not whole-process RSS) has the stated working bound.
