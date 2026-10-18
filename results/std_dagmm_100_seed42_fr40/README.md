# Actual 100-round STD-DAGMM timing queue

Scheduled 18 October 2026 (Asia/Dhaka): MNIST first, then CIFAR-10, sequentially.
Each run executes 100 actual rounds, 100 clients, non-IID Dirichlet alpha .5,
40% FR3, seed 42, three local SGD epochs and five fresh detector-fitting epochs,
CPU with six PyTorch threads. Flags only; all clients continue aggregating.
Five epochs is a declared reproduction budget, not verified convergence or
author-code replication. CIFAR can encounter RAM pressure/paging on this PC.

The old ten-round samples are preserved. New run folders retain per-round
training/fabrication/aggregation/evaluation/preparation/fitting/scoring/decision
timers, full client energy flags and worker logs. No real network communication
is measured. Completion is shown by status/summary files, not this README.

```powershell
.\.venv\Scripts\python.exe monitor.py --watch
# Fixed queue selection, if other batches exist:
.\.venv\Scripts\python.exe monitor.py --status results/std_dagmm_100_seed42_fr40/experiment_status.json --watch
```

The existing password-based Windows task now dispatches this enabled queue
without changing its credentials, startup/logon triggers or five-minute watchdog.
After Windows boots, it resumes the last complete checkpoint (or its backup),
replaying an unfinished round. Saved source/config hashes reject mixed resumes.
Batch/per-run file locks and orphan-worker detection prevent duplicate workers.
Startup settings and the controlled interruption test are recorded in
`recovery_verification.json`; no real reboot/power cut was performed.

`STOP_REQUESTED` in this batch directory stops/blocks automatic execution.
Setting `auto_resume=false` in `configs/std_dagmm_100_queue.json` restores the
launcher to its previous completed-study queue; do not change training settings
or source-hashed files during an unfinished native run.

After both runs finish, the queue independently validates their 100 rounds and
writes `actual_100_round_comparison.csv` and `.json`. Those totals are measured,
not extrapolated. Paper timing charts remain based on the earlier samples until
the new completed evidence is explicitly incorporated.
