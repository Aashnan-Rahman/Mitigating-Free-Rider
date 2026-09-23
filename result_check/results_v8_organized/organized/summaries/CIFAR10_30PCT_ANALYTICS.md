# CIFAR-10 30% V8 analytics

All sixteen planned runs completed: IID and Dirichlet non-IID partitions, two repeated seeds, and FR1--FR4. Every run removed all 30 free riders, so recall is 100% throughout.

## Best-observed configuration summary

As in the paper, each attack is represented by its strongest completed observation and the four selected attacks are then combined.

| Partition | TP | FP | FN | Precision | Recall | F1 | Mean final accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|
| IID | 120 | 2 | 0 | 98.36% | 100% | 99.17% | 77.89% |
| Non-IID | 120 | 48 | 0 | 71.43% | 100% | 83.33% | 75.67% |

The IID result is strong. The non-IID result has complete detection but an unacceptable honest-removal tail: individual runs remove 7--18 honest clients. It is retained in the archive and reported as a limitation rather than being represented as an unevaluated setting.

## Best-observed removal timing

| Attack | IID completion | Non-IID progression |
|---|---:|---|
| FR1 | Round 30 | 100% at round 30 |
| FR2 | Round 30 | 100% at round 32 |
| FR3 | Round 30 | 100% at round 30 |
| FR4 | Round 30 | 53.33% at round 30, 86.67% at round 31, 100% at round 32 |

Across all eight runs per partition, mean execution time is 97.8 seconds/round for IID and 88.6 seconds/round for non-IID. Mean peak process RSS is 1.78 GB and 1.79 GB, respectively.
