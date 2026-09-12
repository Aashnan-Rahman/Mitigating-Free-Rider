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
- `norm_z_matrix.csv`, `loss_z_matrix.csv`, `delta_norm_matrix.csv`, `flag_matrix.csv`

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
`config.py`. Detection computes a robust update-norm z-score using the batch
median and `max(MAD, mad_floor)`. During trap phases, responses are compared
only with responses generated from the same frozen or group-specific model. No
percentile is used. Cosine similarity is logged only as a
diagnostic and never flags or penalizes a client. Automatic penalty decay is
disabled; repeated suspicion checks use a dodge-index rehabilitation rule. An
exact send-back check remains active during trap-selection warmup. Local loss and
accuracy are simulation diagnostics only; neither is trusted by, or supplied to,
the detector.

The initial coverage sweep uses two distinct frozen trap models generated from
the same base model. Two groups are probed per round; every client receives each
trap exactly once, with separately calibrated median/MAD baselines. Decisions
are deferred until the complete double sweep is available. A single magnitude
flag creates a quarantined candidate that must pass or fail an anchor-referenced
confirmation before returning to the unflagged pool or entering frequent
suspicion probing. Later unflagged surveillance uses ten groups and one check per
client. Magnitude-only removal requires at least ten suspicion probes, while
three exact send-backs still remove immediately.
