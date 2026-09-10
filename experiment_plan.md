# Experiment Execution Plan

The machine-readable plan is `configs/experiment_plan.json`. Experiments run
sequentially so CPU/GPU memory and timing measurements are attributable to one
run at a time.

## Enabled 40% experiments (16)

| Stage | Dataset | Distribution | Attacks | Runs |
|---|---|---|---|---:|
| 1 | MNIST | IID | FR1, FR2, FR3, FR4 | 4 |
| 2 | MNIST | non-IID | FR1, FR2, FR3, FR4 | 4 |
| 3 | CIFAR-10 | IID | FR1, FR2, FR3, FR4 | 4 |
| 4 | CIFAR-10 | non-IID | FR1, FR2, FR3, FR4 | 4 |

All use 100 clients, 100 rounds, 40% free riders, seed 42, automatic CUDA/CPU
selection, and checkpoints every five rounds by default.

## Percentage experiments (disabled initially)

Stage 5 contains MNIST and CIFAR-10, IID and non-IID, FR1-FR4, at 10%, 20%,
and 40% free riders: 48 matrix entries. It is disabled so results from the
initial 40% experiments can be reviewed first. Set its `enabled` field to `true`
or run with `--include-disabled`.

## Commands

```powershell
python run_experiments.py
python monitor.py --watch
```

To include the percentage matrix:

```powershell
python run_experiments.py --include-disabled
```

## Batch metadata

The runner creates a timestamped directory below `results/`, containing:

- `experiment_manifest.json`: expanded configurations before execution.
- `experiment_status.json`: live batch and current-round state.
- `batch_summary.json`: final status and per-experiment summaries.
- One directory per experiment containing all existing and new run artifacts.

`results/experiment_status.json` always points to the latest batch state and is
the default file read by `monitor.py`.

## Per-experiment records

- Existing trap, global, client, penalty, removal, checkpoint, and run-config
  records are retained.
- `round_detection_metrics.csv`: TP, FP, TN, FN, accuracy, precision, recall,
  F1, and removals for every decision round.
- `detection_events.csv`: when and why each client was flagged.
- `client_detection_summary.csv`: first flag/removal rounds and final status.
- `norm_z_matrix.csv`, legacy-empty `loss_z_matrix.csv`, `delta_norm_matrix.csv`, and
  `flag_matrix.csv`: client-by-round matrices.
- `global_metrics.csv`: wall time, process CPU time, RSS/system memory,
  process CPU percentage, and CUDA allocated/reserved/peak memory per round.
- `run_config.json`: complete settings, hardware information, total duration,
  and final detection metrics.

Ground-truth labels are used only to calculate evaluation metrics after detector
decisions. They are never passed into the detector.
