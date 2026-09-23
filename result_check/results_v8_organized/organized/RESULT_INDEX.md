# V8 Result Index

This directory is the canonical, consistently named collection of completed V8 experiments. The original result directories and ZIP archives were copied, not moved or deleted.

## Directory convention

```text
<dataset>/<distribution>/attackers_<percentage>pct/seed_<number>/<attack>/
```

Examples:

```text
mnist/iid/attackers_30pct/seed_42/FR1/
mnist/noniid/attackers_40pct/seed_46/FR4/
cifar10/noniid/attackers_40pct/seed_43/FR3/
```

Baseline experiments are stored under:

```text
baselines/mnist/attackers_40pct/seed_42/
```

General analytics and scheduling logs are stored in `summaries/`.

## Included completed runs

| Family | Completed runs |
|---|---:|
| SWT-CP MNIST | 35 |
| SWT-CP CIFAR-10 | 32 |
| MNIST baselines | 16 |
| **Total** | **83** |

Every canonical run contains a `run_config.json` reporting 100 completed rounds.

## Canonical-source decisions

- The completed IID MNIST 40% run from `batch_20260914_133915` is used for seed 42. The older partial batch contained in the same source ZIP is not presented as a canonical run.
- The newer completed workspace copy of MNIST non-IID 30%, seed 42 is used. Its earlier archived execution remains recoverable from the original ZIP.
- MNIST non-IID 40% FR4 repetitions for seeds 44, 45, and 46 are included in addition to the archived seed 42 and 43 runs.
- All CIFAR-10 and baseline batches currently present in the workspace results directory are included.
- The completed `cifar10_fr30_seeds42_43` batch supplies the CIFAR-10 IID and non-IID 30% runs for both repeated seeds and all four attacks.

## Original archive mapping

| Original archive | Canonical contents |
|---|---|
| `results v8 s42 3.zip` | MNIST IID, 30%, seed 42 |
| `results v8 s43 3.zip` | MNIST IID, 30%, seed 43 |
| `results v8 v42 4.zip` | MNIST IID, 40%, seed 42 |
| `results v8 s43 4.zip` | MNIST IID, 40%, seed 43 |
| `results v8 non iid 30.zip` | MNIST non-IID, 30%, seeds 42 and 43 |
| `results v8 non iid 40.zip` | MNIST non-IID, 40%, seeds 42 and 43 |
| `results/cifar10_fr30_seeds42_43/` | CIFAR-10 IID and non-IID, 30%, two seeds |

## Integrity notes

- No completed experiment is intentionally excluded because of its detection result.
- Seed identifiers remain in the result archive for reproducibility, even if a paper later reports pooled statistics.
- Candidate clients are not equivalent to permanently removed clients; both should be analyzed when reporting operational false positives.
