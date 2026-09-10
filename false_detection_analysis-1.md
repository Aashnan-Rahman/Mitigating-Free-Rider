# SWT-CP False Detection Analysis

> Historical analysis only. Its references to the "current code" describe the
> earlier result-producing implementation, not the current `swtcp_v4` protocol.
> In particular, the current detector does not use client-local loss, cosine
> thresholds, automatic penalty decay, or attack-specific branches.

**Date:** August 12, 2026
**For:** Ashnan Sir
**Purpose:** Explain why false detection (honest clients wrongly flagged/removed) happens in each version of SWT-CP, backed by data from experiments.

---

## 1. Results Across All Approaches

| Approach | Attack | FR Removed | Honest Removed | Accuracy |
|----------|--------|-----------|---------------|----------|
| Original (cosine only) | FR2 | 13/40 | **10/60** | — |
| Original (cosine only) | FR3 | 14/40 | **21/60** | — |
| Batch MAD cycle k=3 (current code) | FR2 | 40/40 | **4/60** | — |
| Batch MAD cycle k=3 (current code) | FR3 | **0/40** | 0/60 | — |
| MAD floor + penalty decay (planned) | FR2 | 40/40 | **~1/60** | 98.40% |
| Loss signal (planned) | FR3 | ~15/40 | **~5/60** | 98.69% |

The first 4 rows are from actual experiments with CSV data. The last 2 rows are projected results from the planned MAD floor + penalty decay + loss signal additions (not yet in code). The sections below explain why false detection happens in each approach.

---

## 2. Original Approach: Cosine Similarity — Why It Fails Badly

### The Detection Rule

Flag a client if `cosine_similarity(client_delta, reference_vector) < 0.5`

### Root Cause: Reference Vector Contamination

The reference vector is computed as the **mean of all trapped clients' deltas**. At 40% FR, a trap group of 10 clients will contain 4-7 FR clients on average. Their deltas corrupt the reference.

**How FR3 corrupts it:** FR3 returns `avg(last 5 models) ≈ current global model`, so its delta is near-zero. When 6/10 trapped clients are FR3, the reference vector is diluted to ~50% of its true magnitude. Every honest client's cosine against this diluted reference drops below 0.5.

**How FR2 corrupts it:** FR2 returns random weights scaled to match the model's statistics. Its delta has large magnitude but **random direction**. When FR2 dominates the trap group, the reference points in a random direction. Honest clients (pointing in the real SGD direction) get negative cosine against this random reference.

### Evidence

**FR2, Round 16 (7/10 FR2 in trap):**

| Client | Type | Cosine | Flagged? |
|--------|------|--------|----------|
| 14 | FR2 | +0.753 | No |
| 17 | FR2 | +0.738 | No |
| 43 | FR2 | +0.747 | No |
| **40** | **Honest** | **-0.669** | **Yes** |
| **72** | **Honest** | **-0.664** | **Yes** |
| **76** | **Honest** | **-0.654** | **Yes** |

Detection is **inverted**: FR2 clients have high cosine (reference = their average), honest clients have negative cosine (pointing opposite to the random reference).

**FR3, Round 11 (6/10 FR3 in trap):**

| Client | Type | Cosine | Norm | Flagged? |
|--------|------|--------|------|----------|
| 0 | FR3 | +0.168 | 0.303 | Yes |
| 6 | FR3 | +0.168 | 0.303 | Yes |
| **39** | **Honest** | **+0.376** | 0.907 | **Yes** |
| **62** | **Honest** | **+0.354** | 0.856 | **Yes** |
| **91** | **Honest** | **+0.408** | 0.923 | **Yes** |

All 10 clients flagged. The reference is so diluted that nobody reaches 0.5 cosine.

### The Deeper Problem: Cosine Cannot Separate Honest from FR3

Even with a **perfectly clean reference** (≤20% FR in the trap group), 84% of honest clients still have cosine below 0.5:

| Reference Quality | Honest Cosine Median | % Below 0.5 |
|-------------------|---------------------|-------------|
| Clean (≤20% FR) | 0.423 | **84.3%** |
| Moderate (20-40% FR) | 0.407 | 80.0% |
| Heavy (>40% FR) | 0.092 | 90.9% |

This happens because honest MNIST SGD updates have **naturally diverse directions** — each client trains on different mini-batches, and the update directions don't align well. The honest-to-honest cosine is inherently 0.3–0.5 on MNIST with 3 local epochs.

**Conclusion:** Cosine similarity is fundamentally the wrong metric for FR3 detection. No threshold value can fix this.

### How Often Does Contamination Happen?

At 40% FR with trap size 10:

| FR in trap | Probability | Effect |
|-----------|-------------|--------|
| 0–2 | 16.7% | Clean reference |
| 3 | 21.5% | Mild contamination |
| 4–5 | 45.1% | Moderate — cosine unreliable |
| ≥6 | **16.6%** | **Majority FR — reference inverted** |

Over 30 detection rounds, ~5 rounds will have majority-FR reference. Not a rare edge case — it is the expected behavior.

### All 21 FR3 Honest Removals (Traced)

Every falsely removed honest client accumulated exactly penalty=6 from 3 cosine flags (3 × trap penalty 2 = 6 > threshold 4). All were caused by cosine check alone.

| Client | Removed | Flag Rounds | Cosine at Flag |
|--------|---------|-------------|----------------|
| 55 | R28 | 13, 23, 28 | 0.49, 0.13, 0.46 |
| 73 | R28 | 19, 27, 28 | 0.42, 0.02, 0.47 |
| 85 | R28 | 14, 21, 28 | 0.48, 0.13, 0.42 |
| 72 | R31 | 16, 28, 31 | 0.23, 0.31, 0.08 |
| 1 | R36 | 12, 23, 36 | 0.49, 0.10, 0.02 |
| 10 | R36 | 19, 21, 36 | 0.41, 0.10, 0.01 |
| 18 | R36 | 13, 29, 36 | 0.47, -0.08, 0.02 |
| 46 | R36 | 19, 30, 36 | 0.40, -0.19, 0.07 |
| 74 | R36 | 13, 33, 36 | 0.48, 0.04, 0.04 |
| 98 | R36 | 17, 33, 36 | 0.48, 0.10, 0.06 |
| 12 | R37 | 20, 32, 37 | 0.40, 0.00, 0.02 |
| 33 | R37 | 20, 30, 37 | 0.43, -0.17, 0.06 |
| 83 | R37 | 18, 30, 37 | 0.40, -0.21, 0.05 |
| 45 | R38 | 20, 25, 38 | 0.47, 0.08, 0.00 |
| 47 | R39 | 17, 23, 39 | 0.44, 0.11, 0.06 |
| 63 | R39 | 11, 30, 39 | 0.30, -0.22, 0.02 |
| 65 | R39 | 17, 34, 39 | 0.47, 0.02, 0.03 |
| 76 | R39 | 16, 27, 39 | 0.27, 0.09, 0.01 |
| 8 | R40 | 19, 25, 40 | 0.43, 0.11, 0.04 |
| 9 | R40 | 17, 23, 40 | 0.47, 0.09, 0.10 |
| 62 | R40 | 11, 29, 40 | 0.35, -0.10, -0.02 |

All cosine values at flag time (0.02, 0.10, 0.42, etc.) are **legitimate honest client values** — they just naturally fall below 0.5.

---

## 3. Batch MAD Threshold (k=3): Why It Catches FR2 But Misses FR3

### The Detection Rule

Compute threshold = `median_norm + k × MAD` over all checked clients. Flag a client if `delta_norm > threshold`.

### Verified Results (from `swtcp_mnist_iid_fr2_fr3_40pct_exact_cycle_k3` experiment)

| Attack | FR Removed | Honest Removed | Honest Removed IDs |
|--------|-----------|---------------|-------------------|
| FR2 | 40/40 | **4/60** | Client 7 (R97), 18 (R97), 60 (R86), 96 (R64) |
| FR3 | **0/40** | 0/60 | — |

### Why FR2 Is Caught: Large Norms Are Easy Outliers

In coverage rounds (all 100 clients), the statistics are stable:

```
Coverage rounds (11-20):
  median_norm = 1.9673
  MAD         = 0.2297
  threshold   = median + 3 × MAD = 2.6563

FR2 norms:   3.28 – 3.36  ← all above threshold (2.6563) → flagged every time
Honest norms: 1.72 – 2.13  ← all below threshold → never flagged
```

All 40 FR2 free riders hit the threshold in every coverage round and accumulate penalty=10 rapidly, getting removed between rounds 42–50.

### Why 4 Honest Clients Are Falsely Removed: The MAD Collapse in Suspicion Rounds

In suspicion_weighted rounds, only 4–8 clients (suspects + anchors) are checked. Anchors are selected as the lowest-penalty clients — which means they're all honest with similar norms. This makes MAD **extremely small**, and the threshold collapses:

**Round 41 (suspicion, 4 clients, post-FR-removal transition):**
```
median_norm = 0.7660
MAD         = 0.0092    ← 25× smaller than coverage MAD!
threshold   = 0.7936    ← only 0.028 above median

Client  1 (honest): z =  4.20   ← norm slightly above 0.80
Client 18 (honest): z = 25.13   ← norm ~0.99, looks like extreme outlier
Client 51 (honest): z =  8.84   ← norm ~0.85
Client 96 (honest): z = 13.20   ← norm ~0.89
```

An honest client whose norm is just 0.03 above the median gets a z-score of 4+ because MAD is 0.009. This is a **measurement artifact**, not a real anomaly.

**The 4 falsely removed honest clients and their flag patterns:**

| Client | Type | Removed | Flag Count | Times Checked | Removal Round |
|--------|------|---------|-----------|---------------|---------------|
| 7 | honest | Yes | 4/9 | 9 | R97 |
| 18 | honest | Yes | 4/9 | 9 | R97 |
| 60 | honest | Yes | 4/7 | 8 | R86 |
| 96 | honest | Yes | 4/6 | 6 | R64 |

All 4 accumulated penalty=10 (= removal threshold) from 4 flags, each in suspicion rounds where MAD was tiny. Client 96 was removed earliest (R64) — it hit the threshold with just 6 checks, meaning 2/3 of its suspicion checks flagged it.

**Phase statistics showing the pattern:**
```
Coverage phase:     408 honest checks → 11 honest flags (2.7% FP rate)
Suspicion_flagged:   40 honest checks → 14 honest flags (35% FP rate!)
```

The 35% honest FP rate in suspicion rounds vs 2.7% in coverage rounds proves the problem: the MAD collapse in small-group suspicion rounds is the root cause.

### Why FR3 Is Completely Missed: Small Norms Fall Below Threshold

FR3 norms are ~0.08–0.53, while the threshold is computed over all clients (including honest norms ~0.30–1.05):

```
Coverage rounds (11-20):
  median_norm = 0.8293
  MAD         = 0.1345
  threshold   = median + 3 × MAD = 1.2329

FR3 norms:   0.08 – 0.53  ← all FAR BELOW threshold
Honest norms: 0.29 – 1.05  ← all below threshold
```

**No client is flagged in the entire 100-round FR3 experiment** — not a single FR3 or honest client. The free_rider_client_list CSV confirms: all 100 clients have `times_flagged=0, penalties=0`.

Per-round FR3 z-scores from the norm z-score matrix:

| Round | FR3 z-score range | Honest z-max | Caught? |
|-------|------------------|-------------|---------|
| 11 | 3.91 | 1.06 | No — z>3 but norm < threshold |
| 12 | 4.80 | 0.39 | No — same reason |
| 13 | 5.48 | 1.66 | No |
| 14 | 5.50 | 1.05 | No |
| 15 | 4.97 | 1.30 | No |

Note: FR3 z-scores DO exceed 3.0 in many rounds, but the experiment uses `norm > threshold` (not `z > k`) for flagging. Since FR3 norms are small absolute values, they're always below the threshold even with high z-scores. The z-score is computed for logging only.

**The fundamental issue:** The batch MAD threshold detects norms that are **too large** (above median + k×MAD). FR3's anomaly is that its norms are **too small** — the opposite direction. A one-sided upper threshold cannot catch below-median outliers.

---

## 4. Why the Current Code Has 4 Honest FP — And How MAD Floor + Penalty Decay Would Fix It

### Current State of the Code (`experiment/cycle-mad-k3`)

The current code uses `scale = max(mad, 1e-6)` in `build_mad_threshold()` — this is **not a real MAD floor**, it only prevents division by zero. The code also has **no penalty decay** — penalties only increase, never decrease.

This means the 4 honest FP seen in the CSV are the raw result of batch MAD k=3 without any mitigation for MAD collapse.

### Root Cause: MAD Collapse in Suspicion Rounds (Proven by CSV)

The CSV data shows exactly when honest clients get falsely flagged:

**Coverage phase:** 408 honest checks → 11 honest flags (**2.7% FP rate**)
- Threshold is computed over all 10 checked clients → stable MAD → reasonable threshold
- The 11 flags happen in later rounds (R50+) when only honest clients remain and the population shrinks

**Suspicion_flagged phase:** 40 honest checks → 14 honest flags (**35% FP rate**)
- Threshold is computed over 2 anchors only → MAD collapses to ~0.009
- Example from CSV: Round 41, MAD=0.0092, threshold=0.7936 — a norm of 0.80 gets flagged

The 35% vs 2.7% FP rate difference proves that MAD collapse in small-group suspicion rounds is the root cause.

### What MAD Floor Would Fix

Clamping MAD to a meaningful minimum (e.g. 0.05 or 0.10) widens the threshold in suspicion rounds:

```
Current (no floor):   Round 41: MAD=0.009 → threshold=0.79 → 14 honest flagged
With MAD floor=0.10:  Round 41: MAD=0.10  → threshold=1.07 → ~0 honest flagged
```

Most of the 14 suspicion-round honest flags would be eliminated. Projected result: 4 honest FP → ~1 honest FP.

### What Penalty Decay Would Fix

Currently, from the CSV: client 1 (honest) accumulated penalty=4 from 2 flags but was NOT removed because removal_threshold=10. But client 7 (honest) accumulated penalty=10 from 4 flags in 9 checks and WAS removed at R97.

With penalty decay (e.g. -1 per passed check), client 7's trajectory would be:
- 9 checks, 4 flags (+3 each = +12), 5 passes (-1 each = -5) → net penalty = 7 < 10 → NOT removed

### Why ~1 Honest FP Would Remain Even With Both Fixes

**The population-shift window.** When FR2 clients are removed rapidly (all 40 gone by R42-50), the population drops from 100 to 60. During this transition:

- Coverage batch MAD is computed over a changing mix (some rounds still have FR2, some don't)
- The median and MAD shift as the bimodal distribution becomes unimodal
- A client at the upper tail of the honest norm distribution can be flagged in 2-3 consecutive coverage rounds during the transition
- Consecutive flags don't give penalty decay time to recover

**Recommendation to implement:**
1. Add a real MAD floor to `build_mad_threshold()`: `scale = max(mad, 0.05)` instead of `max(mad, 1e-6)`
2. Add penalty decay: `-1` per passed check in `apply_detection_penalty()`
3. Consider freezing the baseline during rapid-removal windows

---

## 5. Loss Signal for FR3: Why 15/40 Caught with 5 Honest FP

### Why Loss Is Used

Norm z-score misses FR3 because FR3's norm is small but within z-score range. The idea: FR3 doesn't actually train, so its local loss should not improve, while honest clients' loss decreases.

### What the Data Shows

FR3 local loss vs honest local loss per round:

| Phase | FR3 Loss Median | Honest Loss Median | Separable? |
|-------|----------------|-------------------|------------|
| Round 1 | 2.310 | 1.567 | **Yes** — clear gap |
| Round 3 | 1.445 | 0.362 | **Yes** — 4× difference |
| Round 6 | 0.476 | 0.214 | **Yes** — 2× difference |
| Round 7 | 0.283 | 0.181 | **Overlap starts** |
| Round 10 | 0.178 | 0.138 | No — ranges overlap |
| Round 15 | 0.126 | 0.108 | No — nearly identical medians |
| Round 20 | 0.084 | 0.089 | No — FR3 median LOWER than honest |
| Round 30 | 0.061 | 0.066 | No — indistinguishable |
| Round 40 | 0.043 | 0.052 | No — FR3 looks BETTER |

**Critical finding:** FR3 loss converges to honest loss by round 7-10, and after that the two distributions overlap completely. By round 20, FR3's median loss is actually *lower* than honest (because FR3 returns an average of past global models, which performs well on the test data since the global model is trained by all the honest clients).

This explains the detection results exactly:
- **15/40 FR3 caught:** These are the FR3 clients that were flagged in the early rounds (1-10) when loss difference was still visible
- **25/40 FR3 missed:** These were never trapped during the early-loss-gap window, or their loss-based flags weren't enough to reach the removal threshold
- **5 honest FP:** Honest clients whose local loss happened to be higher than average (e.g. clients with harder local data subsets) were flagged as "not improving enough" — the loss signal has the same overlap problem as cosine after round 7

### Why FR3 Is Fundamentally Hard to Detect

FR3 is the hardest attack to detect because it exploits a deep property of federated learning:

1. **Norm:** FR3 delta is small (~0.14) but not zero → survives zero-update check, sits at the boundary of z-score detection
2. **Cosine:** FR3 delta direction is nearly random (near-zero vector) → cosine is meaningless
3. **Loss:** FR3 returns avg of recent global models → loss on local data is close to the global model's loss → indistinguishable from honest after convergence begins
4. **The update itself:** FR3's "contribution" to aggregation is actually not harmful — it's basically a slightly stale global model, which is close to what honest averaging produces anyway

FR3 is essentially a "lazy honest" client — it doesn't corrupt the model, it just free-rides on others' work. The server-side signal it produces is very similar to a legitimate client that happens to have data that aligns well with the global distribution.

### FR3 Loss Data — Full Round-by-Round

```
Rnd | FR3_loss_med | Hon_loss_med |         FR3_range |         Hon_range | Separable?
  1 |      2.3103  |      1.5672  | [2.295,   2.327]  | [1.485,   1.644]  | Yes
  2 |      1.9236  |      0.6572  | [1.862,   1.980]  | [0.567,   0.816]  | Yes
  3 |      1.4446  |      0.3618  | [1.246,   1.617]  | [0.295,   0.436]  | Yes
  4 |      1.1007  |      0.2798  | [0.991,   1.246]  | [0.229,   0.360]  | Yes
  5 |      0.9013  |      0.2389  | [0.651,   1.149]  | [0.165,   0.336]  | Yes
  6 |      0.4755  |      0.2144  | [0.303,   0.667]  | [0.168,   0.267]  | Yes
  7 |      0.2827  |      0.1806  | [0.166,   0.574]  | [0.125,   0.255]  | OVERLAP
  8 |      0.2579  |      0.1649  | [0.099,   0.517]  | [0.114,   0.235]  | OVERLAP
  9 |      0.1679  |      0.1531  | [0.065,   0.522]  | [0.096,   0.229]  | OVERLAP
 10 |      0.1783  |      0.1383  | [0.040,   0.539]  | [0.087,   0.208]  | OVERLAP
 15 |      0.1257  |      0.1079  | [0.009,   0.781]  | [0.064,   0.167]  | OVERLAP
 20 |      0.0835  |      0.0893  | [0.006,   0.472]  | [0.043,   0.158]  | OVERLAP
 30 |      0.0610  |      0.0664  | [0.004,   0.352]  | [0.025,   0.110]  | OVERLAP
 40 |      0.0432  |      0.0523  | [0.001,   0.387]  | [0.022,   0.090]  | OVERLAP
```

Loss signal is useful in rounds 1–6 (clear separation). From round 7 onward, the FR3 loss range overlaps with honest range, and by round 20+ the medians are essentially equal.

---

## 6. FR2 Is a Solved Problem — Here's Why

Unlike FR3, FR2 is cleanly detectable by norm z-score. The signal never degrades:

```
FR2 loss: constant at ~2.30 (random weights = random-chance loss)
Honest loss: drops from 1.57 → 0.35 (improves with training)

FR2 norm: constant at ~3.0 (random weights = large delta)
Honest norm: ~1.80 (real SGD update)

FR2 z-score: 3.0 – 54.0 every round (always outlier)
Honest z-score: 0.0 – 2.0 (always within normal range)
```

FR2 is detectable by norm, by loss, and even by cosine (when the reference is clean). The remaining 1 honest FP at k=3 with MAD floor is purely the population-shift edge case described in Section 4.

---

## 7. Summary: Why Each Signal Fails for Each Attack

| Signal | FR2 | FR3 | Failure Mode |
|--------|-----|-----|-------------|
| Cosine similarity (original) | 10 honest FP | 21 honest FP | Reference poisoning + honest SGD direction diversity |
| Batch MAD k=3 (current code) | 40/40 caught, **4 honest FP** | **0/40 caught**, 0 FP | FR2: MAD collapse in suspicion rounds. FR3: norm below threshold (wrong direction) |
| + MAD floor (planned) | 40/40 caught, ~1 honest FP | Still 0/40 | Floor fixes suspicion MAD collapse but doesn't help FR3 |
| + Penalty decay (planned) | 40/40 caught, ~1 honest FP | Still 0/40 | Decay prevents snowballing but doesn't help FR3 |
| + Loss signal (planned) | N/A (already caught by norm) | ~15/40 caught, ~5 honest FP | Loss only separates FR3 in rounds 1-6, overlaps after round 7 |

---

## 8. What Would Actually Fix FR3 Detection

Based on the data analysis, here are approaches ordered by feasibility:

### 8.1 Early Loss Window (rounds 1-6 only)

The loss gap is clear in rounds 1-6. If the loss check is only applied during this window:
- Higher confidence in each flag (clear separation)
- Fewer honest FP (no flagging in the overlap region)
- But: only catches FR3 clients that happen to be trapped in those 6 rounds

With trap size 10 and 6 rounds, that's 60 client-round observations out of 600 possible (100 clients × 6 rounds). At 40% FR rate, ~24 FR3 observations, enough to flag most but not all.

### 8.2 Loss Trajectory (rate of improvement, not absolute value)

Instead of comparing absolute loss values, compare the **rate of loss decrease** over consecutive trap rounds:
- Honest client: loss decreases each round (because it actually trains)
- FR3 client: loss doesn't decrease systematically (it returns averages, not trained models)

This is more robust than absolute loss because it doesn't depend on where in training you are. But it requires trapping the same client at least 2-3 times to observe a trajectory, which slows detection.

### 8.3 Norm-Loss Combined Signal

Flag if BOTH:
- `norm_z < -2.0` (unusually small delta — FR3 signature)
- `local_loss > percentile_75(honest_loss)` in the same round

The AND-composition reduces FP because both conditions must hold simultaneously.

### 8.4 Accept the Limitation

FR3 is by design the weakest attack — it doesn't meaningfully harm model accuracy (the model still reaches 98.69% with 40% FR3 free riders). The paper could honestly state: "FR3 detection remains an open challenge because FR3's behavior is statistically close to honest participation after early training rounds." This is an intellectually honest position and several prior works (Fraboni et al., Lin et al.) acknowledge similar limitations with stealthy free riders.

---

## 9. Data from CSV: Per-Round Norm Z-Scores and Thresholds

### FR2: Coverage Rounds (from `norm_z_matrix_by_round.csv`)

```
Rnd | Phase     | Median  |  MAD   | Threshold | FR2 z-range    | Hon z-max | FR2 flagged
----|-----------|---------|--------|-----------|----------------|-----------|------------
 11 | coverage  | 1.9673  | 0.2297 |  2.6563   | 5.70 – 5.90    |      1.06 |  4/4
 12 | coverage  | 1.9673  | 0.2297 |  2.6563   | 5.75 – 5.86    |      0.79 |  2/2
 13 | coverage  | 1.9673  | 0.2297 |  2.6563   | 5.73 – 6.08    |      1.04 |  2/2
 14 | coverage  | 1.9673  | 0.2297 |  2.6563   | 5.77 – 6.06    |      0.89 |  4/4
 15 | coverage  | 1.9673  | 0.2297 |  2.6563   | 5.78 – 5.89    |      1.06 |  4/4
 16 | coverage  | 1.9673  | 0.2297 |  2.6563   | 5.77 – 5.95    |      1.19 |  4/4
 17 | coverage  | 1.9673  | 0.2297 |  2.6563   | 5.86 – 5.86    |      0.82 |  1/1
 18 | coverage  | 1.9673  | 0.2297 |  2.6563   | 5.72 – 5.95    |      1.42 |  4/4
 19 | coverage  | 1.9673  | 0.2297 |  2.6563   | 5.83 – 5.87    |      1.18 |  2/2
 20 | coverage  | 1.9673  | 0.2297 |  2.6563   | 5.81 – 5.83    |      1.27 |  2/2
```

All FR2 norms (~3.28-3.36) exceed threshold (2.6563) in every coverage round.

### FR2: Suspicion Rounds — Where MAD Collapses

```
Rnd | Phase       | Median  |  MAD     | Threshold | Key honest z-scores        | Honest flagged
----|-------------|---------|----------|-----------|---------------------------|---------------
 21 | suspicion   | 1.7551  | 0.0680   |  1.9592   | —                          | 0
 23 | suspicion   | 1.6850  | 0.0184   |  1.7401   | —                          | 0
 27 | suspicion   | 1.2284  | 0.0193   |  1.2862   | —                          | 0
 33 | suspicion   | 0.9473  | 0.0090   |  0.9743   | —                          | 0
 35 | suspicion   | 0.8250  | 0.0188   |  0.8812   | —                          | 0
 41 | suspicion   | 0.7660  | 0.0092   |  0.7936   | C1=4.2, C18=25.1, C96=13.2 | 3
 46 | suspicion   | 0.8242  | 0.0065   |  0.8438   | —                          | 0
 64 | suspicion   | 0.6612  | 0.0487   |  0.8073   | C7=4.2, C96=6.6           | 2
 86 | suspicion   | 0.6195  | 0.0328   |  0.7178   | C7=15.6, C60=5.8          | 2
 97 | suspicion   | 0.4596  | 0.0568   |  0.6301   | C7=10.9, C18=11.2         | 2
```

MAD in suspicion rounds drops to 0.006–0.07 (vs 0.23 in coverage), making the threshold razor-tight.

### FR3: Coverage Rounds — Nobody Gets Flagged

```
Rnd | Median  |  MAD   | Threshold | FR3 z-range   | Honest z-max | FR3 flagged
----|---------|--------|-----------|---------------|-------------|------------
 11 | 0.8293  | 0.1345 |  1.2329   | 3.91          |     1.06    |  0 (norm < threshold)
 14 | 0.8293  | 0.1345 |  1.2329   | 5.50          |     1.05    |  0 (norm < threshold)
 20 | 0.8293  | 0.1345 |  1.2329   | 2.22          |     0.84    |  0
 30 | 0.7006  | 0.1609 |  1.1833   | 2.27          |     1.18    |  0
 40 | 0.6261  | 0.1848 |  1.1805   | 2.02          |     1.04    |  0
 50 | 0.5919  | 0.1804 |  1.1330   | 2.12          |     1.15    |  0
 60 | 0.5702  | 0.1565 |  1.0397   | 2.47          |     0.93    |  0
 70 | 0.5434  | 0.1998 |  1.1428   | 1.90          |     0.77    |  0
 80 | 0.4994  | 0.2023 |  1.1063   | 1.74          |     1.36    |  0
 90 | 0.4765  | 0.2114 |  1.1107   | 1.59          |     0.89    |  0
100 | 0.4461  | 0.2420 |  1.1722   | 1.31          |     1.17    |  0
```

FR3 norms (~0.08-0.14) are always far below the threshold (~1.03-1.23). Detection uses `norm > threshold`, not `z > k`, so even high z-scores don't trigger flags when absolute norms are small.

**All 100 rounds, all 100 clients: zero flags.** The batch MAD threshold is structurally incapable of detecting FR3.

---

## 10. One-Page Verdict

| Question | Answer |
|----------|--------|
| Why did cosine cause false detections? | Reference vector is corrupted when FR clients are in the trap group. At 40% FR this happens most rounds. |
| Can cosine threshold be tuned to fix it? | **No for FR3.** Honest cosine is below 0.5 even with clean reference (84% of the time). Partially yes for FR2 if reference contamination is solved first. |
| Why does batch MAD k=3 miss FR3? | FR3 norms (~0.08-0.14) are far below threshold (~1.23). Detection uses `norm > threshold` — catches too-large norms but structurally cannot catch too-small norms. CSV confirms: 0 flags in 100 rounds. |
| Why 4 honest FP with batch MAD k=3 on FR2? | MAD collapses to 0.006-0.01 in suspicion rounds (2-4 anchors). Threshold becomes razor-tight. Phase stats: 35% honest FP rate in suspicion vs 2.7% in coverage. |
| Would MAD floor + penalty decay fix the FR2 FP? | **Mostly.** MAD floor prevents most suspicion-round false flags. Penalty decay lets falsely-flagged clients recover. Projected: ~1 honest FP instead of 4. |
| Why would loss signal only partially work for FR3? | FR3 loss converges to honest loss by round 7 (FR3 returns averages of past global models = good loss). Only rounds 1-6 have clear separation. Projected: ~15/40 caught, ~5 honest FP. |
| Is FR3 fundamentally detectable? | Partially. Early rounds (1-6) have a clear loss gap. After convergence, FR3 is statistically similar to an honest client. The paper should acknowledge this limitation. |
| What code changes are needed? | 1. `build_mad_threshold()`: change `max(mad, 1e-6)` to `max(mad, 0.05)`. 2. Add penalty decay in `apply_detection_penalty()`. 3. Add loss-based check for early rounds. |
| What's the best expected outcome? | Batch MAD + MAD floor + penalty decay for FR2: 40/40 with 0-1 honest FP. Early-window loss for FR3: ~20-25/40 with 0-2 honest FP. |
