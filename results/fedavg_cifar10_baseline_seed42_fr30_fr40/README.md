# CIFAR-10 no-detection baseline matrix

16 sequential runs: IID/non-IID, FR1--FR4, 30%/40%, seed 42, 100 clients,
100 actual rounds each, three local SGD epochs, CPU with six PyTorch threads.
Non-IID FR3/FR4/FR2/FR1 run first at 40%, then 30%, followed by IID equivalents.

No detection, trap models, quarantine, filtering, score thresholds or removal.
All 100 responses aggregate every round using the study's ordinary unweighted
FedAvg. No honest-only run is included in this particular matrix.

Each run stores all client/round metrics, timing segments, partition indices,
source/config hashes, console logs, final global model, and latest/previous
recovery states. Detector time is structurally zero, not estimated. Network
communication is unmeasured; every full client response tensor is not archived.

The existing password-based startup/logon/five-minute Windows task prioritizes
the enabled plan `configs/fedavg_cifar10_baseline_seed42_fr30_fr40.json`.
An unfinished round replays from its last completed checkpoint, with a previous
checkpoint fallback. Windows must boot and the data volume must be available.

Watch: `.\.venv\Scripts\python.exe monitor.py --watch`

`STOP_REQUESTED` in this batch folder stops/blocks automatic recovery. After all
16 runs finish, independently validated `baseline_comparison.csv` and `.json`
are generated. Live records remain stored locally and ignored until completion;
completed records can then be explicitly archived to Git.
