# Measured MNIST segment timing comparison

100 clients, 100 rounds, non-IID, FR3 40%, seed 42, CPU/6 threads, three local SGD epochs.
No network communication is measured. Paired sequential workflows are not a detector-only controlled speedup test.
Our active-client/trap workload changes; STD retains all clients and freshly fits five epochs per round.
Five epochs/reset frequency are declared reproduction choices, not settings established by Lin et al.
Checkpoint/logging and unassigned harness costs are included separately, without attributing them to detection.
Instrumentation CSV publication is excluded and recorded in each timing_summary.json.

| Segment | Ours s/round | STD-DAGMM s/round |
|---|---:|---:|
| Honest training | 34.299833 | 33.885859 |
| Fabrication | 0.018477 | 0.066170 |
| Client evaluation | 0.161262 | 0.000000 |
| Traps + scheduling | 0.001768 | 0.000000 |
| Features + preparation | 0.197901 | 0.045453 |
| Detector fitting | 0.000000 | 15.761211 |
| Decision / scoring | 0.015536 | 0.334632 |
| Aggregation | 0.029923 | 0.042896 |
| Global evaluation | 2.195843 | 2.125535 |
| Research logs + checkpoint | 3.994650 | 3.747721 |
| Unassigned / harness | 0.008776 | 6.823828 |
