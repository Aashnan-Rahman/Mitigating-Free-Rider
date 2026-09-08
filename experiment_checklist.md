# Experiment Checklist

This checklist is ordered so each stage is run only after the previous stage is acceptable. Every run must use a unique `run_name` and a fixed `seed`.

## Before experiments

- [ ] Confirm the dataset cache is available and record the PyTorch/device versions.
- [ ] Confirm the detector rule used by the current code: robust update-norm z-score using median/MAD; cosine is diagnostic only.
- [ ] Decide the removal policy for reporting. The specification says `P_i >= P_max`; the current code removes at `P_i > P_max`.
- [ ] Keep `save_checkpoints=true` and `checkpoint_every=1` for development runs. Use `checkpoint_every=5` for long final runs if disk space is limited.

## Stage 0: Pipeline validation

- [ ] Smoke run: 4 clients, 2 rounds, CPU. Verify all CSV/JSON/PT files exist.
- [ ] Repeat the smoke run with `penalty_decay=1` and confirm passed checks reduce cumulative penalty.

**Go criterion:** the run completes and `latest_results.json`, `latest_checkpoint.pt`, and one checkpoint per configured interval are present.

## Stage 1: Baselines, IID, 100 rounds

Run each attack at 10% free riders with the same seed and model settings:

- [ ] FR1 baseline
- [ ] FR2 baseline
- [ ] FR3 baseline
- [ ] FR4 baseline

Record: final accuracy, best accuracy, final loss, free riders removed, honest clients removed, precision, recall, F1, false-positive removal rate, first removal round, runtime, and peak active-client reduction.

**Go criterion:** no unexplained crashes, complete per-round/per-client records, and baseline accuracy is reported before comparing detector variants.

## Stage 2: Free-rider prevalence sensitivity

Use the baseline detector and run the two most relevant attacks at each prevalence:

- [ ] FR2 at 20%
- [ ] FR2 at 40%
- [ ] FR3 at 20%
- [ ] FR3 at 40%

**Go criterion:** identify whether failures are false positives, missed free riders, or accuracy degradation. Do not tune thresholds using more than one seed.

## Stage 3: FR2 false-positive mitigation

Validate the robust norm-z/MAD detector before running this stage. Keep all other settings fixed:

- [ ] FR2, 40%, norm-z/MAD detector
- [ ] FR2, 40%, z-threshold sensitivity check
- [ ] FR2, 40%, selected threshold plus `penalty_decay=1`
- [ ] Repeat the winning configuration with seeds 43 and 44

Primary decision metrics: honest removal rate, FR2 recall, precision, F1, and accuracy. Inspect robust norm z-scores and MD values for scale stability.

## Stage 4: FR3 detection limits

Implement the loss signal as a separate configurable detector. Do not mix it with threshold tuning in the first comparison:

- [ ] FR3, 40%, norm-only detector
- [ ] FR3, 40%, early loss-window detector
- [ ] FR3, 40%, norm-and-loss AND detector
- [ ] Repeat the best detector with seeds 43 and 44

Inspect the round-level loss distributions. Treat rounds after the documented overlap point as a limitation unless new evidence shows separation.

## Stage 5: Distribution and training robustness

Run the selected detector configuration, not every discarded variant:

- [ ] IID, FR2, 40%
- [ ] IID, FR3, 40%
- [ ] Non-IID alpha=0.5, FR2, 40%
- [ ] Non-IID alpha=0.5, FR3, 40%
- [ ] Non-IID alpha=0.1, FR2, 40%
- [ ] Non-IID alpha=0.1, FR3, 40%

**Go criterion:** report both detection quality and global accuracy. A detector that improves recall while damaging honest accuracy is not an unconditional improvement.

## Minimum run count

- Pipeline validation: 2 runs
- Baselines: 4 runs
- Prevalence sensitivity: 4 runs
- FR2 mitigation: 6 runs, including two confirmation seeds
- FR3 comparison: 5 runs, including two confirmation seeds
- Distribution robustness: 6 runs

**Minimum total: 27 runs.** Additional seeds should be added only for configurations that survive their stage's go criterion. The 27 count excludes exploratory threshold sweeps and failed infrastructure runs.

## Required result files per run

- `global_metrics.csv`: one row per round, including accuracy, loss, active clients, trapped clients, aggregated clients, and time.
- `client_metrics.csv`: one row per active or inactive client per round, including local accuracy/loss, norm/loss robust z-scores and median/MAD baselines, coverage observation round, cosine diagnostic, detection reason, flag, and penalty adjustment.
- `penalty_tracker.csv`: cumulative penalty and counts per client per round.
- `trap_matrix.csv`: trap membership and phase per round.
- `removals.csv`: removal round and ground-truth role.
- `run_config.json`: complete configuration and final summary.
- `latest_results.json`: latest completed round and latest global metrics.
- `latest_checkpoint.pt`: latest model and detector state snapshot.
- `checkpoint_round_XXXX.pt`: numbered checkpoint files according to `checkpoint_every`.
