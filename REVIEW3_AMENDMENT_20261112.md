# Prospective experiment amendment — 12 November 2026

Branch: `v15.4-completed-study`. Paper work remains on `v15.4-paper-version`.
Commit this document, implementation and `configs/review3_registration.json`
together before launching any new phase. Tag the frozen commit
`review3-20261112-frozen`. No detection outcomes were used to choose the grid.

## Preserved registered work

All 22 source hashes and six plan hashes in `review2_registration.json` are
unchanged. Existing checkpoints and completed records retain their original
manifests. Finish the current 48 low-share cases, then run the original 16 passive
cases unchanged. Do not discard 5% cells. All 70 originally registered held-out
cases, seeds 101/103/107/109/113, remain last, including all small-prevalence cases.
The default detector, perturbation .01, support gates and confirmation are unchanged.

## Amended sequential order

1. Existing honest-only (4 complete), low-share (48), passive (16).
2. One analysis job: passive/paired separation, existing MAD diagnostic, synthetic
   N=100/500/1,000 scaling, native timing re-analysis, and synthetic STD smoke check.
3. Two STD-DAGMM validation attempts: Lin-like MNIST IID, 100 clients, one
   delta-weight attacker, two-layer fully connected model, global eta .3 and 1.
4. Block B: 16 unperturbed frozen-challenge controls, then 64 component/memory arms.
5. Original 16 published-attack runs, followed by eight new norm-matched/mixed runs.
6. Twelve stronger-heterogeneity checks, then all 32 exploratory gamma cells.
7. Existing oracle utility (12) and remaining MNIST no-defense baseline phases.
8. All original held-out cases last. Optional WEF/S2-WEF reproduction is **not**
   claimed implemented or scheduled.

`configs/review3_priority_queue.json` is the executable queue. Block B adds
**132 full training runs**, plus two ten-round STD attempts and one analysis job.
This considerably extends the previous queue estimate. Every new training cell
uses seed 42; this is a development/ablation block, not new independent validation.

## Block B definitions

- Zero-perturbation controls: frozen dispatched models and original withholding
  schedule remain. Scale=0 yields exactly the frozen model, distinct from passive
  sampling of the current ordinary model. Both datasets/partitions, FR1–FR4,
  40% attackers, 100 rounds: 16 runs.
- Component arms: norm-only, profile-only, sendback-only, and no retained memory,
  each across those 16 settings. Norm/profile arms neutralize the other view
  **before nomination** and disable exact sendback. This is different from the
  old diagnostic that merely counted channels after joint nomination.
  Sendback-only does not run statistical screening. No-memory retains the
  two-cycle safeguard but requires adjacent same-component certificates instead
  of keeping them across ambiguous cycles. Scheduling/mitigation rules remain.
- Full-model `OracleNormMatchedFR4`: rescale nonzero FR4 deltas to the previous
  round's median honest delta norm. The simulator explicitly supplies this extra
  information to the attacker, **not to the detector**. First response has no
  oracle scale. This is a strong oracle-assisted stress attack, not a claim that
  a real client can observe honest updates. Serialize the scale for recovery.
- `MixedFR`: assign FR1–FR4 in balanced, fixed proportions over sorted attacker
  IDs. Assignments and attack histories are checkpointed. Both new attacks run
  on both datasets/partitions at 40%, 100 rounds: eight runs.
- Heterogeneity: alpha .1/1.0, both datasets, non-IID honest-only plus FR3/FR4 at
  40%: 12 runs. Existing alpha .5 cases remain the reference, not new reruns.
- Exploratory gamma grid: **0/.005/.01/.02**, FR3/FR4, both datasets/partitions,
  40%, first 30 rounds: 32 runs. Report every cell. .01 remains the main setting.
  Selecting and adopting a different gamma requires a new frozen version and
  a fresh held-out evaluation. The original version's registered seeds are not
  an unseen test of a detector selected after their outcomes were examined.

## Metrics fixed before launch

Primary outcomes: per-run removal TP, FP, FN, recall, precision, final accuracy
and first complete-removal round. No detection by the horizon remains a failure,
not a dropped case. An incomplete run remains incomplete and blocks successors.

Separation: round-20 selected A/B pairs for all 100 clients. Free rider is the
positive class; scores are the arithmetic mean of **negative norm-z** and,
separately, the mean of **positive profile-z**. Use rank-based AUROC with half
credit for ties. No tuned combined score, sign selection or best-cycle reporting.
Both one-dimensional metrics and the removal endpoints are reported, with all
settings retained. Evaluation labels are attached only after score production.
The existing MAD lower-tail nominal alpha .01 is unchanged; it is an observational
flag baseline and not a calibrated FPR guarantee or permanent-removal result.

Score logging already exists in `cycle_probes.csv`, `cycle_signals.csv` and
`cycle_decisions.csv`. In passive runs, A/B identify observation slots; they are
not actual trap labels. No frozen-source logging patch was necessary.

Replay is not a substitute for a rerun: active/passive trajectories can diverge
during initial probing, before the first quarantine. Report offline calculations
as diagnostics on stored observations, not counterfactual removal performance.

## Baseline and cost checks

Lin-setting attempts follow the published MNIST/100-client/one-DWA/two-layer-FC
setting and eta .3/1. Reference: https://arxiv.org/html/1911.12560#S5.SS3.
The article does not specify every reproduction choice. We declare 784–256–10,
SGD .01, one local epoch, batch 32, 50 detector epochs per round, batch 20, seed
42, and ten actual rounds. These are **not author code or exact author settings**.
Higher energy is the fixed anomaly direction. Record every client's energies,
AUROC and mean+population-SD flags each round, without removal or an attacker
quota. A completed run is an executed validation attempt, not automatic evidence
that the detector works. Numerical failures block successors and remain visible.

The synthetic STD check tests numerical behavior only. It does not solve the
missing real detection baseline. WEF/S2-WEF would require their additional client
information and separate attack implementations; keep that optional Block C.

Synthetic scaling holds L=8 and seed42 fixed, with continuous random profiles,
N=100/500/1,000, one warmup and three timed repetitions, torch threads=1. Time
feature construction and decisions separately; record before/after RSS as
snapshots, **not peak memory**. These are not model-training or deployment tests.
The sequential controller prevents overlap with project training; outside CPU
activity is a remaining environmental limitation.

Native timing re-analysis reports absolute checking time, its SD and its share
of checking-plus-aggregation. Client diagnostic evaluation is simulator evaluation
of fabricated responses for reporting, not a detector input. The CIFAR training
time gap remains observationally unexplained; do not attribute it to detector
speed. Withheld responses are forgone contributions, not measured CPU/energy waste.

## RAM and recovery

`run_review3_batch.py` supervises both frozen and new workers. It does not change
the frozen runner or historical manifest. Its operational headroom is configurable
in `review3_resources.json`: **.75 GiB MNIST, 1 GiB CIFAR**, instead of 2 GiB for
everything. These are launch safeguards, not measured minimum requirements.
It does not kill other applications, disable the pagefile or change detection.

The original startup/logon/five-minute task and saved credentials are retained.
The active selector points to the amended queue; watch follows it automatically
and now displays a resource-wait/error reason. Batch/worker locks reject duplicate
execution. Original workers keep their original checkpoints; new Block B workers
checkpoint the added attack state. Successors never proceed after incomplete work.

Commit/tag before activating the new queue. Future changes to registered source
bytes must be another amendment; never rewrite registration to resume a changed
scientific protocol. Operational launch resources are intentionally separate.
