# SWT-CP Free-Rider Federated Learning Simulator

This repository implements the `guidelines.md` specification for Suspicion-Weighted
Trap Detection with Cumulative Penalty.

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
- `global_metrics.csv`
- `client_metrics.csv`
- `penalty_tracker.csv`
- `removals.csv`
- `latest_results.json`
- `latest_checkpoint.pt` and numbered `checkpoint_round_XXXX.pt` files
- `run_config.json`
- `detection_summary.csv`
- `round_detection_metrics.csv` and `detection_events.csv`
- `client_detection_summary.csv`
- `norm_z_matrix.csv`, `loss_z_matrix.csv`, `delta_norm_matrix.csv`, `flag_matrix.csv`

Each completed round rewrites the CSV/JSON snapshots and, when enabled, saves a
checkpoint containing the model state, active clients, penalties, flag/trap counts,
ground-truth free-rider IDs, and that round's global metrics. See
`experiment_checklist.md` for the staged experiment plan and stopping criteria.

The trap model perturbation is configurable through `trap_noise_scale` and
`trap_noise_floor`; all detection and attack hyperparameters are centralized in
`config.py`. Detection computes a robust update-norm z-score using the batch
median and `max(MAD, mad_floor)`. Large positive z-scores detect FR2; during
rounds 1–6, a robust high loss z-score combined with a negative norm z-score
detects FR3. No percentile is used.
Cosine similarity is logged only as a
diagnostic and never flags or penalizes a client. Penalty decay defaults to one
point per passed check. An optional early-round loss detector can be enabled with
`use_loss_check=true`; it defaults on, requires a low norm z-score, and is limited
to the empirically separable FR3 loss window (rounds 1–6). Detection runs during
trap-selection warmup so that window is not discarded.

Each coverage sweep uses one exact frozen trap model for every group and defers
coverage flags until all clients in that sweep have responded. A new frozen trap
model is generated for the next coverage sweep.
