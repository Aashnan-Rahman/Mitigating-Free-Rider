# Response to `v7 update 2.txt`

Revision date: 4 November 2026. This revision uses the existing experimental
records. It launches no training, attack, ablation, baseline or tuning runs and
does not modify the six frozen implementation files or experimental logs.
The current manuscript structure, diagrams, black text, and completed CIFAR-10
timing and baseline updates are retained.

## Addressed now

| Review point | Change and evidence |
| --- | --- |
| Accuracy improvement is overstated | Replace improvement headlines with “comparable or slightly higher.” Retain the observed 0.10/0.60 percentage-point differences as descriptive results from the available matched cases. Explain the single MNIST baseline seed and uneven CIFAR-10 coverage, and avoid a systematic-gain claim until paired uncertainty across seeds is available. Overlap with a single method's SD is not itself a paired significance test. |
| Pooled precision dominates the headline | Abstract, introduction and conclusion lead with 100% recall across 96 runs and three honest removals in two runs. The results give the denominator of 6,240 honest client-cases. Pooled precision and F1 remain descriptive metrics in the results; no independent-client confidence interval is claimed. |
| Widespread candidate labels | Explain the unresolved-evidence meaning of Candidate, continued eligibility of ordinary responses and participation in peer references. Dense probing and exclusion depend on review/probation and quarantine, not the label alone. Explicitly acknowledge its limited value as an end-of-run classifier in these non-IID cases. Do not retune the rule using the current results. |
| Sparse-audit clock flaw | Correct Algorithm IV's clock guard to use findings eligible after cooldown. Check the proposed correction against all 622 logged audits in all 96 study runs. Both guards agree at every observed audit. Supply the implementation correction as an unapplied patch and disclose the original engine's guard. |
| Notation clashes | Warmup is `T_warm`, total work is calligraphic `W_det`, and the nominated/peer sets are calligraphic `U`/`V`. Keep scalar `P` for model coordinates and plain `C` for the unresolved cycle outcome. Update equations, the warmup algorithm and notation table together. |
| Captions lack context | Score captions identify representative round-20 runs and the asinh-transformed paired mean z-score axes. The accuracy caption gives the three BaitFL replications and the one versus two-to-three baseline coverage. Detailed interpretation remains in the referenced prose. |
| URL and timing-table housekeeping | Keep a real `url` command, put the repository address on its own compact line, and rename “Research logs and checkpoints” to “Logging and checkpoints.” Preserve the measured I/O values. |
| Existing STD-DAGMM flags | Report only what the stored timing executions establish: 0 flagged free-rider responses out of 4,000 per dataset, with 2,200 and 2,196 flagged honest responses. Pooled roundwise precision and recall are zero for this five-epoch FR3 recipe. These observations are not a matched permanent-removal comparison or a ranking of the published detector. |

## Clock correction: conditional equivalence, not a new experiment

The frozen engine clears its quiet clock for any nonempty raw finding set.
The corrected guard clears it only if review actually opens. A finding blocked
by the pre-decrement cooldown cannot open review.

`check_review2_evidence.ps1` reconstructs active clients and cooldown counters
from completed-cycle decisions, release/follow-up-expiry events, and audit
decrements. It checks the original implementation hashes and records hashes of
the input traces. Of 622 audits, 609 have no findings. In each of the remaining
13, the number of raw findings exceeds the number of active cooling clients.
At least one finding must therefore be eligible, without needing to infer its
identity from subsequent training. Recorded follow-up rounds also agree with
that conclusion. The two guards make the same assignment in every case.

Since the guard is the only proposed change, this establishes equality of the
recorded schedules and decisions under that correction. It does not establish
behavior in unobserved states or beyond the 100-round horizon. The engine
remains the exact source used for the existing results. The unapplied
`AUDIT_CLOCK_CORRECTION.patch` provides the correction for a future versioned
implementation. The manuscript explicitly distinguishes its guarded algorithm
from the recorded engine and supplies the trace-equivalence result.

Outputs: `generated/review2/audit_clock_checks.csv`, `summary.json`,
`std_flag_diagnostics.csv`, and `provenance.json`. Reproduce with
`./check_review2_evidence.ps1`; it is also part of `rebuild_reporting.ps1`.

## Deferred

The following need additional experiments and are not claimed as resolved:

1. Honest-only and 5/10/20% free-rider runs, including the small-cohort gate.
2. A matched passive-screening/no-trap ablation and the other component ablations.
3. A detection benchmark with matched endpoints, a simple MAD baseline, and
   appropriate baseline-fitting validation. The existing flag diagnostic is partial evidence only.
4. Complete matched baseline coverage and an honest-only oracle.
5. Published decaying-noise/scaled-delta strategies and adaptive/colluding behavior.
6. Frozen-parameter evaluation on unseen seeds or a new dataset.

An immutable public archive and DOI also remain a pre-submission release task.
They require freezing and publishing the release. The paper retains its honest
availability statement and does not invent a DOI or claim that the mutable
repository is an immutable archive. Venue/ranking recommendations are outside
this manuscript edit.

## Validation

The 20-page PDF builds with resolved citations and references, without overfull
boxes or oversized floats. The headline counts, notation table, corrected
Algorithm IV, score/accuracy captions, and repository URL were visually checked.
The proposed engine patch passes `git apply --check` and remains unapplied.
The original six implementation hashes match the study record.
