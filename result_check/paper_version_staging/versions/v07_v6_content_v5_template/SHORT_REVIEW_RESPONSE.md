# Short-paper review response — 6 November 2026

The revised short edition remains six pages including references. The full
manuscript, study code and measurements are preserved.

## Changes

1. **STD-DAGMM attribution.** Attribute STD-DAGMM to Lin [4], and DAGMM to
   Zong [6], with separate citations in the same sentence.
2. **Replication.** Restore three seeds (96 runs) in the abstract and Section
   V-A. The retained study contains 32 configurations with three distinct seeds
   each. No experiments are added.
3. **Availability.** Restore the project repository URL and explicitly state
   that an immutable public archive of the exact evidence is not yet available.
   Zenodo publication remains a task before submission. No archive has been
   published and no DOI is claimed for this work.
4. **Disputed target time.** Recompute the first crossing of 98% accuracy from
   the original MNIST non-IID, 40%, seed-42 global logs, checking all round times
   and accuracies against the paired exports and the raw file provenance.
   The four attack crossing times, in seconds, are:

   | Attack | First round | Cumulative seconds |
   | --- | ---: | ---: |
   | FR1 | 27 | 941.647913600 |
   | FR2 | 27 | 939.817192700 |
   | FR3 | 34 | 1196.123099800 |
   | FR4 | 25 | 876.858376000 |

   Their mean is **16.47686075875 minutes**, hence **16.48**. The current
   full-paper Figure 6 also uses 16.476861 as its plot coordinate. The 16.109690
   value belongs to the no-defense MNIST IID, 30% group. The correct value is
   retained in the short paper, together with its observational timing caveat.
5. **Mechanism evidence.** Replace the redundant timing plot with two panels
   from CIFAR-10 non-IID, 40%, round 20, seed 42: FR2 and FR3. A single FR3 panel
   cannot also show FR1/FR2, so the two panels provide the requested comparison.
   All 60 honest and 40 free-rider points per panel are checked against the
   original two selected challenge responses per client. Axis limits include
   every point. FR2 points cluster almost identically, without artificial
   jitter. FR3's *profile scores* overlap the honest range, although its norm
   scores remain lower. The prose specifies this distinction and avoids
   claiming full two-dimensional overlap or a demonstrated passive-ablation
   advantage. The same FR3 run receives paired norm evidence at rounds 20 and
   60, illustrating separated confirmation cycles.
6. **Attack coverage.** Explicitly name Fraboni's decaying-noise disguise and
   Zhu's scaled-delta and advanced attacks as unevaluated, with citations.
7. **Introduction.** Add the headline counts: all 3,360 free riders removed,
   with three honest removals among 6,240 honest client-cases.
8. **Baseline coverage.** State 16 matched MNIST runs, one baseline seed per
   setting, and 47 matched CIFAR-10 runs.
9. **Starting model.** Replace “model initialization” in Related Work with
   “starting model.”
10. **External context.** Add the qualified comparison to FRIDA's STD-DAGMM
    F1 range of 0.00–0.05 at 40/100 IID CIFAR-10 clients. The authors' complete
    paper, Table 9(c), lists 0.01 ± 0.00, 0.05 ± 0.02 and 0.00 ± 0.00 across
    its three attacks. The text says “consistent with” and explicitly notes
    different attacks and setup. This does not validate our reproduction or
    establish a matched detection ranking.

## Reference checks

- [PASS author record](https://arxiv.org/abs/2207.07292) explicitly links
  10.1109/JIOT.2023.3288936 and the published journal metadata. No change needed.
- Clicked the [Melis DOI](https://doi.org/10.1109/SP.2019.00029) through the
  [UCL record](https://discovery.ucl.ac.uk/id/eprint/10061777/). It redirects to
  IEEE Xplore document 8835269. UCL confirms the title and pages 691–706.
  Direct IEEE page content remains limited by its access check. No DOI change.
- [Fraboni's original paper](https://proceedings.mlr.press/v130/fraboni21a/fraboni21a.pdf)
  describes the stochastic disguise with decaying perturbations.
- [Zhu's original paper](https://neurips2021workshopfl.github.io/NFFL-2021/papers/2021/Zhu2021.pdf)
  names scaled delta and advanced free-rider attacks.
- [FRIDA's author manuscript](https://arxiv.org/pdf/2410.05020), Table 9(c),
  supplies the external STD-DAGMM comparison. The existing published journal
  reference is retained.

## Validation

`check_short_review.ps1` independently checks the raw target-time trajectories,
plotted score coordinates, complete point counts and axis bounds, study seed
counts, baseline coverage and unchanged full-PDF hash. Its JSON/CSV outputs are
in `build_short/`. The rebuilt short PDF has 17 resolved references, no undefined
citations or cross-references, and no overfull boxes or oversized floats.
All six pages are visually checked, including the new scatter and final columns.
Only the short-paper wording, presentation and accompanying notes change.
