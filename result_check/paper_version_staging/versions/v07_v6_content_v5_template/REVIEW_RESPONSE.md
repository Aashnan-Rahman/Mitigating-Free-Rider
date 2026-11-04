# Response to the supplied BaitFL review

Review: `BaitFL Paper Review Fixes, Graphs, Reviewer Report and Venues.pdf`.
Revision date: 4 November 2026. The study remains at three seeds (42, 43, 73).
No experiment engine, attack implementation, detector setting or running job
was changed. The manuscript distinguishes revisions supported by existing
records from questions that require additional experiments.

## Changes made

| Review issue | Revision |
| --- | --- |
| Seed count and pooled percentages | State three seeds and 96 detection runs in the abstract/setup. Treat a full run as the experimental unit. Identify pooled precision as descriptive, not a confidence bound over independent clients. Add final-accuracy sample SDs, and report that honest removals cluster in two runs with per-run precision down to 95.24%. |
| Incomplete baseline comparison | Refresh completed matched records: 63 pairs, comprising 16 MNIST and 47 CIFAR-10 cases. State coverage explicitly and retain the remaining incompleteness once in Discussion and Limitations. Partial runs are excluded. No missing result is imputed. |
| Comparisons address different questions | Separate empirical BaitFL detection, no-defense model utility, STD-DAGMM timing and qualitative requirements/privacy comparisons. Do not claim comparative detection superiority or measured privacy superiority over PASS, FRAD or FRIDA. |
| Narrow timing experiment | Lead the abstract and interpretation with measured checking shares of 0.58%/0.89%. Retain the declared five-epoch budget and one non-IID FR3 timing configuration per dataset in the body. Remove the STD-DAGMM speedup/fitting-budget detail from the abstract. |
| Large STD-DAGMM unassigned time | Explain that this is elapsed time minus explicitly timed computation and I/O, not detector fitting. The residual is excluded from computation totals but included in elapsed time. Avoid attributing its gap to a faster detector. Rename the displayed row to Unassigned runtime. |
| Cover and notebook language | Remove MSc Thesis, the version/date overlay and colored abstract. Replace queue, paper-guided and harness wording in the rendered manuscript. Distinguish fixed challenge models from implementation-version language. |
| Introduction and roadmap | Remove healthcare framing and its unrelated reference. Add a headline outcome after introducing BaitFL and reference the methodology, results, complexity, and merged discussion sections. |
| Dense methodology | Add an intuition paragraph and a notation/settings table. Explain the square-root support rule and profile-spacing alternative. Separate fixed engineering choices from population-derived boundaries and state that there is no held-out tuning or sensitivity study. |
| Symbol ambiguity | Use `ell_cyc` for paired-cycle length, retaining `L` for floating tensor count in the complexity analysis. Match the cycle algorithm accordingly without changing its behavior. |
| Repetitive security/limitations material | Merge security and future-work material into Discussion and Limitations. Preserve the observation-equivalence argument, confirmation limits, privacy assumptions and operating-range constraints. |
| Narrow bibliography | Add 17 relevant references and remove the medical reference, increasing cited works from 15 to 31. Cover DAGMM, robust aggregation, heterogeneous optimization, verifiable training, Shapley valuation, update leakage and realistic FL benchmarks. |
| Missing requirements comparison | Add a source-based table separating extra learning, client work, server work and information exposure for STD-DAGMM, FRAD, PASS, FRIDA variants and BaitFL. It is explicitly qualitative. |
| Duplicate round-time column | Remove time from the detection/accuracy table; retain it in the resource table. |
| Honest-impact table omissions and unclear units | Include every FR1–FR4 condition. Clarify final candidates, permanent removals, clients ever quarantined, excluded ordinary responses and withheld participation. Define client-rounds and the active-honest denominator. Expand execution-duration units to minutes per run. |
| Uncertainty in tables | Preserve round-to-round mean/SD in the instrumented timing table and add across-run accuracy SDs to the main performance table. Do not treat round variation as seed variation or manufacture confidence intervals. |
| Graph of the challenge mechanism | Method intuition is added. The representative-run norm plots were withdrawn after author feedback, and their diagnostic exports are retained. Figure 5 now shows aggregate model accuracy across three BaitFL replications and available baseline records, with coverage explicitly labeled. A matched mechanism ablation remains outstanding. |
| PDF artifacts and layout | Check extracted text for thenuse, Honestonly and receivedmodel. Fix long reference-URL wrapping. Use ragged-right prose in wide tables, improve notation-table row spacing and avoid a large gap before the attack definitions. Keep all four attack definitions in one column. |
| Code/data statement | Add the project repository URL and describe retained decisions, timing and source hashes. State that a public immutable archive of the exact evidence snapshot is still unavailable. Do not claim an archival DOI or public release that has not been made. |

## Corrections to the review's interpretation

- The value 1.33 denotes mean honest clients ever quarantined, not permanent
  removals. Counts remain integer-valued in each run.
- The 37/60 MNIST candidate fraction is 61.7%, while 43/60 on CIFAR-10 is 71.7%.
  These are now explicit. A candidate label alone does not prevent ordinary
  aggregation.
- Honest removals are not confined to FR3. Two MNIST non-IID FR3 clients were
  removed through repeated profile certificates; a third honest client in FR4
  was removed later through repeated norm certificates.
- The four implemented strategies are explicitly defined study attacks. The
  manuscript does not claim they reproduce all published decaying-noise,
  scaled-delta or adaptive free-rider attacks.

## Important experimental work still outstanding

These issues are not resolved by editing the paper, and no result is claimed:

1. Complete the remaining matched baseline coverage. The current comparison is
   a completed-record snapshot, not a finished three-seed baseline grid.
2. Honest-only populations, low free-rider proportions and additional
   heterogeneity/model settings. The population support gate remains a real
   limitation for small cohorts.
3. Published advanced attacks, trap-aware behavior, collusion and selective
   training.
4. Matched no-trap, norm/profile, memory and bounded-review ablations. The new
   norm diagnostic shows that ordinary updates can already separate some
   attacks and cannot establish the added benefit of challenges.
5. Controlled scalability, detector-only memory, transport/energy measurements,
   time-to-target utility and sensitivity to the STD-DAGMM fitting budget.
6. Held-out evaluation. Three-seed descriptive variation is reported without
   claiming calibrated error probabilities or universal detection.
7. A public immutable code/evidence release. The repository address alone is
   not represented as a completed archival release.

The audit-clock edge case is retained accurately in the algorithm and disclosed
in Discussion and Limitations. Silently correcting only the pseudocode, or
changing the study engine without rerunning it, would misdescribe the measured
method. A corrected implementation needs its own version and evaluation.

The remaining proposed heatmaps, oracle curves, ROC comparisons, sweeps and
ablation plots are not substituted with synthetic or counterfactual results.
Venue suggestions are not part of the scientific manuscript, and no new
quartile/ranking claims are made in this revision.

## Validation and provenance

The primary reporting pipeline validates all 96 completed configurations and
their implementation hashes. The baseline comparison validates completed
matching records and reproduces their common warmup trajectories. The new
diagnostic checks all initial ordinary/challenge coverage and emits
`generated/comparison/ordinary_trap_clients.csv`, `ordinary_trap_pairs.csv`
and `reviewer_diagnostic_provenance.json`. Quartile exports from the initial
boxplot and paired scatter remain available, but the manuscript now uses
empirical cumulative distributions, exported as ordinary_trap_cdf_values.csv.
Main accuracy SDs use the three
complete runs per condition. Timing SDs continue to use 100 recorded rounds.

The source is rebuilt with PDFLaTeX/BibTeX and checked for unresolved references,
overflowing boxes, oversized floats and reported extraction artifacts. Tables,
the accuracy curves, timing panels and affected layouts are inspected visually.

The final Figure 5 is generated by `build_accuracy_comparison.ps1`. It validates
all three BaitFL trajectories per attack setting and gives the four attacks
equal weight. Baseline curves use all completed matched baseline records, but
the BaitFL curve is not restricted to that subset. This unequal coverage is
explicit in the figure and text. Endpoint checks compare BaitFL to the primary
performance table and no-defense to the baseline table. The paired utility
estimates remain based on the matched table, not on this unbalanced overlay.
