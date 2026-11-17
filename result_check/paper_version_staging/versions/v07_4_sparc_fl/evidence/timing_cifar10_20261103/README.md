# Measured CIFAR-10 segment timing comparison

100 clients, 100 rounds, non-IID, FR3 40%, seed 42, CPU/6 threads, three local SGD epochs.
No network communication is measured. Paired sequential workflows are not a detector-only controlled speedup test.
Our active-client/trap workload changes; STD retains all clients and freshly fits five epochs per round.
Five epochs/reset frequency are declared reproduction choices, not settings established by Lin et al.
Checkpoint/logging and unassigned harness costs are included separately, without attributing them to detection.
Instrumentation CSV publication is excluded and recorded in each timing_summary.json.

| Segment | Ours s/round | STD-DAGMM s/round |
|---|---:|---:|
| Honest training | 81.371468 | 72.422875 |
| Fabrication | 0.188291 | 0.223963 |
| Client evaluation | 0.899274 | 0.000000 |
| Traps + scheduling | 0.018231 | 0.000000 |
| Features + preparation | 0.729371 | 0.115144 |
| Detector fitting | 0.000000 | 42.090017 |
| Decision / scoring | 0.043427 | 0.827315 |
| Aggregation | 0.096397 | 0.136232 |
| Global evaluation | 5.212093 | 4.238189 |
| Research logs + checkpoint | 11.339271 | 9.755540 |
| Unassigned / harness | 0.054297 | 7.490277 |
