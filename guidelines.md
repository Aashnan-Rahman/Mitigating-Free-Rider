# SWT-CP: Suspicion-Weighted Trap Detection with Cumulative Penalty
## Build Specification for Federated Learning Free-Rider Simulation

This document is a complete implementation spec. Every numeric constant below is a
named configuration variable, not a hardcoded value — the code should be built so
that changing any single value in the config does not require touching logic
elsewhere.

---

## 1. Framework & Environment

- **Language / Framework:** Python, PyTorch (torch, torchvision).
- **Reproducibility:** a single global `seed` (int) config value must seed
  `random`, `numpy`, and `torch` (CPU + CUDA if available) at the start of every run.
- **Device:** auto-detect CUDA, fall back to CPU. Should be a config override
  (`"auto" | "cpu" | "cuda"`).
- **Modularity requirement:** the codebase should be structured so that dataset,
  model architecture, non-IID partitioning, attack strategy, and detection
  hyperparameters are all swappable via a single config object (dataclass or YAML/JSON
  config), not scattered as magic numbers across files. See Section 9 for suggested
  file layout.

---

## 2. Configuration Variables (all must be adjustable, with defaults shown)

| Variable | Default | Description |
|---|---|---|
| `methodology_version` | `"swtcp_v7"` | Rejects checkpoints produced by an incompatible detector protocol |
| `dataset` | `"mnist"` | `"mnist"` or `"cifar10"` |
| `distribution` | `"iid"` | `"iid"` or `"noniid"` |
| `dirichlet_alpha` | `0.5` | Concentration parameter for Non-IID Dirichlet partitioning. Lower = more skewed. Only used if `distribution == "noniid"` |
| `num_clients` (N) | `100` | Total registered clients |
| `num_rounds` (T) | `100` | Total communication rounds. Also supports `200` |
| `free_rider_pct` | `0.10` | Fraction of clients that are free riders. Also test `0.20`, `0.40` |
| `attack_type` | `"FR1"` | One of `"FR1"`, `"FR2"`, `"FR3"`, `"FR4"` — see Section 4. Exactly one attack type active per run |
| `local_epochs` (E) | `3` | Local training epochs per client per round |
| `batch_size` | `32` | Local training batch size |
| `optimizer` | `"sgd"` | `"sgd"` or `"adam"` |
| `learning_rate` | `0.01` | Local optimizer learning rate |
| `momentum` | `0.9` | Only used if `optimizer == "sgd"` |
| `warmup_rounds` (n_w) | `10` | Rounds before trap selection activates; passive update detection still runs |
| `trap_fraction` (rho) | `0.10` | Base group size for the initial double-coverage sweep |
| `coverage_checks_per_client` | `2` | Coverage observations per client; `2` enables balanced double checking, while `1` retains the original single sweep |
| `candidate_confirmation_flags` | `2` | Joint norm/profile failures required to enter S; any single-signal anomaly enters C |
| `anchors_per_suspicion_group` | `3` | Maximum low-suspicion anchors assigned to each suspicious group |
| `max_suspicion_anchors` | `10` | Maximum total anchors excluded in one round |
| `surveillance_groups` | `10` | Fixed number of groups in every post-initial unflagged sweep |
| `penalty_zero_update` | `5` | Penalty for near-zero delta (static replay / no training) |
| `penalty_trap_flag` | `2` | Penalty for a joint norm/profile failure in an initial coverage probe |
| `penalty_normal_flag` | `1` | Penalty for a joint failure in one-check surveillance |
| `penalty_suspicion_flag` | `3` | Penalty for an anchor-relative joint failure |
| `removal_threshold_points` | `15` | Fixed cumulative penalty required for removal |
| `dodge_min_probes` | `10` | Minimum frequent-suspicion probes before rehabilitation |
| `dodge_max_flag_rate` | `0.10` | Maximum per-episode trap-flag rate allowed for rehabilitation |
| `zero_update_epsilon` | `1e-6` | Numerical tolerance for "delta ≈ 0" check (L2 norm below this counts as zero) |
| `magnitude_z_threshold` | `3.0` | Two-sided robust norm z-score boundary used for every attack |
| `mad_floor` | `0.05` | Real minimum MAD scale, preventing small-batch threshold collapse |
| `profile_z_threshold` | `3.0` | High-sided robust z-score boundary for layer-profile distance |
| `profile_mad_floor` | `0.01` | Minimum MAD scale for layer-profile distances |
| `fr2_update_range` | `1e-3` | Half-width of the bounded uniform random update used by FR2 |
| `fr3_window` | `5` | Maximum number of received models averaged by FR3 |
| `fr4_history_size` | `5` | Maximum number of received-model deltas averaged by FR4 |
| `fr4_noise_fraction` | `0.1` | FR4 noise norm as a fraction of its predicted update norm |
| `fr4_cold_start_scale` | `1e-4` | FR4 Gaussian update scale before a historical delta exists |
| `full_participation` | `true` | All active clients train every round (no dropout simulated) — see Section 3.1 |
| `seed` | `42` | Global random seed |
| `output_dir` | `"./results/"` | Where all CSV/log outputs are written |
| `run_name` | auto-generated | e.g. `"{dataset}_{distribution}_{attack_type}_fr{free_rider_pct}_{timestamp}"`, used as subfolder / filename prefix |
| `save_checkpoints` | `true` | Save a complete recovery checkpoint after every round |
| `checkpoint_keep_last` | `5` | While running, retain only the newest numbered checkpoints; delete all recovery checkpoints after success |

---

## 3. System Model

### 3.1 Participation Model
Every active client trains every round (`full_participation = true`). There is no
random per-round training-sample subset — this differs from standard FedAvg papers
that use a participation rate `C`, and is a deliberate simplification since this is
a simulation with no real device dropout. The **only** subset selected each round is
the trap subset `T_t` (Section 3.3), which is drawn from the full active pool.

### 3.2 Roles per Round
Each active client in round `t` is either:
- **Trapped** (`i ∈ T_t`): receives the corrupted/trap model, its update is
  **excluded from aggregation** regardless of outcome, but is still checked for flags.
- **Candidate** (`i ∈ C`): quarantined after a one-signal or joint anomaly; its update is
  excluded until its confirmation result is resolved.
- **Normal**: receives the true global model and is aggregated when it is not
  simultaneously selected for a trap or held in C.

### 3.3 Phases

**Phase 0 — Warm-Up (rounds 1 to `warmup_rounds`)**
No trapping. Only exact-zero/send-back detection is active; nonzero magnitude
and layer-profile checks do not run and cannot create candidates. The five-point
send-back penalty applies from round one.

**Phase 1 — Coverage Sweep (immediately after warm-up)**
- Generate two distinct trap models from the same global base at the beginning
  of the initial sweep and freeze each model for its complete pass.
- Partition all currently active clients into consecutive groups of size
  `m = ceil(rho * |active_clients|)`.
- Trap two distinct groups per round. In the first randomized pass every client
  receives trap A once; in the second randomized pass every client receives trap
  B once. Avoid repeating a group-pair where possible.
- Store each trapped response without flagging or penalizing it immediately.
- After the final pair responds, compute norm and layer-profile median/MAD
  baselines separately for the complete trap-A and trap-B passes. Either signal
  alone creates candidate evidence without points; only a joint failure earns
  `penalty_trap_flag`. Every zero update applies five points.
- Each trap pass's median delta is used as its diagnostic reference vector.
- When the queue of groups is exhausted, transition to Phase 2.

**Phase 2 — Suspicion-Flagged Sweep (ongoing)**
- Maintain unflagged (`U`), candidate (`C`), and suspicious (`S`) pools.
- Any one-signal or joint anomaly moves U to quarantined C. Confirm C on fresh
  group traps against never-flagged anchors: two joint failures move it to S; a
  fully normal response returns it to U and clears the current magnitude episode.
  An exact send-back moves it directly to S.
- Build `X = max(1, floor(|S| / 10))` groups when `S` is non-empty. Every
  suspicious client is included, so group size is not capped at ten.
- Select at most ten never-flagged anchors for each ten-round cycle and assign up
  to three per suspicious/confirmation group. A candidate or any client with a
  prior flag can never anchor. Shuffle suspects and anchors among groups every round.
- Give every suspicious group its own fresh trap model. Compare suspect update
  norms and layer profiles with baselines from that group's anchors. A joint
  failure adds three points; either signal alone adds none. An exact send-back adds five and a zero-update anchor
  is excluded from the magnitude baseline.
- Independently partition non-anchor `U` clients into exactly ten surveillance
  groups. Probe one group per round with a frozen model shared across that whole
  ten-round sweep, exclude it from aggregation, and evaluate the sweep together.
- A surveillance anomaly moves the client to C; only a joint failure adds one point.
- After ten episode probes, a C or S client with at most a ten-percent joint-
  failure rate returns to U. Its magnitude episode is cleared while exact-zero
  evidence remains.
- When `S` is empty, continue ten-group single-check surveillance sweeps. The
  initial double-coverage sweep is not repeated.

---

## 4. Free-Rider Attack Types (implement all four, select one per run via `attack_type`)

- **`FR1` (Static Replay):** client returns the last model it received without
  training. On its first participation it returns the current received model.
- **`FR2` (Bounded Random Update):** client adds an independently sampled update
  from `Uniform(-fr2_update_range, fr2_update_range)` to every floating-point
  parameter of the currently received model. It is memoryless and uses no
  privileged information.
- **`FR3` (Sliding-Window Average):** client maintains a buffer of up to its last
  `fr3_window` received models and returns their element-wise average.
- **`FR4` (Distribution-Aware Adaptive):** client records differences between
  consecutive models it receives, averages up to `fr4_history_size` recent
  differences, and adds isotropic noise whose norm is
  `fr4_noise_fraction` of that predicted update norm. Before one difference is
  available, it adds Gaussian noise scaled by `fr4_cold_start_scale`.

All attackers have only client-observable information: client identity, round,
the current received model, models previously sent to that same client, public
configuration, and local randomness. The server never discloses whether a model
is a trap. Consequently, every received model enters FR1/FR3/FR4 history under
the same rules, including a secret trap model.

Free riders are assigned once at the start of the run: `ceil(free_rider_pct * N)`
clients are randomly selected and flagged internally as free riders (ground truth,
used only for evaluation metrics, never exposed to the detection logic).

---

## 5. Per-Round Detection Logic (applies to checked clients)

1. **Zero-update check:** if `||delta|| < zero_update_epsilon`, add
  `penalty_zero_update` to that client's `P_i`. This applies during warm-up as
  well as coverage and suspicion. Skip the cosine diagnostic.
2. **Robust norm-z check** (only if step 1 did not trigger): during coverage or
  surveillance, compute the complete sweep's norm median/MAD and apply the
  configured two-sided robust-z boundary. During frequent suspicion probing, use
  only the two or three anchors that received the same trap, and flag the
  suspect when `abs((norm - anchor_median) / max(anchor_MAD, mad_floor))`
  exceeds `magnitude_z_threshold`.
3. **Layer-profile check:** normalize the per-parameter-tensor update norms to
   sum to one, measure distance from the phase median profile, and robustly score
   that distance. One failed signal creates C evidence without a penalty. Both
   norm and profile must fail on the same response to earn the phase penalty.
4. **Cosine diagnostic:** compute cosine similarity against the phase reference
  and write it to client metrics. It is currently not used to flag or
  penalize a client.
5. **Rehabilitation:** after at least ten episode probes, return C or S to U when
   its joint-failure rate is at most ten percent. Clear current magnitude points,
   preserve exact-zero points, and reset episode counters.
6. **Removal check:** three accumulated exact send-backs remove immediately.
   Nonzero joint evidence additionally requires at least ten completed S-state
   probes before `P_i >= 15` can remove the client. A qualifying low joint-rate
   rehabilitation takes precedence over nonzero-evidence removal. Log the event.
7. **Aggregation:** global model for round `t+1` = mean of deltas from all
   clients that are neither trapped nor quarantined candidates in round `t`.
   A candidate clearing response is still excluded in its confirmation round;
   ordinary aggregation resumes in the next round.

Client-local loss and accuracy may be recorded by the simulator for evaluation,
but they are not detector inputs and cannot change suspicion or penalties.

---

## 6. Models

Keep architectures simple and swappable via a `get_model(dataset_name)` factory
function.

- **MNIST:** small CNN — e.g. 2 conv layers (16, 32 filters, 3x3, ReLU, maxpool)
  followed by 2 fully connected layers ending in a 10-way softmax.
- **CIFAR-10:** slightly deeper CNN — e.g. 3 conv blocks (32, 64, 128 filters,
  3x3, ReLU, batchnorm, maxpool) followed by 2 fully connected layers ending in a
  10-way softmax.

Both should be defined as standard `torch.nn.Module` subclasses so they can later
be swapped for other architectures without touching the training loop.

---

## 7. Data Partitioning

- **IID:** shuffle the full training set, split into `num_clients` equal shards.
- **Non-IID:** Dirichlet-based partitioning using `dirichlet_alpha` — for each
  class, draw a proportion vector over clients from `Dirichlet(alpha)` and assign
  samples of that class accordingly, so lower `alpha` produces more label-skewed
  clients.

---

## 8. Required Outputs (all under `output_dir/run_name/`)

1. **`trap_matrix.csv`** — rows = rounds (1..T), columns = client IDs (0..N-1).
   Cell value: `1` if that client was trapped that round, `0` otherwise. Include a
   `phase` column per row (`warmup`, `coverage`, `confirmation`, `suspicion`, or
   `surveillance`).
2. **`global_metrics.csv`** — one row per round: `round, global_accuracy,
   global_loss, num_active_clients, num_candidate_clients,
   num_suspected_clients, num_trapped, num_aggregated, round_time_seconds`.
3. **`client_metrics.csv`** — one row per (round, client): `round, client_id,
   is_free_rider (ground truth), was_trapped, local_accuracy, local_loss,
   cosine_similarity, delta_norm, norm_z_score, norm_median, norm_mad,
   profile_score, profile_z_score, magnitude_flag, profile_flag,
   joint_flag_count, detection_reason,
   flagged (bool), penalty_added_this_round`.
   Local accuracy/loss are simulator diagnostics only. Legacy loss-z fields may
   remain present but blank for compatibility and are not detector inputs.
4. **`penalty_tracker.csv`** — one row per (round, client), including cumulative
   penalty, C/S state, candidate-episode flags, exact-zero count, and lifetime
   flag/trap counts.
5. **`removals.csv`** — one row per removal event: `round, client_id,
   is_free_rider (ground truth), final_penalty, removal_basis,
   zero_update_count, suspicion_probes`.
6. **`run_config.csv`** (or `.json`, whichever is easier to generate) — a full dump
   of every config variable in Section 2 for that run, plus `run_name`, `seed`,
   `device`, start/end timestamp, and total wall-clock runtime.
7. **`candidate_events.csv`** — U-to-C entries, additional candidate evidence,
   C-to-S confirmations, and confirmation passes that return C to U.

All files for a given run should share a common `run_name` prefix or live in a
common per-run folder so multiple experiment configurations (different datasets,
distributions, free-rider percentages, attack types) don't overwrite each other.

---

## 9. Suggested Project Structure

```
project/
├── config.py            # Config dataclass, defaults from Section 2
├── data/
│   ├── loaders.py        # MNIST/CIFAR-10 loading
│   └── partition.py       # IID / Dirichlet Non-IID partitioning
├── models/
│   └── architectures.py  # get_model(dataset_name)
├── clients/
│   └── attacks.py         # FR1–FR4 implementations, applied per client per round
├── server/
│   ├── trap_selection.py  # Warmup, coverage, and suspicion-flagged trap queues
│   ├── detection.py       # zero-update and norm-outlier checks, penalty logic
│   └── aggregation.py     # FedAvg over non-trapped clients
├── train.py               # main training loop orchestrating the above
├── logging_utils.py       # CSV writers for Section 8 outputs
└── run_experiment.py      # entry point, reads config, calls train.py
```
---

## 10. Notes / Assumptions Carried Over From Design Discussion

- Detection never causes the whole round to be discarded. Trapped and candidate
  clients' updates are excluded; other active clients aggregate normally.
- Reference populations differ by phase: complete stored responses during
  coverage/surveillance and same-model anchors during frequent suspicion.
  Cosine similarity remains diagnostic only.
- `P_max` is a fixed 15 evidence points, independent of experiment length.
- Ground-truth free-rider labels must be tracked internally for evaluation
  metrics (precision/recall/F1 of detection, false-positive removal rate) but must
  never be accessible to the detection/trap-selection logic itself — the whole
  point is that detection works without knowing this in advance.
