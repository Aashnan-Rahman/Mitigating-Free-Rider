# SPARC-FL revision tracker

Last updated: 17 November 2026, 18:40 (Asia/Dhaka machine time).
This file is the single place to track the response to the v7.1 review: what is
done, what is running, what is deliberately not done, and roughly when the queue
finishes. Keep the same file on both branches.

| Branch | Holds | Notes |
|---|---|---|
| `v15.4-completed-study` | Experiment code, plans, registrations, launcher | **This checkout must stay on this branch.** The Windows recovery task runs from it. |
| `v15.4-paper-version` | Paper versions (v7.3, v7.4), reviewer response | Edit from a separate worktree. Do not switch the experiment checkout. |

## 1. Reviewer concerns

Status key: **Done** = in the v7.4 manuscript. **Queued** = registered and
scheduled below. **Argued** = answered by analysis, not experiment. **Open** =
neither.

| Concern | Request | Status | Where / phase |
|---|---|---|---|
| M1 | Traps vs same statistics without traps | **Done** at 40%, **Queued** at 30% | v7.4 §V-H, Table VI, Fig. 6; phase `review2_07` |
| M1 | Norm-only, profile-only, send-back-only, no-memory | **Queued** | `review3_02` (64 runs) |
| M1 | Frozen model with zero perturbation (is it the noise or the freezing?) | **Queued** | `review3_01` (16 runs) |
| M2 | 5/10/20% prevalence | **Done** | v7.4 §V-G, Table V |
| M2 | Cohort minimum in abstract | **Done** | v7.4 abstract |
| M2 | Norm-matched FR4 (full model), mixed strategies | **Queued** | `review3_03` (8 runs) |
| M2 | Fraboni disguised free rider, Zhu scaled delta | **Queued** | `review2_05` (16 runs) |
| M2 | S2-WEF adaptive attack | **Open** | Needs WEF client protocol (see §3) |
| M3 | Working detection baseline | **Argued** + STD-DAGMM validation **Queued** | §3 below; `review3_00b` |
| M3 | Simple norm threshold | **Done** | v7.4 §V-H, MAD column |
| M3 | Cosine threshold | **Argued** | §3 below |
| M4 | Absolute ms, server-only share, withheld training as cost | **Done** | v7.4 abstract, §V-D, §V-K |
| M4 | Scaling to N = 100/500/1,000 | **Queued** | `review3_00` analysis job (synthetic) |
| M4 | Explain 8.95 s CIFAR-10 training gap | **Open** (disclosed) | Records cannot identify cause |
| M5 | Honest-only runs | **Done** (4) | v7.4 §V-G |
| M5 | Dirichlet α = 0.1 and 1.0 | **Queued** | `review3_04` (12 runs) |
| M5 | Run-level uncertainty | Partly done, **Queued** | Held-out seeds `review2_06` |
| M6 | References and positioning | **Done** | v7.4 §II |
| Minor 1–6 | Presentation | **Done** | v7.4 |

## 2. Experiment queue

Executable queue: `configs/review3_priority_queue_amended_20261117.json`, selected by
`configs/active_experiment_schedule.json`. It is the registered review3 order
(`configs/review3_priority_queue.json`, unchanged and hash-registered) with the
passive 30% amendment inserted after the 40% passive phase. Supervisor:
`run_review3_batch.py`. RAM launch guard: 0.75 GiB (MNIST), 1 GiB (CIFAR-10).

Times are estimates from measured run lengths (MNIST ≈ 1.1–1.25 h, CIFAR-10 ≈
2.5–2.8 h per 100-round run, honest-only runs longer). They assume no power cuts.
The machine logged 37 unexpected shutdowns between 5 and 16 November, so expect
slippage.

| # | Phase | Runs | Purpose | Est. hours | Est. finish | Status (17 Nov) |
|---|---|---:|---|---:|---|---|
| 1 | `review2_01` honest-only | 4 | M5 | – | – | Done |
| 2 | `review2_02` low prevalence | 48 | M2 | – | – | Done |
| 3 | `review2_03` passive 40% | 16 | M1 | – | – | Done |
| 4 | `review2_07` passive 30% | 16 | M1 at both prevalences | 32 | 19 Nov | Running since 17 Nov 18:35 |
| 5 | `review3_00` analysis job | 1 | M4 scaling, MAD, timing | 1 | 19 Nov | Queued |
| 6 | `review3_00b` STD-DAGMM Lin setting | 2 | M3 validation | 1 | 19 Nov | Queued |
| 7 | `review3_01` zero-perturbation control | 16 | M1 | 28 | 20 Nov | Queued |
| 8 | `review3_02` component/memory arms | 64 | M1 | 114 | 25 Nov | Queued |
| 9 | `review2_05` published attacks | 16 | M2 | 28 | 26 Nov | Queued |
| 10 | `review3_03` norm-matched and mixed attacks | 8 | M2 | 14 | 26 Nov | Queued |
| 11 | `review3_04` heterogeneity α 0.1/1.0 | 12 | M5 | 25 | 27 Nov | Queued |
| 12 | `review3_05` γ sweep (30 rounds) | 32 | Sensitivity | 17 | 28 Nov | Queued |
| 13 | `review2_04` oracle utility reference | 12 (3 done) | M4 utility split | 20 | 29 Nov | Paused, resumes here |
| 14 | `fedavg_mnist_baseline_seed73` | 16 | Utility pairs | – | – | Done |
| 15 | `fedavg_mnist_baseline_seed43` | 16 (1 done) | Utility pairs | 18 | 30 Nov | Queued |
| 16 | `review2_06` held-out seeds | 70 | Run-level variation | 124 | 5 Dec | Queued, last |
| | **Total remaining** | **≈ 301** | | **≈ 422 h** | **≈ 5 Dec** | |

Paper-relevant checkpoints: phases 4–6 by about 19 Nov, phase 8 (component
ablations) by about 25 Nov, phases 9–11 (attacks, heterogeneity) by about 27 Nov.

## 3. Detection baselines: decision and argument

Goal: a **lightweight, update-only** detector. The server sees only returned
models. It does not change what clients train on, ask clients for extra reports,
or fit a large auxiliary model. We compare methods on these properties instead of
re-implementing methods that need a different protocol. Claims below use only the
published designs as described in our related work and our own measurements.

| Method | What it needs beyond returned models | Conflict with the target setting |
|---|---|---|
| STD-DAGMM (Lin et al.) | Fits an autoencoder + GMM on full update vectors each round | Cost: first encoder layer alone is P × 128 weights, i.e. 128× the audited model (26.5 M for MNIST, 79.5 M for CIFAR-10). Measured fitting 15.76 s / 42.09 s per round vs 0.215 s / 0.791 s checking for SPARC-FL. Only N = 100 samples of dimension P ≫ N per fit. |
| FRIDA (Recasens et al.) | Honest clients train on server-supplied canaries (membership variant), or the server infers dataset properties (property variant) | Injects server data into client training and changes the local objective. Property inference extracts information about private data by design. Server evaluates every client model on canaries each round. |
| FRAD (Wang et al.) | Client-reported computation, communication, resources, contribution and reputation, plus a learned detector | Relies on self-reported information a free rider controls, and adds auxiliary learning. |
| PASS (Wang et al.) | Clients evaluate peers' models on local data | Exposes models to other clients and adds client-side evaluation work. Low peer utility can reflect heterogeneity. |
| WEF-defense / S2-WEF | Clients compute and upload weight-evolution matrices. S2-WEF also simulates attack patterns on the server | Extra client computation and upload. The matrix is reported by the client and cannot be checked against the returned model alone. Extra server simulation for S2-WEF. |
| FLET | Test tasks and a game-theoretic mechanism | Additional client work outside ordinary training. |
| FLoomChecker, proof-of-learning | Training-integrity evidence produced during training | Extra client computation, storage and verification artifacts. |
| Norm threshold (one-round MAD) | Nothing | **Measured.** No honest flags, but full recall in only 5/16 settings at 40% (Table VI). |
| Cosine threshold | Nothing | **Argued, not measured.** FR4 adds the average of recent global changes, so its direction follows the global trend and stays close to honest updates. FR1 returns a zero vector with undefined cosine. Non-IID honest clients have lower cosine. A cosine cut-off therefore cannot separate FR4 without flagging heterogeneous honest clients. |

Not claimed: that SPARC-FL detects better than these methods in a matched
benchmark. The claim is near-complete removal at ≥10% prevalence using only
returned models, at measured server cost below 1 s per round at N = 100.

## 4. Change log

- **17 Nov 2026**
  - Passive 40% ablation finished. No detection gain from traps. Paper reframed
    as SPARC-FL (v7.4) on `v15.4-paper-version`.
  - Registered `review2_07` (passive 30%) as a dated amendment (`d622139`).
  - Found that the 12 Nov review3 amendment was never activated because the
    experiment checkout was on the paper branch. Switched the checkout to
    `v15.4-completed-study`. Verified all 22 registered sources are identical
    across branches. All plans validate against both registrations. 32 review2 and
    review3 tests pass.
  - Added the amended queue file (registered review3 queue left untouched) and
    pointed the active schedule at it. Handoff from the paused oracle run at a
    round boundary through the owned stop marker. The new launcher started `review2_07` at 18:35.
  - Disabled the stale "v15.3 Queued Experiments" Windows task.
  - Decided not to re-implement baselines that need a different client protocol.
    See §3.

## 5. Checking progress

```powershell
& ([scriptblock]::Create((Get-Content ./check_status.txt -Raw))) -Once
```

Or open `results/<phase>/experiment_status.json`. Update §2 and §4 when a phase
completes.
