# Independent STD-DAGMM MNIST timing sample

Completed **100 real federated rounds**: MNIST noniid, seed 42,
100 clients, 40% FR3 free riders, CPU,
6 PyTorch threads. Each honest client performs 3 local SGD epochs;
the detector is freshly fitted for 5 epochs each round.

## Measured timing and explicitly projected cost

| Component | Mean s/round | Sample SD | Range (s) | CV | Measured 100 rounds (min) |
|---|---:|---:|---:|---:|---:|
| Update preparation | 0.0447 | 0.0038 | 0.0405–0.0607 | 8.5% | 0.07 |
| Detector fit + mixture finalization | 13.6293 | 0.4670 | 12.3878–15.9732 | 3.4% | 22.72 |
| Scoring | 0.2782 | 0.0110 | 0.2409–0.3198 | 4.0% | 0.46 |
| Flag decision | 0.0002 | 0.0000 | 0.0002–0.0004 | 15.5% | 0.00 |
| All detector work | 13.9525 | 0.4764 | 12.6729–16.3375 | 3.4% | 23.25 |
| Other measured simulator compute | 36.2333 | 1.5812 | 35.3888–45.9492 | 4.4% | 60.39 |
| Combined measured compute | 50.1858 | 1.9428 | 49.0449–62.0292 | 3.9% | 83.64 |

Added detector work / other measured same-trajectory compute:
**38.51%**.
Detector fraction of their combined measured compute:
**27.80%**.
These are different denominators. The baseline component is the sum of measured
client work, fabrication, aggregation and evaluation in this trajectory, NOT a
separate no-detector control run. Observed wall time additionally includes worker
startup, matrix serialization and other instrumentation; those costs are retained
per round but excluded from the computational projection. Checkpoint publication
happens after that round timer and is not included in compute totals/projections.

The 100-round totals are sums of **100 actually executed rounds**, not extrapolations. Mean seconds per round is that measured total divided by 100.
Neither measured totals nor projections constitute a confidence interval,
proof of converged-model detection, or a guarantee of constant late-round cost.
Ranges/SD/CV expose observed variation. Mean fitting time in the first three
rounds was 15.84 s; in the last three it was 13.63 s.

## Memory and flags

- Maximum sampled detector-worker RSS: **1482.3 MiB**.
- Maximum sampled simulator-parent RSS: **895.5 MiB**.
- Minimum system available memory in recorded samples: **2329.3 MiB**.
- Distinct clients ever flagged: **0 free riders**, **60 honest**.
- Last-round flags: **0 free riders**, **22 honest**.
- Permanent removals: **none**, by design. Flags do not become an invented removal rule.

RSS is sampled every 20 ms, not exact allocator accounting; short peaks can be
missed. Parent/worker peak values must NOT simply be added as though their peaks
occurred simultaneously. No paging or energy-consumption measurements were made.

## Native detection workflow and fidelity limits

Ordinary global model -> local client training/fabrication -> flattened updates ->
STD-DAGMM fitting -> energy flags -> ordinary unfiltered FedAvg. **No traps,
warmup, paired comparisons, our z/profile nomination, quarantine or confirmation**
are applied. Reusing shared model/data/SGD/seed utilities does not run our detector.
The worker receives only the full update matrix and fitting settings. Evaluation
labels are joined after flags are final, never used for thresholds or fitting.
The one-sided flag rule is energy > population mean + one population SD; it
does not use known attacker prevalence or a quota.

This is a **paper-guided reproduction**, not original author code or a claimed
exact published experiment. The underlying external MNIST/SGD/FR3 scenario is
matched to our study, not substituted with a paper's different dataset/model.
Widths 128/64/32, K=3 and loss weights .1/.005 follow FRIDA's STD-DAGMM description.
Fresh initialization, five detector epochs, Adam .001, batch size 20, clipping 5,
covariance ridge 1e-6, float64 small-mixture math and the symmetric decoder are
declared choices where the full original recipe is not verified. Inputs are full
206,922-coordinate float32 updates; there is no few-scalar proxy or projection.
Five epochs is a budget, NOT proof of convergence. Poor flags here must not be
generalized to every STD-DAGMM implementation or horizon. No thresholds were
retuned to these results. Per-round reconstruction/energy losses remain in the
detector JSON/logs for review.

References: [STD-DAGMM](https://arxiv.org/pdf/1911.12560),
[FRIDA baseline description](https://arxiv.org/html/2410.05020v2).

## Context for comparison with our native method

Historical v15.4, same dataset/partition/seed/attacker share/type: 100 actual rounds, mean logged full-round time 34.41 s, summed logged rounds 57.35 min. It removed 40 free riders and 0 honest clients by its full horizon. These are older, separately executed native runs, NOT an isolated detector-overhead control. Our protocol changes probing/aggregation/client count, while this baseline keeps 100 clients; host load, memory pressure and logged timer boundaries also differ. Do not interpret their ratio as a causal speedup. Roundwise flags and permanent removals remain different outcomes, even at an equal horizon.

## Evidence and reproducibility

`protocol.json` records settings, independent seed streams and executed source
hashes. `round_timings.csv` and `client_flags.csv` retain every round/client;
`detector_round_XX.json`/`.log` retain detailed fitting/score measurements.
`summary.json` retains measured totals (100-round runs) or explicit projections
(short samples); `analysis_checks.json` records
independent verification of all rounds, flags and source hashes. Existing FL
results and our detector implementation are unchanged. Protocol checks validate
the round/client grid, score-based flags and frozen source hashes.

Reproduce with a NEW output directory:

```powershell
.\.venv\Scripts\python.exe run_std_dagmm_long.py --dataset mnist --rounds 100 --clients 100 --distribution noniid --attack FR3 --free-rider-pct 0.4 --seed 42 --threads 6 --detector-epochs 5 --detector-batch 20 --local-epochs 3 --output analysis/std_dagmm_mnist_native_repeat
```

Interrupted runs can be continued by repeating the exact original command with
`--resume`; checkpointed client-loader/attack RNGs and history are restored.
This run is part of the persistent startup/logon/watchdog queue. An interrupted round replays from the last completed checkpoint; a previous-checkpoint fallback is retained.
The ignored checkpoint and transient matrix are runtime state, not final evidence.
