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
| `warmup_rounds` (n_w) | `10` | Rounds before any detection logic activates |
| `trap_fraction` (rho) | `0.10` | Fraction of *currently active* clients trapped per round, in both phases |
| `num_anchors` (a_h) | `3` | Confirmed-honest clients placed in every Suspicion-Weighted trap subset |
| `epsilon` | `1.0` | Baseline sampling weight so a clean client (P=0) still has non-zero trap probability |
| `similarity_threshold` (tau) | `0.5` | Fixed cosine similarity threshold. Below this = flagged |
| `penalty_zero_update` | `4` | Penalty for near-zero delta (static replay / no training) |
| `penalty_trap_flag` | `2` | Penalty for failing similarity check while trapped |
| `penalty_normal_flag` | `1` | Penalty for failing similarity check while not trapped |
| `removal_threshold_pct` | `0.10` | `P_max = ceil(removal_threshold_pct * num_rounds)` — scales automatically with T |
| `reset_flag_threshold` | `1` | If new flags in a 10-round window ≤ this, for `reset_window_count` consecutive windows, trigger a fresh Coverage Sweep |
| `reset_window_size` | `10` | Size (in rounds) of each monitoring window used for the reset trigger |
| `reset_window_count` | `2` | Consecutive quiet windows required to trigger reset |
| `zero_update_epsilon` | `1e-6` | Numerical tolerance for "delta ≈ 0" check (L2 norm below this counts as zero) |
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
- **Normal**: receives the true global model, trains normally, its update **is
  aggregated** (unless it fails a check — Section 5).

### 3.3 Phases

**Phase 0 — Warm-Up (rounds 1 to `warmup_rounds`)**
No trapping. Standard FedAvg over all active clients. No penalties assigned.

**Phase 1 — Coverage Sweep (immediately after warm-up, and re-triggered later)**
- Partition all currently active clients into consecutive groups of size
  `m = ceil(rho * |active_clients|)`.
- Trap exactly one group per round until every active client has been trapped
  exactly once in this sweep.
- Reference vector for the similarity check in this phase = **coordinate-wise
  median** of the trapped group's deltas (robust statistic — composition is not
  yet known to be trustworthy).
- When the queue of groups is exhausted, transition to Phase 2.

**Phase 2 — Suspicion-Weighted Sweep (ongoing, until reset trigger)**
- Each round, build the trap subset `T_t` of size `m = ceil(rho * |active_clients|)`:
  1. Draw `m - num_anchors` clients **without replacement**, weighted by
     `P_i + epsilon` (so higher-penalty clients are more likely, but every client
     has non-zero probability).
  2. Draw `num_anchors` clients from those with the **lowest current `P_i`**
     (ties broken randomly; prefer never-flagged clients).
  3. `T_t` = union of the two draws.
- Reference vector for the similarity check in this phase = **mean of the
  `num_anchors` anchors' deltas** (not the median — anchors are known-honest, no
  need for a robust statistic here).
- Track `F_k`: number of new flags issued in each `reset_window_size`-round
  window. If `F_k ≤ reset_flag_threshold` for `reset_window_count` consecutive
  windows, transition back to **Phase 1** (fresh Coverage Sweep over the current
  active population).

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

## 5. Per-Round Detection Logic (applies to every client, trapped or not)

1. **Zero-update check:** if `||delta|| < zero_update_epsilon`, add
   `penalty_zero_update` to that client's `P_i`. Skip similarity check.
2. **Cosine similarity check** (only if step 1 did not trigger): compute
   `sim(delta_i, reference_vector)`. If `sim < similarity_threshold`:
   - if client was trapped this round: add `penalty_trap_flag`
   - else: add `penalty_normal_flag`
3. **Removal check:** if `P_i > P_max` (where
   `P_max = ceil(removal_threshold_pct * num_rounds)`), remove client from the
   active pool permanently starting next round. Log the removal event.
4. **Aggregation:** global model for round `t+1` = mean of deltas from all
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
   cosine_similarity, delta_norm, flagged (bool), penalty_added_this_round`.
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
│   ├── trap_selection.py  # Phase 0/1/2 logic, coverage queue, weighted sampling
│   ├── detection.py       # zero-update check, cosine similarity, penalty logic
│   └── aggregation.py     # FedAvg over non-trapped clients
├── train.py               # main training loop orchestrating the above
├── logging_utils.py       # CSV writers for Section 8 outputs
└── run_experiment.py      # entry point, reads config, calls train.py
```

---

## 10. Notes / Assumptions Carried Over From Design Discussion

- Detection never causes the whole round to be discarded — only trapped clients'
  updates are excluded; all other active clients' updates aggregate normally
  every round.
- The reference vector computation method differs by phase (median in Coverage
  Sweep, anchor-mean in Suspicion-Weighted) — this is intentional, not an
  inconsistency, see Section 3.3.
- `P_max` scales automatically with `num_rounds` via `removal_threshold_pct`, so
  switching between `num_rounds=100` and `num_rounds=200` does not require manually
  recalculating the removal threshold.
- Ground-truth free-rider labels must be tracked internally for evaluation
  metrics (precision/recall/F1 of detection, false-positive removal rate) but must
  never be accessible to the detection/trap-selection logic itself — the whole
  point is that detection works without knowing this in advance.