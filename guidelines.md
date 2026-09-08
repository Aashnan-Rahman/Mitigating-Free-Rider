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
| `trap_fraction` (rho) | `0.10` | Fraction of *currently active* clients trapped per round, in both phases |
| `num_anchors` (a_h) | `3` | Confirmed-honest clients placed in every Suspicion-Weighted trap subset |
| `epsilon` | `1.0` | Baseline sampling weight so a clean client (P=0) still has non-zero trap probability |
| `penalty_zero_update` | `4` | Penalty for near-zero delta (static replay / no training) |
| `penalty_trap_flag` | `2` | Penalty for a magnitude-based flag while trapped |
| `penalty_normal_flag` | `1` | Penalty for a magnitude-based flag while not trapped |
| `removal_threshold_pct` | `0.10` | `P_max = ceil(removal_threshold_pct * num_rounds)` — scales automatically with T |
| `reset_flag_threshold` | `1` | If new flags in a 10-round window ≤ this, for `reset_window_count` consecutive windows, trigger a fresh Coverage Sweep |
| `reset_window_size` | `10` | Size (in rounds) of each monitoring window used for the reset trigger |
| `reset_window_count` | `2` | Consecutive quiet windows required to trigger reset |
| `zero_update_epsilon` | `1e-6` | Numerical tolerance for "delta ≈ 0" check (L2 norm below this counts as zero) |
| `magnitude_z_threshold` | `3.0` | Upper robust norm z-score threshold used for FR2 |
| `mad_floor` | `0.05` | Real minimum MAD scale, preventing small-batch threshold collapse |
| `mad_min_samples` | `5` | Minimum reference sample count for robust threshold estimation |
| `penalty_decay` | `1` | Penalty removed after each passed detection check, capped at the current penalty |
| `use_loss_check` | `true` | Enable the early-round FR3 loss detector |
| `loss_check_rounds` | `6` | Last round in which the loss detector is active |
| `loss_mad_floor` | `0.05` | Minimum MAD scale for robust loss z-scores |
| `loss_z_threshold` | `2.0` | High-loss z-score required by the FR3 combined rule |
| `loss_norm_z_threshold` | `-2.0` | Maximum robust norm z-score for the combined FR3 loss signal |
| `full_participation` | `true` | All active clients train every round (no dropout simulated) — see Section 3.1 |
| `seed` | `42` | Global random seed |
| `output_dir` | `"./results/"` | Where all CSV/log outputs are written |
| `run_name` | auto-generated | e.g. `"{dataset}_{distribution}_{attack_type}_fr{free_rider_pct}_{timestamp}"`, used as subfolder / filename prefix |

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
- **Normal**: receives the true global model, trains normally, and its update is
  aggregated unless `fedavg_skip_penalty_threshold` is configured and its
  cumulative penalty exceeds that threshold.

### 3.3 Phases

**Phase 0 — Warm-Up (rounds 1 to `warmup_rounds`)**
No trapping. Standard FedAvg over all active clients. Passive norm-z/MAD
detection and penalties remain active so rounds 1–6 can supply the only reliable
FR3 loss signal; "warm-up" applies to trap selection, not anomaly observation.

**Phase 1 — Coverage Sweep (immediately after warm-up)**
- Generate one trap model at the beginning of the sweep and freeze its exact
  weights until the sweep finishes. A later coverage sweep generates a new one.
- Partition all currently active clients into consecutive groups of size
  `m = ceil(rho * |active_clients|)`.
- Trap exactly one group per round until every active client has been trapped
  exactly once in this sweep.
- Store each trapped response without flagging or penalizing it immediately.
- After the final group responds, compute the norm and loss median/MAD over the
  complete sweep and apply flags and penalties together.
- The complete sweep's median delta is used as the diagnostic reference vector.
- When the queue of groups is exhausted, transition to Phase 2.

**Phase 2 — Suspicion-Flagged Sweep (ongoing)**
- Each round, build a trap subset `T_t` of size
  `m = ceil(rho * |active_clients|)`.
- Previously penalized or flagged clients are ordered by cumulative penalty and
  flag count, then grouped as suspects.
- Up to `num_anchors` clients without prior penalties are added as anchors. The
  remaining slots are filled from active clients if necessary.
- The anchor mean is used as the diagnostic reference vector when anchors are
  available.
- The implementation alternates suspicion-flagged groups with coverage groups.

---

## 4. Free-Rider Attack Types (implement all four, select one per run via `attack_type`)

- **`FR1` (Static Replay):** client ignores whatever it received this round and
  returns the last model it legitimately held (i.e. simply does not update its
  local copy).
- **`FR2` (Bounded Random Noise):** client returns a tensor of random weights
  matching the model's shape, sampled within a plausible magnitude range (e.g.
  uniform or normal scaled to match the empirical parameter std of the received
  model). If a generated tensor's shape doesn't match the model architecture,
  resample.
- **`FR3` (Sliding-Window Average):** client maintains a buffer of its last 5
  received global models and returns their average, regardless of what it
  actually received this round.
- **`FR4` (Distribution-Aware Adaptive):** client estimates the expected norm and
  direction of a genuine update (e.g. from its own history of past legitimate
  updates, or from the global model's trajectory across rounds) and fabricates a
  noise vector calibrated to match those statistics, rather than fabricating
  blindly.

Free riders are assigned once at the start of the run: `ceil(free_rider_pct * N)`
clients are randomly selected and flagged internally as free riders (ground truth,
used only for evaluation metrics, never exposed to the detection logic).

---

## 5. Per-Round Detection Logic (applies to checked clients)

1. **Zero-update check:** if `||delta|| < zero_update_epsilon`, add
  `penalty_zero_update` to that client's `P_i`. Skip the cosine diagnostic.
2. **Robust norm-z check** (only if step 1 did not trigger): compute the batch
  norm median and MAD, use `max(MAD, mad_floor)` as the scale, and calculate
  `norm_z = (delta_norm - median_norm) / scale`. If
  `norm_z > magnitude_z_threshold`, flag the client as an FR2-style large-norm
  outlier:
  - if client was trapped this round: add `penalty_trap_flag`
  - otherwise: add `penalty_normal_flag`
3. **Cosine diagnostic:** compute cosine similarity against the phase reference
  and write it to client metrics. It is currently not used to flag or
  penalize a client.
4. **Early loss check:** compute
  `loss_z = (loss - median_loss) / max(loss_MAD, loss_mad_floor)` without a
  percentile. During observations made at `round <= loss_check_rounds`, flag
  only when `loss_z > loss_z_threshold` AND
  `norm_z_score < loss_norm_z_threshold`. This AND rule is intentionally limited to
  early rounds because FR3 loss overlaps honest loss after convergence begins.
  A consistent early flag receives
  `ceil(removal_threshold / loss_check_rounds)` penalty points so the finite
  six-round signal can reach the removal threshold.
5. **Penalty decay:** after a passed detection check, subtract
  `penalty_decay` from `P_i`, without allowing it to become negative.
6. **Removal check:** if `P_i >= P_max` (where
   `P_max = ceil(removal_threshold_pct * num_rounds)`), remove client from the
   active pool permanently starting next round. Log the removal event.
7. **Aggregation:** global model for round `t+1` = mean of deltas from all
   **non-trapped** clients in round `t` (trapped clients' updates are never
   aggregated, regardless of whether they were flagged).

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
   `phase` column per row (`warmup` / `coverage` / `suspicion`).
2. **`global_metrics.csv`** — one row per round: `round, global_accuracy,
   global_loss, num_active_clients, num_trapped, num_aggregated, round_time_seconds`.
3. **`client_metrics.csv`** — one row per (round, client): `round, client_id,
   is_free_rider (ground truth), was_trapped, local_accuracy, local_loss,
   cosine_similarity, delta_norm, norm_z_score, norm_median, norm_mad, detection_reason,
   flagged (bool), penalty_added_this_round`.
4. **`penalty_tracker.csv`** — one row per (round, client): `round, client_id,
   cumulative_penalty, times_flagged_so_far, times_trapped_so_far`.
5. **`removals.csv`** — one row per removal event: `round, client_id,
   is_free_rider (ground truth), final_penalty`.
6. **`run_config.csv`** (or `.json`, whichever is easier to generate) — a full dump
   of every config variable in Section 2 for that run, plus `run_name`, `seed`,
   `device`, start/end timestamp, and total wall-clock runtime.

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
l
---

## 10. Notes / Assumptions Carried Over From Design Discussion

- Detection never causes the whole round to be discarded — only trapped clients'
  updates are excluded; all other active clients' updates aggregate normally
  every round.
- Reference vectors differ by phase: trapped-group mean during Coverage and
  anchor mean during Suspicion-Flagged. Cosine similarity is logged as a
  diagnostic and is not currently used for flagging.
- `P_max` scales automatically with `num_rounds` via `removal_threshold_pct`, so
  switching between `num_rounds=100` and `num_rounds=200` does not require manually
  recalculating the removal threshold.
- Ground-truth free-rider labels must be tracked internally for evaluation
  metrics (precision/recall/F1 of detection, false-positive removal rate) but must
  never be accessible to the detection/trap-selection logic itself — the whole
  point is that detection works without knowing this in advance.
