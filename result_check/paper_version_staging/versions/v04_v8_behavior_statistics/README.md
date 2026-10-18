# V8 all-run attack statistics

Source: 67 completed v8 executions; no best-seed selection.

| Dataset / partition | Share | Attack | n | Recall mean ± SD (%) | Range | Honest removed/run | Pooled P/F1 (%) | Full runs | Full-round median | Model accuracy (%) |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| cifar10 iid | 30% | FR1 | 2 | 100.0 ± 0.0 | 100–100 | 1.0 | 96.8 / 98.4 | 2/2 | 30.0 | 77.6 |
| cifar10 iid | 30% | FR2 | 2 | 100.0 ± 0.0 | 100–100 | 0.0 | 100.0 / 100.0 | 2/2 | 30.0 | 77.8 |
| cifar10 iid | 30% | FR3 | 2 | 100.0 ± 0.0 | 100–100 | 1.0 | 96.8 / 98.4 | 2/2 | 30.0 | 77.9 |
| cifar10 iid | 30% | FR4 | 2 | 100.0 ± 0.0 | 100–100 | 0.0 | 100.0 / 100.0 | 2/2 | 30.0 | 77.5 |
| cifar10 iid | 40% | FR1 | 2 | 100.0 ± 0.0 | 100–100 | 0.5 | 98.8 / 99.4 | 2/2 | 30.0 | 76.8 |
| cifar10 iid | 40% | FR2 | 2 | 100.0 ± 0.0 | 100–100 | 0.5 | 98.8 / 99.4 | 2/2 | 30.0 | 76.7 |
| cifar10 iid | 40% | FR3 | 2 | 100.0 ± 0.0 | 100–100 | 0.5 | 98.8 / 99.4 | 2/2 | 30.0 | 76.8 |
| cifar10 iid | 40% | FR4 | 2 | 100.0 ± 0.0 | 100–100 | 0.5 | 98.8 / 99.4 | 2/2 | 30.0 | 76.7 |
| cifar10 noniid | 30% | FR1 | 2 | 100.0 ± 0.0 | 100–100 | 8.0 | 78.9 / 88.2 | 2/2 | 30.0 | 75.7 |
| cifar10 noniid | 30% | FR2 | 2 | 100.0 ± 0.0 | 100–100 | 15.5 | 65.9 / 79.5 | 2/2 | 32.0 | 76.0 |
| cifar10 noniid | 30% | FR3 | 2 | 100.0 ± 0.0 | 100–100 | 12.5 | 70.6 / 82.8 | 2/2 | 30.0 | 75.6 |
| cifar10 noniid | 30% | FR4 | 2 | 100.0 ± 0.0 | 100–100 | 16.5 | 64.5 / 78.4 | 2/2 | 32.0 | 75.2 |
| cifar10 noniid | 40% | FR1 | 2 | 100.0 ± 0.0 | 100–100 | 8.5 | 82.5 / 90.4 | 2/2 | 30.0 | 74.7 |
| cifar10 noniid | 40% | FR2 | 2 | 100.0 ± 0.0 | 100–100 | 11.0 | 78.4 / 87.9 | 2/2 | 32.0 | 74.8 |
| cifar10 noniid | 40% | FR3 | 2 | 100.0 ± 0.0 | 100–100 | 11.0 | 78.4 / 87.9 | 2/2 | 30.0 | 74.6 |
| cifar10 noniid | 40% | FR4 | 2 | 100.0 ± 0.0 | 100–100 | 6.5 | 86.0 / 92.5 | 2/2 | 62.5 | 74.5 |
| mnist iid | 30% | FR1 | 2 | 100.0 ± 0.0 | 100–100 | 1.5 | 95.2 / 97.6 | 2/2 | 30.0 | 98.9 |
| mnist iid | 30% | FR2 | 2 | 100.0 ± 0.0 | 100–100 | 1.0 | 96.8 / 98.4 | 2/2 | 30.0 | 98.9 |
| mnist iid | 30% | FR3 | 2 | 100.0 ± 0.0 | 100–100 | 0.5 | 98.4 / 99.2 | 2/2 | 30.0 | 99.0 |
| mnist iid | 30% | FR4 | 2 | 100.0 ± 0.0 | 100–100 | 1.5 | 95.2 / 97.6 | 2/2 | 30.0 | 98.9 |
| mnist iid | 40% | FR1 | 2 | 100.0 ± 0.0 | 100–100 | 1.0 | 97.6 / 98.8 | 2/2 | 30.0 | 98.9 |
| mnist iid | 40% | FR2 | 2 | 100.0 ± 0.0 | 100–100 | 0.5 | 98.8 / 99.4 | 2/2 | 30.0 | 98.9 |
| mnist iid | 40% | FR3 | 2 | 100.0 ± 0.0 | 100–100 | 1.0 | 97.6 / 98.8 | 2/2 | 30.0 | 98.9 |
| mnist iid | 40% | FR4 | 2 | 100.0 ± 0.0 | 100–100 | 0.5 | 98.8 / 99.4 | 2/2 | 31.5 | 98.8 |
| mnist noniid | 30% | FR1 | 2 | 100.0 ± 0.0 | 100–100 | 2.0 | 93.8 / 96.8 | 2/2 | 30.0 | 98.9 |
| mnist noniid | 30% | FR2 | 2 | 100.0 ± 0.0 | 100–100 | 2.5 | 92.3 / 96.0 | 2/2 | 32.0 | 98.9 |
| mnist noniid | 30% | FR3 | 2 | 100.0 ± 0.0 | 100–100 | 3.0 | 90.9 / 95.2 | 2/2 | 30.0 | 98.9 |
| mnist noniid | 30% | FR4 | 2 | 100.0 ± 0.0 | 100–100 | 2.0 | 93.8 / 96.8 | 2/2 | 32.0 | 98.9 |
| mnist noniid | 40% | FR1 | 2 | 100.0 ± 0.0 | 100–100 | 2.0 | 95.2 / 97.6 | 2/2 | 30.0 | 98.9 |
| mnist noniid | 40% | FR2 | 2 | 100.0 ± 0.0 | 100–100 | 1.5 | 96.4 / 98.2 | 2/2 | 33.0 | 98.9 |
| mnist noniid | 40% | FR3 | 2 | 100.0 ± 0.0 | 100–100 | 3.5 | 92.0 / 95.8 | 2/2 | 30.0 | 98.9 |
| mnist noniid | 40% | FR4 | 5 | 40.0 ± 54.8 | 0–100 | 0.4 | 97.6 / 56.7 | 2/5 | 82.0 | 98.9 |

SD is sample SD across seeds. Full-round median conditions on full detection; -- means no successful completion. Undefined precision is --. Raw CSVs include per-run values, score quartiles and honest-removal rates.

## Provenance

Totals across executions: 2240 removed attackers, 237 removed honest clients, 120 missed attackers. These repeated-run counts are not a unique-client population.

Original v2/v3 and all archived results remain unchanged. Build: python build_paper_v4_v8_statistics.py; compile paper_v4.tex with pdflatex/bibtex in this directory.
