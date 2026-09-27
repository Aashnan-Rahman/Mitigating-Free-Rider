# v12 40% results, seed 42

All 16 runs completed 100 rounds with 100 clients, 40 free riders, and seed 42. Non-IID uses Dirichlet alpha 0.5. Removal counts were cross-checked against unique client IDs in the event logs.

## MNIST

| Distribution | Seed | Attack | Final acc. | Best acc. | F1 | Precision | Recall | FR removed | Honest removed | Removal rounds (first/median/last) | Hours |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|---:|
| iid | 42 | FR1 | 98.87% | 98.91% | 100.00% | 100.00% | 100.00% | 40 | 0 | 10/10/10 | 1.51 |
| iid | 42 | FR2 | 98.87% | 98.87% | 100.00% | 100.00% | 100.00% | 40 | 0 | 30/30/30 | 1.54 |
| iid | 42 | FR3 | 98.82% | 98.87% | 100.00% | 100.00% | 100.00% | 40 | 0 | 30/30/30 | 1.64 |
| iid | 42 | FR4 | 98.83% | 98.84% | 100.00% | 100.00% | 100.00% | 40 | 0 | 30/30/30 | 1.68 |
| noniid | 42 | FR1 | 98.82% | 98.87% | 100.00% | 100.00% | 100.00% | 40 | 0 | 10/10/10 | 1.62 |
| noniid | 42 | FR2 | 98.85% | 98.88% | 100.00% | 100.00% | 100.00% | 40 | 0 | 30/30/30 | 1.61 |
| noniid | 42 | FR3 | 98.81% | 98.82% | 100.00% | 100.00% | 100.00% | 40 | 0 | 30/30/30 | 1.71 |
| noniid | 42 | FR4 | 98.82% | 98.86% | 100.00% | 100.00% | 100.00% | 40 | 0 | 30/30/30 | 1.60 |

- iid: mean final accuracy 98.85%; mean removal F1 100.00%; honest removals 0; summed round time 6.37 hours.
- noniid: mean final accuracy 98.83%; mean removal F1 100.00%; honest removals 0; summed round time 6.53 hours.

Non-IID minus IID final accuracy (percentage points):

- FR1: -0.05 pp.
- FR2: -0.02 pp.
- FR3: -0.01 pp.
- FR4: -0.01 pp.

## CIFAR10

| Distribution | Seed | Attack | Final acc. | Best acc. | F1 | Precision | Recall | FR removed | Honest removed | Removal rounds (first/median/last) | Hours |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|---:|
| iid | 42 | FR1 | 74.62% | 75.53% | 100.00% | 100.00% | 100.00% | 40 | 0 | 10/10/10 | 3.73 |
| iid | 42 | FR2 | 76.74% | 77.13% | 100.00% | 100.00% | 100.00% | 40 | 0 | 30/30/30 | 2.75 |
| iid | 42 | FR3 | 76.80% | 76.80% | 100.00% | 100.00% | 100.00% | 40 | 0 | 30/30/30 | 3.11 |
| iid | 42 | FR4 | 76.56% | 77.05% | 100.00% | 100.00% | 100.00% | 40 | 0 | 30/30/30 | 3.17 |
| noniid | 42 | FR1 | 75.02% | 75.12% | 100.00% | 100.00% | 100.00% | 40 | 0 | 10/10/10 | 2.35 |
| noniid | 42 | FR2 | 74.77% | 75.10% | 100.00% | 100.00% | 100.00% | 40 | 0 | 30/30/30 | 2.19 |
| noniid | 42 | FR3 | 74.72% | 74.77% | 98.77% | 97.56% | 100.00% | 40 | 1 | 30/30/30 | 2.94 |
| noniid | 42 | FR4 | 74.32% | 74.87% | 100.00% | 100.00% | 100.00% | 40 | 0 | 30/30/30 | 3.34 |

- iid: mean final accuracy 76.18%; mean removal F1 100.00%; honest removals 0; summed round time 12.77 hours.
- noniid: mean final accuracy 74.71%; mean removal F1 99.69%; honest removals 1; summed round time 10.82 hours.

Non-IID minus IID final accuracy (percentage points):

- FR1: +0.40 pp.
- FR2: -1.97 pp.
- FR3: -2.08 pp.
- FR4: -2.24 pp.

## False removals

- cifar10 noniid FR3: client 32, round 30; {'round': '30', 'client_id': '32', 'is_free_rider': '0', 'final_penalty': '-4.0', 'removal_basis': 'two_strong_cycles_with_trusted_confirmation', 'zero_update_count': '0', 'suspicion_probes': '4'}.

## Interpretation

Across runs, 640 free-rider instances were removed; 0 were missed. These are repeated experiment instances, not distinct real users.

Removal precision/recall do not measure temporary false flags or exclusion from aggregation. Final candidate and suspect counts are included in summary.csv. Single-seed results do not establish statistical robustness, and no no-attack baseline is included. Runtime sums use per-round timings and exclude setup overhead; device speed cannot be inferred from comparisons with different free-rider percentages.
