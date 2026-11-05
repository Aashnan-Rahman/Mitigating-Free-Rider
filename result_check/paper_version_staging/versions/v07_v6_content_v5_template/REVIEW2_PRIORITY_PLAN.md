# Review update 2: actions and frozen experiment order

Synchronization note, 6 November 2026: the latest manuscripts from the writing
laptop were pulled at `82e31e3` and preserved. Their baseline tables use the
63-pair published snapshot. The 81-pair refresh described later in this log is
the 5 November local revision, retained in the verified recovery archive; it
has not overwritten the newer authored manuscripts. New completed review
records are published separately for a later deliberate manuscript update.

The paper's completed 96-run v15.4 evidence remains immutable. New results
belong to `results/review2_*`, with an independent engine and source hashes.
No detection threshold, support gate or confirmation setting is fitted to the
new outcomes. Misses at small attack shares must be retained and reported.

## Completed inexpensive corrections

- Lead with complete observed recall and 3 honest removals in 2 of 96 runs.
- Describe final model accuracy as comparable or slightly higher, with the
  existing incomplete paired coverage stated explicitly.
- Distinguish unresolved candidate labels from quarantine, removal and
  contribution eligibility. The broad FR3 candidate labels are not evidence
  of useful discrimination by themselves.
- Use separate cohort/peer symbols and detector-work notation.
- Report the stored STD-DAGMM recipe's flags as observational diagnostics,
  not a fair permanent-removal benchmark or a claim about all STD-DAGMM recipes.
- Verify the corrected clock guard agrees with all 622 recorded audits.
  New experiments use the liveness correction in `train_review2.py`; the
  checkpoint-hashed `train_v15_4.py` remains unchanged.
- Keep figure titles short. Axes, transforms, coverage and scope belong in
  adjacent notes or prose rather than in long figure titles.

## Ordered computation

Every new primary run uses 100 clients, 100 rounds, seed 42 and the frozen
training/protocol settings. Non-IID and difficult FR3/FR4 cases run first.
The current MNIST replication yields at a safe checkpoint boundary;
its remaining work is retained in the final replication phase.

| Priority | Evidence | New runs |
|---|---|---:|
| 1 | Honest-only BaitFL: both datasets and IID/non-IID | 4 |
| 2 | 5%, 10%, 20%: both datasets, both partitions, FR1–FR4 | 48 |
| 3 | Passive ordinary-response ablation at 40%, same screening/confirmation | 16 |
| 4 | Oracle utility reference at 0%, 30%, 40%, exact same honest identities | 12 |
| 5 | Fraboni decaying noise and Zhu scaled delta, 30%/40%, both datasets/partitions | 16 |
| 6 | Finish the already scheduled matched MNIST baseline replications | Existing work |
| 7 — last | Unseen seeds 101, 103, 107, 109, 113: non-IID honest-only and FR3/FR4 at 5%, 10%, 20% | 70 |

There are 96 new single-seed runs before the final replication phase, then
70 additional held-out runs. This is a substantial sequential workload,
not a quick pilot. Existing completed baseline partners are skipped.
`configs/review2_priority_queue.json` is the machine-readable order.

## Comparisons and interpretation

The passive ablation keeps the same selected response slots and the exact
norm/profile screening, evidence and confirmation backend. Clients receive
ordinary current models. Responses are not withheld merely for being sampled,
but fresh quarantine/removal can still exclude a response at a decision.
The two slot labels in passive `cycle_probes.csv` indicate paired sampling,
not two distinct challenge models. `was_trapped` and trap assignments record
actual challenges only. Compare with seed-42 v15.4 cases and disclose the
independently audited clock correction.

A cheap MAD-on-norm diagnostic is computed on each passive run's complete
round-20 population, before permanent removals. The lower-tail nominal
alpha is fixed at 0.01 and the scale uses normal-consistent MAD. This is a
declared statistical baseline, not a calibrated error guarantee. Truth labels
are supplied only after screening to count errors. Its flags are not removals.

The oracle is an explicitly label-aware utility reference. It keeps the same
100-client partition, initialization and honest identities, excludes the
designated free riders before training and performs no auditing. Oracle
exclusions must never be counted as detector successes. A 0%-attack oracle
also measures the cost of auditing an otherwise honest federation.

Published attacks follow [Fraboni et al., Section 3.2](https://proceedings.mlr.press/v130/fraboni21a/fraboni21a.pdf)
and [Zhu et al., Eq. 9](https://neurips2021workshopfl.github.io/NFFL-2021/papers/2021/Zhu2021.pdf).
They use only each client's received-model history, not the true ordinary
global model during challenges. Fraboni uses gamma=1, multiplier=1 and RMS
sigma from the first observed received-model difference. Zhu uses the exact
ratio of consecutive delta norms; missing-history and zero-denominator
behavior is declared in the implementation. Only trainable parameters are
fabricated; non-parameter BatchNorm buffers are preserved. These are
paper-guided adaptations, not author-code reproductions. No attack parameters
are optimized against BaitFL. Zhu's distinct advanced attack and an adaptive
challenge-aware attack remain separate future tasks.

## Recovery, watch and completion

- The existing boot, logon and five-minute Windows task remains the entry point.
- `resume_experiments.ps1` now recognizes isolated `review2` batches.
- Plans and source hashes are frozen when a batch starts; a mismatch blocks
  mixed results. Training checkpoints restore model, clients, RNG and evidence.
- Batch and worker locks prevent duplicate writers after interrupted launchers.
- Incomplete/failed/stopped batches block successors. The priority handoff
  clears only its own exact stop marker after obtaining the launcher mutex.
- Both watch interfaces follow the declared queue; no new credentials needed.
- The launcher waits for 2 GiB available RAM before starting a worker. This
  operational guard does not enter client screening. Registered source/plan
  bytes are protected from Git line-ending conversion.
- A completed phase exports `review_summary.json`, including available MAD
  diagnostics. Missing runs are never treated as completed or imputed.

## Archive/DOI limitation

An archive preparation script creates a checksum-verified local evidence bundle
without inventing a DOI or publishing unfinished experiments. A Zenodo DOI
still requires an authenticated deposit and publication. This external step
is pending; the manuscript must continue to state that accurately.
Completed new results should enter the paper only after their records are
validated, never while these plans are merely scheduled.

Validation on 5 November 2026: all 44 focused tests passed, covering tiny real
training, honest-only behavior, passive withholding semantics, exact checkpoint
weight/state replay, cooldown liveness, queue ordering, ownership-safe handoff
and rejection of registered source changes. Final-round interruption tests also
check complete client/removal records on both sides of checkpoint publication.
The new engine writes evidence before checkpoints and rolls uncommitted removal
rows back with the other logs. A short warmup-only validation attempt was
preserved separately before this I/O maintenance fix and fresh registration;
no screening outcome or detector parameter informed the correction.
The paper compiled without layout or reference errors.
A verified local evidence bundle is prepared under
`.local_cleanup/review2_deposit_20261105_v3/`, with a SHA-256 manifest and no
public DOI. The earlier deposit preparation is retained as a separate snapshot.

The manuscript also incorporates every available completed matched baseline:
81 pairs, comprising 33 MNIST and all 48 CIFAR-10 pairs. MNIST has two to three
baseline replications per attack setting; CIFAR-10 has three. The descriptive
mean accuracy differences are 0.08 and 0.61 percentage points, respectively.
These are reported cautiously; incomplete replications are not imputed and
have been retained at the end of the computation queue.

An additional 41 tests passed for the existing replication, native baseline,
watch and mixed-workflow recovery paths. Historical queue fixtures now test
their declared frozen schedules instead of assuming that users can never
select a newer priority queue. The two validation groups total 85 passing tests.
