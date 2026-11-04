# Results and reviewer revision — 4 November 2026

The manuscript and its reporting scripts have been revised. Detector code,
attack code, training settings and running experiments are unchanged.
[REVIEW_RESPONSE.md](REVIEW_RESPONSE.md) maps the supplied review to completed
changes and remaining experimental work.

## Data and aggregation

- Primary results use all 96 completed executions: MNIST/CIFAR-10, IID/non-IID,
  30%/40%, FR1–FR4 and seeds 42, 43, 73. The paper now explicitly states
  three seeds. Missing or duplicated primary grid cells fail validation.
- Performance-table detection rates pool attacks within each seed and average
  the seed-level rates. Accuracy averages the three runs for each condition,
  with sample SD. Resource summaries weight attacks and seeds equally.
- Overall pooled outcomes are 3,360 true removals, three honest removals and
  no misses. Pooled precision is descriptive, not a confidence bound over
  independent clients. Honest removals occur in two runs.
- All attack conditions appear in the honest-impact table, including FR1/FR2.
  It separates final candidates, permanent removals, clients ever quarantined
  and excluded client-rounds. Withheld percentages use active honest
  client-rounds and avoid counting a trap/quarantine overlap twice.
- The value 1.33 is mean honest clients ever quarantined in MNIST/non-IID/30%/FR3.
  Individual counts range from zero to three. There are 620 honest quarantine
  client-rounds, and nobody remains quarantined at completion.
- Baseline coverage is 63 completed matched pairs: 16 MNIST and 47 CIFAR-10.
  All 32 attack conditions have a partner, but coverage across seeds is
  incomplete. Partial live runs are excluded. Average matched seeds within an
  attack, then weight the four attacks equally.
- Missing branch-local completed records are sourced from the verified
  commit-pinned snapshot in evidence/completed_baselines, without overwriting
  live result directories.

## Timing and uncertainty

The instrumented BaitFL/STD-DAGMM pairs are separate 100-round timing cases.
They are not multi-seed timing replications. STD-DAGMM uses a declared fresh
five-epoch fitting budget, not a budget established by the original paper.

Stage means/SDs are computed from all 100 rounds. Combined stages and checking
subtotals are summed within each round before SD, preserving covariance.
The export is generated/comparison/timing_table_statistics.csv. Checking
occupies 0.58%/0.89% of MNIST/CIFAR computation. Computation savings are
15.34 s (29.35%)/31.50 s (26.23%) per round; elapsed savings are
21.91 s (34.87%)/37.35 s (27.20%). Percentage shares and savings use horizon
aggregates, not an average of per-round ratios.

Unassigned runtime is elapsed time minus explicitly timed computation and I/O.
Its substantial STD-DAGMM value is not attributed to detector fitting.
Network transmission and isolated detector RSS are unmeasured.

## Honest-removal records

The explanation is checked against removals.csv and cycle_decisions.csv:

- MNIST/non-IID/FR3/40%/seed43: honest clients 54 and 90 receive profile_high
  at rounds 20 and 30, reaching two profile certificates and removal at 30.
- MNIST/non-IID/FR4/40%/seed43: honest client 52 receives norm_low/profile_high
  at 60, no fresh certificate at 70/80, and norm_low at 90. Norm memory
  reaches two and authorizes removal. No honest removal follows exact sendback.

Persistent legitimate heterogeneity can satisfy the same geometric tests.
FR3 reuses received history and can overlap genuine responses. The paper does
not claim perfect imitation or experimentally isolated causality. The candidate
fractions 37/60 and 43/60 are 61.7% and 71.7%, respectively.

## Current presentation

- Results and Discussion remain merged. Evaluation Metrics is black and grouped
  by detection, utility/honest participation and computational cost.
- Related work now includes 31 cited sources and a qualitative requirements
  table. It distinguishes timing comparisons from information/privacy
  requirements and makes no empirical detection ranking across all methods.
- A notation/settings table and intuition explain the challenge mechanism,
  profile certificate and engineering defaults. Cycle length uses ell_cyc,
  distinct from tensor count L.
- Healthcare framing, thesis/version cover labels and notebook language are
  removed. The abstract states three seeds and leads with checking cost.
- Performance reports accuracy SDs and no duplicated time column. Honest impact
  covers every attack. Resource headers identify seconds, GiB and minutes/run.
- Score scatters remain. Figure 5 now shows test accuracy versus round across
  both datasets, partitions and attacker proportions. BaitFL uses all three
  replications; no-defense uses completed baseline records. FR1–FR4 are weighted
  equally and unequal coverage is explicit. Paired utility estimates remain
  in the matched table. A standalone vector/raster preview is generated.
- Adjacent teal/orange timing bars and the completion-round mean/range plot
  remain. They follow the new norm boxplot and renumber automatically.
- Security and future-work material are merged into Discussion and Limitations.
  The uncorrected audit-clock edge case is disclosed, not silently changed.
  The repository URL and missing immutable public archive are stated.
- Appendices stay commented out with no active references.

## Regeneration and validation

Run rebuild_reporting.ps1, then build.ps1. Primary grid, implementation hashes,
native timing sources and stage sums are validated. The review diagnostics
check 1,000 initial-cycle rows per representative case, eight ordinary and two
challenge responses per client, and expected honest/free-rider populations.

Diagnostic client summaries, quartiles and input hashes are retained under
generated/comparison. The baseline snapshot can expand when more live cases
finish. Source citations, tables, norms, timing bars, attack layout and
discussion are inspected visually after compilation. References must resolve
without overflowing boxes or oversized floats.
