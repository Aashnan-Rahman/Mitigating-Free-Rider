# Independent STD-DAGMM MNIST timing sample

Completed **10 real federated rounds**: MNIST noniid, seed 42,
100 clients, 40% FR3 free riders, CPU,
6 PyTorch threads. Each honest client performs 3 local SGD epochs;
the detector is freshly fitted for 5 epochs each round.

## Measured timing and explicitly projected cost

| Component | Mean s/round | Sample SD | Range (s) | CV | Estimated 100 rounds (min) |
|---|---:|---:|---:|---:|---:|
| Update preparation | 0.0570 | 0.0024 | 0.0540–0.0617 | 4.2% | 0.10 |
| Detector fit + mixture finalization | 15.5574 | 0.7012 | 14.2996–16.9605 | 4.5% | 25.93 |
| Scoring | 0.3235 | 0.0077 | 0.3137–0.3357 | 2.4% | 0.54 |
| Flag decision | 0.0029 | 0.0085 | 0.0002–0.0270 | 289.0% | 0.00 |
| All detector work | 15.9409 | 0.7021 | 14.6752–17.3539 | 4.4% | 26.57 |
| Other measured simulator compute | 46.4870 | 0.4508 | 45.7820–47.3018 | 1.0% | 77.48 |
| Combined measured compute | 62.4279 | 0.7910 | 61.3278–64.3671 | 1.3% | 104.05 |

Added detector work / other measured same-trajectory compute:
**34.29%**.
Detector fraction of their combined measured compute:
**25.53%**.
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
rounds was 14.87 s; in the last three it was 15.60 s.

## Memory and flags

- Maximum sampled detector-worker RSS: **1480.9 MiB**.
- Maximum sampled simulator-parent RSS: **903.4 MiB**.
- Minimum system available memory in recorded samples: **1169.1 MiB**.
- Distinct clients ever flagged: **0 free riders**, **59 honest**.
- Last-round flags: **0 free riders**, **23 honest**.
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

Historical v15.4, same dataset/partition/seed/attacker share/type: 100 actual rounds, mean logged full-round time 34.41 s, summed logged rounds 57.35 min. It removed 40 free riders and 0 honest clients by its full horizon. These are older, separately executed native runs, NOT an isolated detector-overhead control. Our protocol changes probing/aggregation/client count, while this baseline keeps 100 clients; host load, memory pressure and logged timer boundaries also differ. Do not interpret their ratio as a causal speedup. Do not compare 10-round baseline flags with 100-round permanent removals as equal-horizon detection results.

## Evidence and reproducibility

`protocol.json` records settings, independent seed streams and executed source
hashes. `round_timings.csv` and `client_flags.csv` retain every round/client;
`detector_round_XX.json`/`.log` retain detailed fitting/score measurements.
`summary.json` is the computational projection; `analysis_checks.json` records
independent verification of all rounds, flags and source hashes. Existing FL
results and our detector implementation are unchanged. Seven synthetic-pilot
tests plus four native-rule/projection tests passed before launch.

Reproduce with a NEW output directory:

```powershell
.\.venv\Scripts\python.exe run_std_dagmm_mnist.py --rounds 10 --clients 100 --distribution noniid --attack FR3 --free-rider-pct .4 --seed 42 --threads 6 --detector-epochs 5 --detector-batch 20 --local-epochs 3 --output analysis/std_dagmm_mnist_native_repeat
```

Interrupted runs can be continued by repeating the exact original command with
`--resume`; checkpointed client-loader/attack RNGs and history are restored.
This one-off benchmark is NOT registered with the Windows startup scheduler.
The ignored checkpoint and transient matrix are runtime state, not final evidence.
