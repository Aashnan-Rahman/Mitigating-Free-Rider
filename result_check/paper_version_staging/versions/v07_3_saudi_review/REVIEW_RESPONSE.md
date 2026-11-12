# v7.3 response to the Azom review

Revision date: 12 November 2026. Review source: [Peer review_Azom.docx](Peer%20review_Azom.docx).
The review concerns v7.1. v7.3 builds on v7.2, not a fresh copy of v7.1.
The extracted review is preserved in `REVIEW_TEXT.txt`.

## Assessment

The central criticism is fair: good results for the combined pipeline do not
establish that traps cause the gains. A matched passive ablation is the most
important outstanding test. The failed five-epoch STD-DAGMM recipe cannot support
a claim of superior detection. Low prevalence, norm-matching, honest heterogeneity
and server-only accounting are also substantive concerns, not presentation issues.
The existing queue addresses some of these questions, but not all of them.

Three qualifications matter. First, the support gate limits the size of the
**nominated cohort**. Five attackers could in principle enter a larger mixed
cohort, so “no statistical detection below 10% at all” is too absolute. The
observed five-client misses remain real. The exact formula is
ceil(n / ceil(sqrt(n))), which is not always ceil(sqrt(n)). Second, FR4's additive
delta cancels the sent model, but challenges can still alter honest responses
and hence its reference distribution. Only a matched experiment can show whether
that helps. Third, the timing measurements remain observations of the declared
recipe even when its detector fails; they cannot establish a useful detector's
intrinsic cost or an effectiveness-adjusted speedup.

The proposed demand for identical permanent-removal endpoints needs care: a
baseline that only flags or personalizes should retain its native endpoint.
Report native decisions and, separately, a declared common mitigation adapter.
Otherwise a supposedly fair comparison changes the baseline's method.

## Response by concern

| Item | Already in v7.2 | v7.3 action | Remaining evidence |
| --- | --- | --- | --- |
| M1: traps may not matter | Scope limitations and pending passive tests acknowledged | Explicit FR4 additive cancellation and FR1 no-trap observation; remove any inference that pipeline recall proves trap benefit | Matched ordinary-model ablation is queued; standalone norm/profile/sendback and memory ablations are **not scheduled** |
| M2: weak threat model | Non-adaptive scope; norm-matching feature diagnostic; non-IID 5/10/20% checks; small-cohort limitation | Exact integer support bound in abstract/method; both IID and non-IID completed results in one table; hash-sharing collusion risk explicit | Remaining low-share runs active/queued. Published attacks queued. Mixed strategies, full-model norm-matched FR4 and S2-WEF camouflage attacks are **not scheduled** |
| M3: no working baseline | Zero attacker flags and honest flags disclosed; no detection ranking claimed | Explicitly call the recipe unsuccessful as a comparative detection baseline, separate its chosen fitting budget from the published method; add related WEF literature | Validate/fix STD-DAGMM against author settings or replace; WEF/common-endpoint comparison **not scheduled** |
| M4: cost denominator | Full stage table, withheld responses, residual-runtime caveats | Abstract uses 215/791 ms; define checking-plus-aggregation denominator (87.8/89.2%); explain diagnostic evaluation from instrumented code; disclose unresolved 8.95 s honest-training gap | Controlled timing rerun and N=100/500/1,000 scaling **not scheduled**. Existing data cannot prove the cause of the gap or actual wasted CPU/energy |
| M5: honest harm | Four honest-only runs, three main-grid false removals, unresolved-label costs already disclosed | Run-level uncertainty example for honest-only null; reject treating 6,240 correlated client-cases as independent; retain unresolved only as a defined operational label, not a useful final classifier | Additional registered seeds last. Alpha=0.1/1.0 sweep and cluster-aware uncertainty for error rates **not scheduled** |
| M6: positioning/links | Original bibliography rebuilt from BibTeX | Add WEF-defense, S2-WEF preprint, FLET and FLoomChecker; clean BibTeX build and PDF link check | Added papers are related work, not executed baselines; detailed protocol replication still needed |

## Minor and presentation changes

- Both 4-by-4 geometry figures are now **Appendix A in the main paper PDF**.
  They were already present in the separate v7.2 supplement, so they were not
  missing data, but were absent from the main file the user was reading.
- Abstract explicitly limits attackers, support size, measured population and
  withheld contributions. The simulator percentage no longer carries the cost
  claim by itself.
- Main geometry captions distinguish averaged plotting coordinates from the
  individual per-trap certificate tests.
- Cycle outcome and participation status are defined separately. “Unresolved”
  is retained consistently, without calling every such client a free rider.
- Equations and tables are rebuilt from LaTeX rather than edited through PDF
  text extraction. Render checks and resolved references are part of validation.
- The review's equation and figure numbers refer to v7.1 and may differ in v7.3.

## Experiment snapshot incorporated

This is a dated inventory, not a live monitor. Machine-readable records and source
hashes are in `generated/saudi/snapshot.json`; completed outputs are exported in
`generated/saudi/completed_runs.csv`. Every included run has 100 ordered round
records and a completed run configuration. Partial outputs do not become results.

| Phase, in current queue order | Complete / planned | Status at snapshot |
| --- | ---: | --- |
| Honest-only, seed 42 | 4/4 | Complete, zero honest removals |
| Low-prevalence, 5/10/20% | 35/48 | Running MNIST IID FR1 at 20%; other incomplete cells shown as dashes |
| Passive ordinary-model ablation/MAD diagnostics | 0/16 | Queued |
| Oracle utility comparisons | 0/12 | Queued |
| Published decaying-noise/scaled-delta attacks | 0/16 | Queued |
| Remaining MNIST baseline seed 73 | 16/16 | Complete |
| MNIST baseline seed 43 | 1/16 | Deferred for priority work, remains in queue |
| Registered held-out multi-seed checks | 0/70 | Last |

All non-IID low-share cases are complete. At 5%, FR1 removes 5/5, FR2–FR4
remove 0/5, on both datasets. At 10% and 20%, all non-IID attacks are removed;
CIFAR-10 non-IID FR3 at 10% removes one honest client. MNIST IID is complete
at 5% and 10%, plus FR2–FR4 at 20%, with the same recall pattern and no honest
removals. The remaining FR1 20% run is not counted as complete.

The original 96-run main grid and 81-pair matched baseline snapshot are retained
unchanged. New prospective checks are not pooled into the original study. The
72-case oracle feature diagnostic is still a single-cycle replay, **not** an
adaptive full-model attack or a permanent-removal experiment.

## Recommended additional work, not silently added to the queue

1. Finish the registered passive ablation. Compare detector quality and honest
   withholding with the active pipeline. Do not tune thresholds using these outcomes.
2. Run component and certificate-memory ablations with frozen settings and seeds.
3. Establish a functioning detection baseline. Record native flags, false flags,
   time and any separately declared mitigation policy.
4. Run norm-matched full-model FR4, mixed strategies and challenge-aware attacks,
   including the published camouflage threat. Distinguish an oracle attacker from
   a client-visible estimator of honest scale.
5. Measure the leave-one-out step at 100/500/1,000 clients with fixed tensor count,
   report CPU threads, repetitions, memory, and synthetic-versus-real inputs.
6. Run alpha=0.1/0.5/1.0 and honest-only replications, then use federation-level
   uncertainty rather than independent-client confidence intervals.
7. Reconcile native timing harnesses under controlled execution conditions.

These are recommendations, not authorization to alter the running registered
protocol. No queue, source-hashed file, threshold, attack definition or recovery
setting was changed for this manuscript revision.

## Verified reference sources

- WEF-defense: https://arxiv.org/abs/2206.05406 (cited as the verified 2022 preprint;
  no unverified 2024 journal metadata invented).
- S2-WEF: https://arxiv.org/abs/2604.04611v3 (explicitly a preprint).
- FLET: https://doi.org/10.1109/TON.2026.3668944; metadata checked against
  https://api.crossref.org/works/10.1109/TON.2026.3668944.
- FLoomChecker: https://doi.org/10.1109/ICPADS63350.2024.00034; metadata checked
  against https://api.crossref.org/works/10.1109/ICPADS63350.2024.00034.

The added positioning is limited to verified method descriptions and metadata,
not a claim that all four implementations were obtained or tested.
