# Experiment Checklist

This checklist is ordered so each stage is run only after the previous stage is acceptable. Every run must use a unique `run_name` and a fixed `seed`.

## Before experiments

- [ ] Confirm the dataset cache is available and record the PyTorch/device versions.
- [ ] Run `python -m pytest -q` on the execution machine; do not begin final runs
      unless all attack and detector tests pass.
- [ ] Confirm no attacker method receives trap membership, detector decisions,
      ground-truth labels, other clients' updates, or an unperturbed server model.
- [ ] Confirm FR1 returns every currently received model unchanged and FR3/FR4
      retain every model sent to that client under the same rule; secret trap
      models must not be selectively excluded.
- [ ] Confirm checkpoint/resume preserves attacker-visible FR3/FR4 history.
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
- [ ] Confirm active anchor panels rotate through never-flagged U clients and a
      one-group S phase does not reuse the same three anchors in consecutive rounds.
- [ ] Confirm all U clients, including off-duty potential anchors, appear once in
      each ten-group Y audit cycle; a Y flag permanently removes anchor eligibility.
- [ ] Confirm off-duty anchor-roster clients contribute normally unless selected
      as an active anchor or as part of the current trapped Y group.
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

## v10 protocol checks (required before full experiments)

- [ ] FR1 earns exactly one send-back strike per round and all FR1 clients are
      removed at the end of warm-up round 10 with no earlier removal.
- [ ] Initial rounds 11–20 use ten groups, two frozen traps, and give every active
      client each trap exactly once.
- [ ] Later groups are state-homogeneous; C/S never aggregate, while nontrapped R
      and probationary R do.
- [ ] Later baselines contain only same-trap, reference-eligible R responses;
      provisional R outliers are removed and the reference is recomputed once.
- [ ] One failed signal (norm OR profile) fails a probe. Confirm the configured
      3.0 multipliers remain fixed while median/MAD raw thresholds change by cycle.
- [ ] Verify R -> C first, C -> R after two clean cycles, S -> C after two clean
      cycles, and rehabilitated R becomes reference-eligible after one more clean
      cycle.
- [ ] Verify score cap at zero, -1/-2 failure costs, and removal only at score <=
      -4 with two strong cycles including one trusted-reference confirmation.
- [ ] Verify double -> single -> dormant transitions, 20 passive dormant rounds,
      the single audit cycle, and immediate return to double after an anomaly.
- [ ] Interrupt/resume during every phase and confirm the cycle queue, frozen
      traps, evidence, roles, counters, reference eligibility, and probation are
      identical after recovery.

## v11 validation gates

- [ ] Confirm the cutoff is derived from the configured false-alarm budget and
      prior cycles only; current responses cannot change their own cutoff.
- [ ] Confirm MAD uses the `1.4826` consistency conversion and historical scale
      stabilization, not the legacy absolute detector floors.
- [ ] Confirm a cross-signal pair (for example norm on A, profile on B) is weak,
      enters C, adds zero score, and cannot count as a strong cycle.
- [ ] Confirm the same anomaly signature under A and B is coherent strong
      evidence and still requires a later trusted confirmation for removal.
- [ ] Confirm current-cycle provisional outliers never trigger reference
      recomputation or removal from the frozen baseline.
- [ ] Confirm checkpoints store scalar cycle norms/profiles rather than full
      flattened client deltas.
- [ ] FR1 gate: 40/40 removed at round 10 and zero honest removals through round
      40 before enabling FR2-FR4 validation.

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
