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

Each completed round rewrites the CSV/JSON snapshots and, when enabled, saves a
checkpoint containing the model state, active clients, penalties, flag/trap counts,
ground-truth free-rider IDs, and that round's global metrics. See
`experiment_checklist.md` for the staged experiment plan and stopping criteria.

The trap model perturbation is configurable through `trap_noise_scale` and
`trap_noise_floor`; all detection and attack hyperparameters are centralized in
`config.py`.
