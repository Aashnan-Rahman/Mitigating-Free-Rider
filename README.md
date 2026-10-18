# SWT-CP Free-Rider Federated Learning Simulator

This repository implements the `guidelines.md` specification for Suspicion-Weighted
Trap Detection with Cumulative Penalty.

For complete individual-run, four-attack scheduling, monitoring, timing, CUDA,
checkpoint, and resume commands, see [`RUN_GUIDE.md`](RUN_GUIDE.md).

The rewritten full-study manuscript is
[`paper_v6.pdf`](result_check/paper_version_staging/versions/v06_v15_4_full_study/paper_v6.pdf),
with v2-style sections, all 32 completed v15.4 runs, separate result/security
analysis, and per-run appendices. Rebuild with `build_paper_v6_full_study.py --compile`.

## Current CIFAR-10 no-detection baselines (18 October 2026)

`configs/fedavg_cifar10_baseline_seed42_fr30_fr40.json` schedules 16 sequential
100-round cases: IID/non-IID, FR1--FR4, 30%/40%, seed 42, 100 clients, CPU/6
threads and 3 local SGD epochs. No detection, traps, quarantine, filtering or
removal executes: every returned response enters ordinary unweighted FedAvg.
Non-IID runs go first. The existing startup/logon/five-minute recovery task
prioritizes this queue when its `auto_resume` is enabled, preserving credentials.

Watch with `.\.venv\Scripts\python.exe monitor.py --watch`. Outputs go to
`results/fedavg_cifar10_baseline_seed42_fr30_fr40/`: all client/round metrics,
phase timings, partition indices, source/config hashes, logs, final global model,
and latest/previous recovery states. Full response tensors from every client and
round are not archived. A batch STOP_REQUESTED marker blocks recovery. Live
baseline outputs stay out of Git until completion; files remain stored locally.

## Completed native STD-DAGMM timing queue (18 October 2026)

`configs/std_dagmm_100_queue.json` completed two separate actual 100-round runs:
MNIST, then CIFAR-10; non-IID, 100 clients, 40% FR3, seed 42, CPU/6 threads,
3 local SGD epochs and 5 fresh detector epochs each round. All clients remain;
flags do not cause removal. Ten-round samples and existing paper data are kept.

The existing password-based startup/logon/five-minute Windows task dispatches
this queue while `auto_resume` is true. Credentials/triggers are unchanged.
Recovery resumes the last completed checkpoint, replays an unfinished round,
uses a previous-checkpoint fallback, and prevents duplicate parent/worker runs.
Windows must actually boot and the data volume must be available; the task cannot
turn a powered-off PC on. Source/config changes intentionally block mixed resume.

```powershell
.\.venv\Scripts\python.exe monitor.py --watch
# Or select this queue explicitly:
.\.venv\Scripts\python.exe monitor.py --status results/std_dagmm_100_seed42_fr40/experiment_status.json --watch
```

Results, full timing segments, energy flags and per-run logs go into
`results/std_dagmm_100_seed42_fr40/`. On completion, the queue validates both runs
and writes `actual_100_round_comparison.csv`. A batch `STOP_REQUESTED` file blocks
automatic restart; disabling `auto_resume` returns the task to its legacy queue.
These remain paper-guided reproductions with an explicit fitting budget, not
verified author-code implementations. CIFAR memory pressure/paging is a caveat.
The full measured outcomes are in `analysis/std_dagmm_100_round_summary/` and
now replace the earlier projections in the timing report and manuscript.

## V15.4 completed study recovery

The current persistent recovery queue is
[`configs/scheduled_experiment_queue.json`](configs/scheduled_experiment_queue.json):
finish CIFAR-10 30%, then MNIST 40%, then MNIST 30%, all v15.4/seed 42.
Each MNIST batch contains eight 100-round cases, non-IID FR3/FR4/FR2/FR1 before
IID FR4/FR3/FR2/FR1. The existing password-based startup/watchdog task reads this
queue without re-registering its account or credentials. Completed batches are
skipped; a stopped/failed prerequisite blocks later batches. Use `-Queue ""` on
the recovery launcher to run a single plan without its queued successors.

The opt-in `swtcp_v15_4` preserves the v15.3 certificate gate and counts fresh
two-trap norm/profile certificates across ambiguous cycles. The same component
must certify twice; two consecutive clean cycles clear its memory. Stored
evidence alone cannot renew quarantine. Exact sendback remains consecutive,
and no attack-specific threshold or removal quota is used. This is empirical
screening, not a guarantee of zero misses or false removals.

Run all eight CIFAR-10 seed-42 cases (40% free riders, 100 rounds), non-IID first,
with `configs/v15_4_cifar10_seed42_fr40_plan.json`. Completed v15.3 runs remain
preserved; its unfinished run/queue was discarded during the 2026-10-15 cleanup
and is blocked from automatic restart by its STOP_REQUESTED marker.

Historical incomplete-run cleanup is recorded in
[`result_check/cleanup_2026_10_15.json`](result_check/cleanup_2026_10_15.json).
Completed evidence, previous paper versions, and the active 30% CIFAR-10 batch
are preserved. Removed partial runs are locally recoverable under the ignored
`.local_cleanup/2026-10-15/` directory. Caches, recovery checkpoints, live monitor
files, paper compilation scratch, and the active batch are excluded from Git;
the active batch should be explicitly added after successful completion.
Install/reinstall recovery using:

```powershell
.\install_resume_task.ps1 -Plan configs\v15_4_cifar10_seed42_fr40_plan.json
```

Recovery runs at logon and every five minutes while logged on, skips completed
runs, resumes the latest published checkpoint and prevents duplicate runners.
It honours intentional stop markers. Start the task immediately with
`Start-ScheduledTask -TaskName "Mitigating Free Rider - Resume Experiments"`.

For recovery before Windows login, open PowerShell as Administrator, run the
following locally, and enter your Windows account password only into its secure
credential prompt (not chat):

```powershell
.\install_startup_resume_task.ps1 -Plan configs\v15_4_cifar10_seed42_fr40_plan.json
```

This verifies password-based unattended recovery one minute after startup,
at logon, and every five minutes. A successful setup verifies the saved task
settings; it does not reboot the PC or interrupt a running experiment.
Later calls to `install_resume_task.ps1` preserve an existing unattended account
and its Windows-managed credentials instead of changing it to interactive mode.
The PC must be awake and the project drive available; powered-off/sleeping PCs
cannot execute training. Interactive-only mode still requires a logged-in user.

## V15.3 strict norm experiment

The opt-in `swtcp_v15_3` backend removes concentration-only norm certificates:
the measured gap to the full peer population must exceed the cohort's own IQR
on both traps in consecutive cycles. Overlapping low-norm groups remain
candidates; diagonal scores cannot authorize removal. Profile certificates,
exact-sendback confirmation, bounded review and training settings retain v15.1
behavior. This applies in every cycle, not just after round 30, and can reduce
recall; it provides no guaranteed false-positive bound.

The seed-42 MNIST IID/non-IID FR1-FR4 plan is
`configs/v15_3_mnist_seed42_fr40_plan.json` (40% free riders, 100 rounds).
`queued_experiments.ps1` waits for the entire v15.1 seed-42 batch to complete
before launching it and resumes the prerequisite first after an interruption.
Previous result directories and source-hashed v15.1 engine files are preserved.
See `guidelines.md` for the full policy and its known detection trade-off.

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
In v8, active anchor panels rotate through the never-flagged U roster. Off-duty
roster members aggregate normally, and the Y sweep periodically audits them;
any flagged client permanently loses anchor eligibility.

See [`VERSION_HISTORY.md`](VERSION_HISTORY.md) for the v4-v8 methodology and
result provenance.
