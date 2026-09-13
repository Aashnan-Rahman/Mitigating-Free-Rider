# Experiment Checklist

This checklist is ordered so each stage is run only after the previous stage is acceptable. Every run must use a unique `run_name` and a fixed `seed`.

## Before experiments

- [ ] Confirm the dataset cache is available and record the PyTorch/device versions.
- [ ] Run `python -m pytest -q` on the execution machine; do not begin final runs
      unless all attack and detector tests pass.
- [ ] Confirm no attacker method receives trap membership, detector decisions,
      ground-truth labels, other clients' updates, or an unperturbed server model.
- [ ] Confirm FR1, FR3, and FR4 retain every model sent to that client under the
      same rule; secret trap models must not be selectively excluded.
- [ ] Confirm checkpoint/resume preserves attacker-visible FR1/FR3/FR4 history.
- [ ] Confirm a 100-client, 10% coverage sweep probes 20 clients per round for
      10 rounds, each client receives trap A once and trap B once, each trap has
      its own complete-pass baseline, and no group-pair repeats where avoidable.
- [ ] Confirm coverage treats magnitude-only and profile-only failures as
      non-penalized candidate evidence, and applies `penalty_trap_flag` only when
      both fail on the same response. Every zero response still adds five points.
- [ ] Confirm warm-up runs only exact-zero detection and a zero response receives
      five points; nonzero norm/profile outliers must not create candidates.
- [ ] Confirm `X` and `Y` are independent: `X=max(1,floor(|S|/10))` when
      suspects exist, while `Y` always contains ten surveillance groups.
- [ ] Confirm every suspicious group receives a different fresh trap each round,
      while the ten `Y` groups share one frozen trap over their cycle.
- [ ] Confirm any single-signal anomaly creates C, a fully normal candidate probe
      returns it to U, and two joint failures move it to S.
- [ ] Confirm candidates and all previously flagged clients are never anchors.
- [ ] Run one short smoke test per attack and inspect returned-update norms and
      first-round behavior before launching the experiment matrix.
- [ ] Confirm the detector uses robust norm z-score plus normalized per-tensor
      layer-profile distance; cosine is diagnostic only.
- [ ] Confirm client-local loss and accuracy never enter flag, penalty, suspicion,
      rehabilitation, or removal decisions; their CSV values are diagnostics only.
- [ ] Confirm nonzero joint-evidence removal requires both `P_i >= P_max` and at least
      ten S-state probes, while three accumulated exact send-backs remove without
      waiting for that probe gate.
- [ ] Confirm a client meeting the ten-probe, at-most-10% rehabilitation rule is
      rehabilitated rather than removed by its reversible magnitude episode.
- [ ] Keep `save_checkpoints=true` and `checkpoint_keep_last=5`; confirm every
      round creates a recoverable checkpoint and only the five newest numbered
      snapshots remain while running.
- [ ] Confirm successful experiments delete all numbered checkpoints and
      `latest_checkpoint.pt`, while interrupted/failed experiments retain them.

Results generated before the attack-information-boundary correction must be kept
for provenance but must not be mixed with or reported as results from the corrected
threat model.

## Stage 0: Pipeline validation

- [ ] Smoke run: 4 clients, 2 rounds, CPU. Verify all CSV/JSON/PT files exist.
- [ ] Confirm C/S clients leave their episode only after a fully normal candidate
      confirmation or at least ten probes with a joint-failure rate at or below
      ten percent; magnitude points clear but exact-zero points remain.

**Go criterion:** during an interrupted check, `latest_checkpoint.pt` and no more
than five numbered checkpoints are present; after a successful run,
`latest_results.json` remains and all checkpoint files are gone.

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
- [ ] FR2, 40%, selected threshold plus dodge-index rehabilitation
- [ ] Repeat the winning configuration with seeds 43 and 44

Primary decision metrics: honest removal rate, FR2 recall, precision, F1, and
accuracy. Inspect robust norm z-scores and MAD values for scale stability.

## Stage 4: FR3 detection limits

Evaluate FR3 using the same gradient-only detector used for every attack:

- [ ] FR3, 40%, IID, seed 42
- [ ] FR3, 40%, IID, seeds 43 and 44
- [ ] Inspect per-probe norm distributions for honest/FR3 overlap without feeding
      ground truth or client-local metrics into the detector
- [ ] Report indistinguishable responses as a detector limitation rather than
      introducing an attack-specific rule

Treat persistent honest/FR3 overlap as a limitation unless a new server-observable
gradient statistic shows separation.

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
- FR3 limits: 3 runs, including two confirmation seeds
- Distribution robustness: 6 runs

**Minimum total: 25 runs.** Additional seeds should be added only for configurations that survive their stage's go criterion. The count excludes exploratory threshold sweeps and failed infrastructure runs.

## Required result files per run

- `global_metrics.csv`: one row per round, including accuracy, loss, active clients, trapped clients, aggregated clients, and time.
- `client_metrics.csv`: one row per active or inactive client per round, including
  simulation-only local accuracy/loss, gradient-norm and layer-profile robust
  z-scores and median/MAD baselines, individual and joint flags, coverage observation round, coverage check/flag counts,
  cosine diagnostic, detection reason, flag, and penalty adjustment. Legacy
  loss-z fields must remain empty.
- `penalty_tracker.csv`: cumulative penalty, U/C/S state, zero-update count, and
  flag/trap counts per client per round.
- `trap_matrix.csv`: trap membership and phase per round.
- `trap_assignments.csv`: role and suspicious-group assignment for every probed client.
- `dodge_tracker.csv`: suspicious-episode probes, flags, dodge index, and lifetime trap flags.
- `rehabilitations.csv`: clients returned from the suspicious pool to the unflagged pool.
- `candidate_events.csv`: candidate entry, confirmation, and clearance events.
- `removals.csv`: removal round, ground-truth role, evidence basis, zero count,
  and suspicion-probe count.
- `run_config.json`: complete configuration and final summary.
- `latest_results.json`: latest completed round and latest global metrics.
- `latest_checkpoint.pt`: active/interrupted-run copy of the latest detector state;
  deleted after successful completion.
- `checkpoint_round_XXXX.pt`: rolling snapshots; only the newest
  `checkpoint_keep_last` files are retained while running, then deleted on success.
