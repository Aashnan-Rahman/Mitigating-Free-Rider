# CIFAR-10 Result Analytics

Analyzed 8 completed runs: IID seed 42 and non-IID seed 43, each with
40% free riders, 100 clients, and 100 rounds. Because distribution and seed both
change between the two batches, IID/non-IID differences are descriptive and
must not be interpreted as distribution-only causal effects.

## Run summary

| Distribution | Seed | Attack | Final acc. | Best acc. | F1 | Precision | Recall | FR removed | Honest removed | Removal rounds (first/median/last) | Hours |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|---:|
| iid | 42 | FR1 | 77.17% | 77.42% | 100.00% | 100.00% | 100.00% | 40 | 0 | 30/30/30 | 2.39 |
| iid | 42 | FR2 | 77.11% | 77.40% | 100.00% | 100.00% | 100.00% | 40 | 0 | 30/30/30 | 2.20 |
| iid | 42 | FR3 | 77.00% | 77.28% | 98.77% | 97.56% | 100.00% | 40 | 1 | 30/30/30 | 2.67 |
| iid | 42 | FR4 | 77.07% | 77.20% | 98.77% | 97.56% | 100.00% | 40 | 1 | 30/30/30 | 2.64 |
| noniid | 43 | FR1 | 74.61% | 74.68% | 90.91% | 83.33% | 100.00% | 40 | 8 | 30/30/30 | 2.11 |
| noniid | 43 | FR2 | 74.59% | 74.91% | 90.91% | 83.33% | 100.00% | 40 | 8 | 32/32/32 | 2.11 |
| noniid | 43 | FR3 | 74.85% | 75.17% | 86.02% | 75.47% | 100.00% | 40 | 13 | 30/30/30 | 2.52 |
| noniid | 43 | FR4 | 74.36% | 74.42% | 96.39% | 93.02% | 100.00% | 40 | 3 | 44/76.5/92 | 2.77 |

## Main findings

- Highest final global accuracy: iid FR1 at 77.17%.
- Strongest final detection: iid FR1 with F1 100.00% and precision 100.00%.
- Every run removed all 40 free riders: total false negatives across all runs = 0.
- IID mean final accuracy: 77.09%; mean detection F1: 99.38%; honest removals across four runs: 2.
- Non-IID mean final accuracy: 74.60%; mean detection F1: 91.06%; honest removals across four runs: 32.
- Runtime is reconstructed from per-round metrics, because a resumed process's `total_wall_clock_seconds` only covers its final process segment.

## Attack-matched IID vs non-IID differences

- FR1: non-IID minus IID final accuracy -2.56 pp; F1 -9.09 pp; honest removals +8.
- FR2: non-IID minus IID final accuracy -2.52 pp; F1 -9.09 pp; honest removals +8.
- FR3: non-IID minus IID final accuracy -2.15 pp; F1 -12.74 pp; honest removals +12.
- FR4: non-IID minus IID final accuracy -2.71 pp; F1 -2.38 pp; honest removals +2.

## Interpretation limits

- Only one seed exists per distribution, and the seeds differ. More seeds are required for uncertainty estimates or claims about generalization.
- There is no no-attack baseline in these two batches, so accuracy cost cannot be attributed solely to the defense or attack.
- Detection recall is a final removal metric; early-round flags and transient candidates should be interpreted from the event-level CSV files.
