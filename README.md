# SWT-CP Free-Rider Federated Learning Simulator

This repository implements the `guidelines.md` specification for Suspicion-Weighted
Trap Detection with Cumulative Penalty.

For complete individual-run, four-attack scheduling, monitoring, timing, CUDA,
checkpoint, and resume commands, see [`RUN_GUIDE.md`](RUN_GUIDE.md).

## Run

```powershell
python run_experiment.py
```

Use JSON config files or CLI overrides to run experiment variants:

```powershell
python run_experiment.py --set attack_type='"FR2"' --set free_rider_pct=0.2
python run_experiment.py --config configs/example.json
```

Quick data-flow check:

```powershell
python run_experiment.py --smoke
```

Run the configured 16-experiment 40% matrix and monitor it from another terminal:

```powershell
python run_experiments.py
python monitor.py --watch
```

See `experiment_plan.md` and `configs/experiment_plan.json` for the enabled
MNIST/CIFAR-10 IID/non-IID matrix and the disabled percentage sweep.

Or open `experiment_notebook.ipynb` in Jupyter/VS Code and edit the parameters
in Section 2.

Outputs are written under `output_dir/run_name/`:

- `trap_matrix.csv`
- `trap_assignments.csv`
- `global_metrics.csv`
- `client_metrics.csv`
- `penalty_tracker.csv`
- `removals.csv`
- `rehabilitations.csv`, `candidate_events.csv`, and `dodge_tracker.csv`
- `latest_results.json`
- during active/interrupted runs, `latest_checkpoint.pt` and the five newest
  numbered `checkpoint_round_XXXX.pt` files
- `run_config.json`
- `detection_summary.csv`
- `round_detection_metrics.csv` and `detection_events.csv`
- `client_detection_summary.csv`
- `norm_z_matrix.csv`, `profile_z_matrix.csv`, `loss_z_matrix.csv`,
  `delta_norm_matrix.csv`, `flag_matrix.csv`, and `joint_flag_matrix.csv`

Each completed round rewrites the CSV/JSON snapshots and, when enabled, saves a
checkpoint containing the model state, active clients, penalties, flag/trap counts,
ground-truth free-rider IDs, and that round's global metrics. See
`experiment_checklist.md` for the staged experiment plan and stopping criteria.
Checkpointing occurs every round. Older numbered snapshots are deleted
automatically according to `checkpoint_keep_last` (default five), and
`latest_checkpoint.pt` is a portable copy of the newest snapshot. All recovery
checkpoints are deleted after successful completion; failed or interrupted runs
retain them for resume.

The trap model perturbation is configurable through `trap_noise_scale` and
`trap_noise_floor`; all detection and attack hyperparameters are centralized in
`config.py`. During secret-trap phases, detection combines a two-sided robust
update-norm z-score with a scale-free profile of how update norm is distributed
across parameter tensors. A single abnormal signal quarantines the client for
confirmation but earns no magnitude penalty; only simultaneous norm and profile
failure earns one. Responses are compared only with responses generated from the
same frozen or group-specific model. Cosine similarity is diagnostic only. The
warm-up performs only the exact send-back check. Local loss and accuracy are
simulation diagnostics and are never detector inputs.

The initial coverage sweep uses two distinct frozen trap models generated from
the same base model. Two groups are probed per round; every client receives each
trap exactly once, with separately calibrated median/MAD baselines. Decisions
are deferred until the complete double sweep is available. Any single-signal
anomaly creates a quarantined candidate. Repeated joint norm/profile evidence
moves it into frequent suspicion probing; a fully normal confirmation clears it.
Later unflagged surveillance uses ten groups and one check per client. Candidate
clearance and rehabilitation erase only the current magnitude episode, while
exact-zero evidence remains permanent and three exact send-backs still remove.

See [`VERSION_HISTORY.md`](VERSION_HISTORY.md) for the v4-v7 methodology and
result provenance.
