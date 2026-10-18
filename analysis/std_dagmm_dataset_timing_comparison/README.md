# STD-DAGMM: MNIST versus CIFAR-10

Ten actual rounds per dataset, 100 participating clients throughout, non-IID,
seed 42, 40% FR3; 3 local epochs, 5 fresh detector epochs, CPU/6 threads.
Full update vectors, unchanged detector fitting/scoring implementation.

| Component | MNIST mean ± SD (s/round) | CIFAR-10 mean ± SD (s/round) | CIFAR/MNIST |
|---|---:|---:|---:|
| fit_seconds | 15.557 ± 0.701 | 44.973 ± 3.217 | 2.89× |
| inference_seconds | 0.323 ± 0.008 | 0.907 ± 0.070 | 2.80× |
| detector_seconds | 15.941 ± 0.702 | 46.049 ± 3.301 | 2.89× |
| baseline_compute_seconds | 46.487 ± 0.451 | 100.240 ± 10.073 | 2.16× |
| round_compute_seconds | 62.428 ± 0.791 | 146.289 ± 13.096 | 2.34× |

CSV also gives conditional 100-round projections (observed mean × 100), not
completed 100-round measurements. Fixed workload makes similar timing plausible,
not guaranteed: CPU load, RAM pressure, caches and paging may change.
MNIST and CIFAR use their respective study CNNs (206,922 versus 621,258 floating
update coordinates, including CIFAR batch-normalization buffers). This is a
dataset-plus-model workload comparison, not an isolated dataset-only effect.
Runs were sequential at different times, not randomized simultaneous controls.

Detector time includes preparation, fresh fitting/mixture finalization, scoring
and flag decisions. Combined compute adds local work, aggregation and evaluation;
it excludes process startup, matrix serialization and checkpoint writes.
Those harness costs remain separately recorded in per-round CSVs. No removals
or trap logic; all responses aggregate. Detection flags are not removal counts.
Minimum sampled system available RAM: MNIST 1169.1 MiB;
CIFAR-10 0.2 MiB. Maximum detector-worker
RSS: MNIST 1480.9 MiB; CIFAR-10
3704.3 MiB. RSS sampling may miss peaks;
parent and worker independent peaks must not be added as simultaneous usage.
Very low available memory can cause paging and distort timing; paging itself was
not measured. These are observed workstation timings, not memory-isolated CPU costs.

Five epochs is a declared reproduction budget, not verified convergence or an
exact author-code replication. No cutoffs were retuned to either dataset.

Our method's workload can shrink after removal; compare actual full-horizon
trajectories separately, not its early-round mean × 100. No causal speedup claim
against our older runs is justified by these two timing samples alone.
