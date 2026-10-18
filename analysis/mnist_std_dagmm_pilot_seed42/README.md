# MNIST-sized STD-DAGMM computational feasibility pilot

Completed 18 October 2026, on this PC. This is **not federated training, an
attack experiment, a recall comparison, or an official STD-DAGMM reproduction**.
No experiment or deployed detector source was changed.

## Measured results

Three repetitions; six PyTorch CPU threads; 100 clients per input batch;
206,922 floating coordinates per response. Each comparison unit includes TWO
independent 100-response batches (200 responses total), so it is not a single
federated round. Both isolated workers verified identical input SHA-256:
`d4b478a109646fe79ecb37f314f755a9e2d3380ed4704e136b6f9ae36fb9e91c`.

| Work on the paired input batches | Median elapsed seconds |
|---|---:|
| Current v15.4 feature extraction + LOO measurements + screening/gates + fresh-cycle transition | 0.879661 |
| STD-DAGMM preparation + pretrained inference | 0.740033 |
| STD-DAGMM preparation + fresh five-epoch fitting + mixture finalization + inference | 27.232497 |

Our measured time is **3.23%** of the five-epoch fit-plus-score time: **96.77%
less elapsed time in this particular comparison**. In contrast, ours takes
**18.87% more time than the already-fitted baseline's preparation/inference**.
Neither comparison is a universal detector speedup or an estimate of total
federated-round overhead. Deployment retraining frequency and the useful
lifetime of a fitted baseline would need separate evaluation.

| Process memory, sampled every 20 ms | v15.4 worker | STD-DAGMM worker |
|---|---:|---:|
| Pre-detector baseline, including common input tensors (MiB) | 358.66 | 356.62 |
| Maximum sampled process RSS (MiB) | 368.11 | 1,629.99 |
| Additional sampled RSS over that worker's baseline (MiB) | 9.45 | 1,273.37 |
| Minimum system available memory during that worker (MiB) | 2,705.19 | 1,530.38 |

Memory peaks include warmup and all phases; STD's inference-only memory was
NOT isolated. Sampling can miss short peaks. Allocator behavior and process
libraries are included, so these are not exact tensor-memory bounds. At least
about 1.49 GiB of system RAM remained available during the STD worker's samples.
The benchmark completed without out-of-memory errors; paging was not measured.
The full parent workflow took 103.56 seconds, including subprocess startup.

## Workload and reproduction choices

- Windows, i7-8700 (6 cores/12 threads), approximately 11.8 GiB usable RAM;
  PyTorch 2.14.0+cpu, Python 3.11.9. No GPU or dependency installation required.
- Synthetic unlabelled Gaussian full-update vectors, with independent
  lognormal client-scale variation (log scale standard deviation 0.25), added
  to the initialized MNIST model. No private data, actual FR1--FR4 behavior,
  attacker labels, known attack proportion, or detection cutoff is used.
- Our worker calls the unchanged current v15.4 code and the real norm, layer
  profile, fingerprint and flattening helpers. It measures only one selected
  A/B-pair workload per repetition, not feature work for all ten cycle rounds.
  Trap generation, scheduling, local training, aggregation, transport, research
  logging and long-term trajectories are excluded. One warmup repetition is
  excluded from timing, not from peak-memory sampling.
- The full-update autoencoder is `P-128-64-32-64-128-P`, with 53,200,243 total
  detector parameters including the estimation network. Reconstruction and
  input standard deviation feed the mixture network alongside latent features.
  No input projection, layer selection or few-scalar substitution is used.
- Widths 128/64/32, three mixtures and loss weights 0.1/0.005 follow the FRIDA
  paper's baseline description. Symmetric decoder, estimation width 10,
  dropout 0.5, Adam 0.001, batch size 20, gradient clipping at norm 5, five
  epochs, and population-STD convention are explicit pilot choices. They are
  NOT a verified original training-to-convergence recipe. Inputs are not
  standardized or normalized before the autoencoder.
- The 35-dimensional mixture uses float64 Cholesky/log-sum-exp calculations
  and covariance ridge 1e-6 for numerical stability; the large autoencoder is
  float32. The ridge is not a classification threshold.
- A fresh baseline is fitted independently to each 100-client batch, then its
  mixture is re-estimated globally. One inference warmup is excluded; median
  of three scoring repetitions is retained per fit. This measures fit cost
  without asserting that a deployment must refit every round.
- All scores, losses and tested gradients were finite. This does NOT establish
  convergence, useful anomaly separation, or detection accuracy.

Sources:
[original STD-DAGMM paper](https://arxiv.org/pdf/1911.12560),
[FRIDA baseline description](https://arxiv.org/html/2410.05020v2).
`comparison/std_dagmm.py` is independently implemented, paper-guided code, not
author code. The legacy `benchmark_detectors.py` / contribution-based FRAD
reproduction was not used or modified.

## Files and reproduction

`summary.json` records timing percentages, environment, limitations and source
hashes; `ours.json` / `std.json` retain all raw trial timings and sampled memory;
the corresponding `.log` files retain progress. No full vectors, model weights
or large checkpoints are retained. Existing completed FL results are untouched.

Use a fresh output directory to reproduce; the launcher rejects existing runs:

```powershell
.\.venv\Scripts\python.exe benchmark_mnist_std_dagmm.py --clients 100 --epochs 5 --batch-size 20 --repeats 3 --threads 6 --seed 42 --output analysis/mnist_std_dagmm_pilot_repeat
```

Validation: `tests/test_mnist_std_benchmark.py` — 7 tests passed, including
Gaussian-mixture energy agreement, finite joint gradients, full-vector
flattening, missing-pair rejection and preservation of negative time savings.

Next step for paper-grade claims: real recorded full updates, workload/training
budget sensitivity, isolated phase-memory measurements, matched no-detector
FL timing, actual evaluation schedules and detection utility. Do not divide
these synthetic timings by historical MNIST round times and label the result
as measured FL overhead.
