# Independent STD-DAGMM CIFAR10 timing sample

Completed **10 real federated rounds**: CIFAR10 noniid, seed 42,
100 clients, 40% FR3 free riders, CPU,
6 PyTorch threads. Each honest client performs 3 local SGD epochs;
the detector is freshly fitted for 5 epochs each round.

## Measured timing and explicitly projected cost

| Component | Mean s/round | Sample SD | Range (s) | CV | Estimated 100 rounds (min) |
|---|---:|---:|---:|---:|---:|
| Update preparation | 0.1556 | 0.0393 | 0.1221–0.2528 | 25.3% | 0.26 |
| Detector fit + mixture finalization | 44.9731 | 3.2165 | 41.3030–50.4054 | 7.2% | 74.96 |
| Scoring | 0.9074 | 0.0699 | 0.8150–0.9814 | 7.7% | 1.51 |
| Flag decision | 0.0129 | 0.0163 | 0.0002–0.0330 | 126.8% | 0.02 |
| All detector work | 46.0490 | 3.3008 | 42.2736–51.5399 | 7.2% | 76.75 |
| Other measured simulator compute | 100.2400 | 10.0733 | 89.5174–112.4406 | 10.0% | 167.07 |
| Combined measured compute | 146.2890 | 13.0959 | 132.3336–161.4712 | 9.0% | 243.81 |

Added detector work / other measured same-trajectory compute:
**45.94%**.
Detector fraction of their combined measured compute:
**31.48%**.
These are different denominators. The baseline component is the sum of measured
client work, fabrication, aggregation and evaluation in this trajectory, NOT a
separate no-detector control run. Observed wall time additionally includes worker
startup, matrix serialization and other instrumentation; those costs are retained
per round but excluded from the computational projection. Checkpoint publication
happens after that round timer and is not included in either projection.

The 100-round estimate is **100 times the observed per-round mean**, conditional
on unchanged active-client count, model, local/detector epochs, device and load.
It is NOT a completed 100-round run, a confidence interval, an estimate of
converged-model detection, or evidence that late-round costs must stay constant.
Ranges/SD/CV expose observed variation. Mean fitting time in the first three
rounds was 48.45 s; in the last three it was 44.47 s.

## Memory and flags

- Maximum sampled detector-worker RSS: **3704.3 MiB**.
- Maximum sampled simulator-parent RSS: **1903.3 MiB**.
- Minimum system available memory in recorded samples: **0.2 MiB**.
- Distinct clients ever flagged: **0 free riders**, **59 honest**.
- Last-round flags: **0 free riders**, **21 honest**.
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
exact published experiment. The underlying external CIFAR10/SGD/FR3 scenario is
matched to our study, not substituted with a paper's different dataset/model.
Widths 128/64/32, K=3 and loss weights .1/.005 follow FRIDA's STD-DAGMM description.
Fresh initialization, five detector epochs, Adam .001, batch size 20, clipping 5,
covariance ridge 1e-6, float64 small-mixture math and the symmetric decoder are
declared choices where the full original recipe is not verified. Inputs are full
621,258-coordinate float32 updates; there is no few-scalar proxy or projection.
Five epochs is a budget, NOT proof of convergence. Poor flags here must not be
generalized to every STD-DAGMM implementation or horizon. No thresholds were
retuned to these results. Per-round reconstruction/energy losses remain in the
detector JSON/logs for review.

References: [STD-DAGMM](https://arxiv.org/pdf/1911.12560),
[FRIDA baseline description](https://arxiv.org/html/2410.05020v2).

## Context for comparison with our native method

Historical v15.4, same dataset/partition/seed/attacker share/type: 100 actual rounds, mean logged full-round time 84.85 s, summed logged rounds 141.41 min. It removed 40 free riders and 0 honest clients by its full horizon. These are older, separately executed native runs, NOT an isolated detector-overhead control. Our protocol changes probing/aggregation/client count, while this baseline keeps 100 clients; host load, memory pressure and logged timer boundaries also differ. Do not interpret their ratio as a causal speedup. Do not compare 10-round baseline flags with 100-round permanent removals as equal-horizon detection results.

## Evidence and reproducibility

`protocol.json` records settings, independent seed streams and executed source
hashes. `round_timings.csv` and `client_flags.csv` retain every round/client;
`detector_round_XX.json`/`.log` retain detailed fitting/score measurements.
`summary.json` is the computational projection; `analysis_checks.json` records
independent verification of all rounds, flags and source hashes. Existing FL
results and our detector implementation are unchanged. Protocol checks validate
the round/client grid, score-based flags and frozen source hashes.

Reproduce with a NEW output directory:

```powershell
.\.venv\Scripts\python.exe run_std_dagmm_native.py --dataset cifar10 --rounds 10 --clients 100 --distribution noniid --attack FR3 --free-rider-pct 0.4 --seed 42 --threads 6 --detector-epochs 5 --detector-batch 20 --local-epochs 3 --output analysis/std_dagmm_cifar10_native_repeat
```

Interrupted runs can be continued by repeating the exact original command with
`--resume`; checkpointed client-loader/attack RNGs and history are restored.
This one-off benchmark is NOT registered with the Windows startup scheduler.
The ignored checkpoint and transient matrix are runtime state, not final evidence.
