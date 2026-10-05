# CIFAR-10 Result Analytics

Analyzed 8 completed runs from results\v12_cifar10_iid_fr40_seed42, results\v12_cifar10_noniid_fr40_seed42.
Seeds: 42.
Comparisons below match attack and seed. These are descriptive results, not causal estimates.

## Run summary

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

## Main findings

- Highest final global accuracy: iid FR3 at 76.80%.
- Strongest final detection: iid FR1 with F1 100.00% and precision 100.00%.
- Total free riders removed across runs: 320; total missed: 0.
- iid: mean final accuracy 76.18%; mean F1 100.00%; total honest removals 0.
- noniid: mean final accuracy 74.71%; mean F1 99.69%; total honest removals 1.
- Runtime is reconstructed from per-round metrics, because a resumed process's `total_wall_clock_seconds` only covers its final process segment.

## Attack-matched IID vs non-IID differences

- FR1, seed 42: non-IID minus IID final accuracy +0.40 pp; F1 +0.00 pp; honest removals +0.
- FR2, seed 42: non-IID minus IID final accuracy -1.97 pp; F1 +0.00 pp; honest removals +0.
- FR3, seed 42: non-IID minus IID final accuracy -2.08 pp; F1 -1.23 pp; honest removals +1.
- FR4, seed 42: non-IID minus IID final accuracy -2.24 pp; F1 +0.00 pp; honest removals +0.

## Interpretation limits

- Results from a single seed do not establish robustness. More seeds are required for uncertainty estimates or claims about generalization.
- There is no no-attack baseline in these two batches, so accuracy cost cannot be attributed solely to the defense or attack.
- Detection recall is a final removal metric; early-round flags and transient candidates should be interpreted from the event-level CSV files.
