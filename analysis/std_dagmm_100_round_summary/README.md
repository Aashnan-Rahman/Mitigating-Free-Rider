# Actual 100-round STD-DAGMM results

| Dataset | Fit s/round | Score s/round | Detector s/round | All compute s/round | Actual compute min | Final accuracy | Ever flagged FR / honest |
|---|---:|---:|---:|---:|---:|---:|---:|
| mnist | 13.629 | 0.278 | 13.952 | 50.186 | 83.64 | 98.44% | 0/40 / 60/60 |
| cifar10 | 45.029 | 0.856 | 46.040 | 127.239 | 212.06 | 72.55% | 0/40 / 60/60 |

All totals are measured over 100 actual rounds, not extrapolated. Same non-IID FR3, seed 42, 40% setup; 100 clients remain throughout.
Flags are roundwise observations, not permanent removals. All responses aggregate. Five fresh detector epochs per round are an explicit reproduction budget, not verified author-code fidelity or convergence.
No FR was ever flagged and every honest client was flagged at least once in both runs. This is a limitation of this selected implementation/scenario, not a universal claim about STD-DAGMM.
CIFAR encountered near-zero available RAM; paging can confound timings and was not itself measured. Compute excludes worker startup, serialization and checkpoint publication; full per-round wall timings remain in source CSVs.
Earlier ten-round pilots are preserved separately. Small final models and their hashes are retained; large latest/previous recovery histories stay local and are excluded from Git.
