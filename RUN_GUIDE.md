
# SWT-CP Experiment Run Guide

Run every command in PowerShell from the repository root:

```powershell
cd "E:\New Projects\Mitigating-Free-Rider"
.\.venv\Scripts\Activate.ps1
```

The project environment contains the CUDA-enabled PyTorch installation. If PowerShell
does not allow activation scripts, run the commands with the environment's Python
directly, for example `.\.venv\Scripts\python.exe -m pytest -q`.

## 1. Before a long run

Activate the Python environment containing PyTorch and the project dependencies,
then confirm whether PyTorch can actually use CUDA:

```powershell
python -c "import torch; print('PyTorch:', torch.__version__); print('CUDA available:', torch.cuda.is_available()); print('CUDA device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU only')"
```

If this prints `CUDA available: False`, `device=auto` will run on the CPU. Fix the
PyTorch/CUDA installation before launching a long experiment if GPU execution is
required.

Run the automated checks on the execution laptop:

```powershell
python -m pytest -q
```

Optional short data-flow check:

```powershell
python run_experiment.py --smoke --set device=auto --set run_name=smoke_check
```

Do not reuse a `run_name` containing results that must be preserved. A repeated
name writes into the same result directory.

## 2. Run FR1, FR2, FR3, or FR4 individually

The following commands run 100 clients for 100 rounds on MNIST non-IID with a
Dirichlet alpha of 0.5, 40% free riders, seed 42, and automatic CUDA/CPU
selection. Their output directories are kept separate from scheduled batch output.

### FR1

```powershell
python run_experiment.py --set dataset=mnist --set distribution=noniid --set dirichlet_alpha=0.5 --set free_rider_pct=0.4 --set attack_type=FR1 --set num_clients=100 --set num_rounds=100 --set seed=42 --set device=auto --set output_dir=results/manual_mnist_noniid_fr40 --set run_name=FR1_swtcp_v8_noniid_fr40_seed42
```

### FR2

```powershell
python run_experiment.py --set dataset=mnist --set distribution=noniid --set dirichlet_alpha=0.5 --set free_rider_pct=0.4 --set attack_type=FR2 --set num_clients=100 --set num_rounds=100 --set seed=42 --set device=auto --set output_dir=results/manual_mnist_noniid_fr40 --set run_name=FR2_swtcp_v8_noniid_fr40_seed42
```

### FR3

```powershell
python run_experiment.py --set dataset=mnist --set distribution=noniid --set dirichlet_alpha=0.5 --set free_rider_pct=0.4 --set attack_type=FR3 --set num_clients=100 --set num_rounds=100 --set seed=42 --set device=auto --set output_dir=results/manual_mnist_noniid_fr40 --set run_name=FR3_swtcp_v8_noniid_fr40_seed42
```

### FR4

```powershell
python run_experiment.py --set dataset=mnist --set distribution=noniid --set dirichlet_alpha=0.5 --set free_rider_pct=0.4 --set attack_type=FR4 --set num_clients=100 --set num_rounds=100 --set seed=42 --set device=auto --set output_dir=results/manual_mnist_noniid_fr40 --set run_name=FR4_swtcp_v8_noniid_fr40_seed42
```

To require CUDA rather than silently falling back to CPU, replace
`--set device=auto` with `--set device=cuda`. The program will stop immediately
if CUDA is unavailable.

An individual run does not create the batch-level `experiment_status.json` used
by `monitor.py`. Its latest completed round can instead be read from:

```powershell
Get-Content results/manual_mnist_noniid_fr40/FR1_swtcp_v8_noniid_fr40_seed42/latest_results.json
```

Change `FR1_swtcp_v8_noniid_fr40_seed42` to the applicable individual run name.

## 3. Schedule FR1 → FR2 → FR3 → FR4 automatically

The v8 plan `configs/stage1_v8_plan.json` contains exactly four runs in
this order:

1. MNIST non-IID FR1, 40%, seed 42
2. MNIST non-IID FR2, 40%, seed 42
3. MNIST non-IID FR3, 40%, seed 42
4. MNIST non-IID FR4, 40%, seed 42

Start the sequence with:

```powershell
python run_experiments.py --plan configs/stage1_v8_plan.json --stop-on-error
```

The batch runner is sequential: it completes all 100 rounds of FR1 before FR2,
then FR3, and finally FR4. `--stop-on-error` prevents later experiments from
running if an earlier one fails. Omit it only when continuing after a failed run
is intentional.

The plan leaves `batch_name` as `null`, so the runner creates a fresh timestamped
batch directory and does not overwrite the earlier v4/v5 results. Do not launch
the same plan twice at exactly the same time.

## 4. Monitor the scheduled batch

Open a second PowerShell terminal in the repository root.

Show one status snapshot:

```powershell
python monitor.py
```

Continuously refresh until the batch finishes:

```powershell
python monitor.py --watch
```

Use a slower five-second refresh if preferred:

```powershell
python monitor.py --watch --interval 5
```

Monitor the batch-specific status file directly:

```powershell
$batchId = (Get-Content results/experiment_status.json | ConvertFrom-Json).batch_id
python monitor.py --status "results/$batchId/experiment_status.json" --watch
```

The monitor displays:

- which experiment is running or queued;
- current round and total rounds;
- current methodology phase;
- actual device (`cpu` or `cuda`);
- active-client count;
- candidate and suspicious-client counts;
- time taken by the latest round;
- global accuracy and loss;
- process memory and peak CUDA memory;
- estimated time remaining for the complete four-experiment batch.

The ETA is an estimate based on completed rounds. It becomes more useful after
several rounds and may change as clients are removed or different phases begin.
After an experiment finishes, its exact total and average-round times are stored
in that experiment's `run_config.json` as `total_wall_clock_seconds` and
`average_round_time_seconds`.

To estimate the running experiment by itself—elapsed time, average seconds per
round, remaining time, and estimated total time—use:

```powershell
$status = Get-Content results/experiment_status.json | ConvertFrom-Json
$current = $status.experiments | Where-Object id -eq $status.current_experiment
$elapsed = ([datetime]$status.updated_at - [datetime]$current.started_at).TotalSeconds
$round = [int]$current.progress.round
$totalRounds = [int]$current.progress.total_rounds
$average = if ($round -gt 0) { $elapsed / $round } else { 0 }
[pscustomobject]@{
    Experiment = $current.id
    Round = "$round/$totalRounds"
    Elapsed = [timespan]::FromSeconds($elapsed)
    AverageSecondsPerRound = [math]::Round($average, 2)
    EstimatedRemaining = [timespan]::FromSeconds($average * ($totalRounds - $round))
    EstimatedExperimentTotal = [timespan]::FromSeconds($average * $totalRounds)
}
```

For example, after FR1 completes:

```powershell
$batchId = (Get-Content results/experiment_status.json | ConvertFrom-Json).batch_id
$result = Get-Content "results/$batchId/stage1_v8_mnist_noniid_fr1_fr40/run_config.json" | ConvertFrom-Json
$result | Select-Object total_wall_clock_seconds, average_round_time_seconds, final_global_accuracy, removed_free_riders, removed_honest_clients
```

## 5. Check status without Python

The top-level batch status is ordinary JSON and can also be inspected directly:

```powershell
Get-Content results/experiment_status.json
```

Useful result locations are:

```text
results/experiment_status.json
results/<batch-id>/experiment_status.json
results/<batch-id>/experiment_manifest.json
results/<batch-id>/<experiment-id>/latest_results.json
results/<batch-id>/<experiment-id>/global_metrics.csv
results/<batch-id>/<experiment-id>/run_config.json
```

## 6. Checkpoints and interruption

To resume an interrupted or failed scheduled batch, pass its existing batch
directory. The runner skips experiments whose outputs are marked complete,
resumes the first incomplete experiment from the newest checkpoint consistent
with its published logs, and then runs the remaining queued experiments:

```powershell
$batchId = (Get-Content results/experiment_status.json | ConvertFrom-Json).batch_id
python run_experiments.py --resume-batch "results/$batchId" --stop-on-error
```

The existing batch-level status files are updated during recovery, so
`python monitor.py --watch` works normally in a second terminal. Recovery uses
the frozen defaults and experiment matrix in the batch manifest rather than the
currently editable plan file.

### Automatic recovery after a restart

The scheduled task `Mitigating Free Rider - Resume Experiments` runs after the
current Windows user logs on. It finds the newest unfinished batch, avoids
starting a duplicate runner, and resumes the remaining experiments. It then
runs the fixed MNIST non-IID, 30% free-rider plans for seed 42 followed by seed
43. The fixed result folders `results/mnist_noniid_fr30_seed42` and
`results/mnist_noniid_fr30_seed43` prevent duplicate batches and contain simple
`FR1` through `FR4` run directories.
Install or refresh the task with:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install_resume_task.ps1
```

Run the same recovery launcher immediately without restarting Windows:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\resume_experiments.ps1
```

Task output is appended to `results/scheduled_resume.log`. Because the trigger
uses the user-session Python environment and `E:` drive, Windows login is
required after a reboot before recovery starts.

To run before Windows is unlocked, open PowerShell as Administrator and install
the startup variant. Windows prompts for the current account password and stores
it in Task Scheduler; the password is not written to the project:

```powershell
cd "E:\New Projects\Mitigating-Free-Rider"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install_startup_resume_task.ps1
```

This replaces the logon trigger with an `At startup` trigger under the same
task name. Use the account password, not a Windows Hello PIN.

When `save_checkpoints=true`, every completed round creates a recovery
checkpoint. While a run is active or interrupted, only the five newest numbered
checkpoints are retained, controlled by `checkpoint_keep_last=5`, and
`latest_checkpoint.pt` is a portable copy of the newest snapshot. After an
experiment completes successfully, all numbered checkpoints and
`latest_checkpoint.pt` are deleted automatically. Failed or interrupted runs
keep their recovery checkpoints.

If the process is interrupted during a round, the unfinished round is lost, but
the last completed round remains recoverable. Resume an interrupted individual run using the
same experiment settings, output directory, and run name, plus its checkpoint:

```powershell
python run_experiment.py --set dataset=mnist --set distribution=noniid --set dirichlet_alpha=0.5 --set free_rider_pct=0.4 --set attack_type=FR1 --set num_clients=100 --set num_rounds=100 --set seed=42 --set device=auto --set output_dir=results/manual_mnist_noniid_fr40 --set run_name=FR1_swtcp_v8_noniid_fr40_seed42 --set resume_checkpoint=results/manual_mnist_noniid_fr40/FR1_swtcp_v8_noniid_fr40_seed42/latest_checkpoint.pt
```

Do not resume a checkpoint using a different attack, dataset, distribution, or
methodology version.

## 7. Changing the experiment

Common command-line overrides are:

```text
dataset=mnist or cifar10
distribution=iid or noniid
dirichlet_alpha=0.5
free_rider_pct=0.1, 0.2, 0.3, or 0.4
attack_type=FR1, FR2, FR3, or FR4
num_clients=100
num_rounds=100
seed=42
device=auto, cpu, or cuda
checkpoint_keep_last=5
candidate_confirmation_flags=2
profile_z_threshold=3.0
profile_mad_floor=0.01
```

Use a different `run_name` for every seed or configuration.
