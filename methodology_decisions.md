# Free-Rider Detection Methodology and Design Decisions

## Purpose

This document records the decisions made while reviewing
`false_detection_analysis-1.md` and refining the simulator. It distinguishes the
implemented method from discarded interpretations and explains the reasoning.

## Clarification: "MD" did not mean Mahalanobis distance

An earlier interpretation treated "MD" as Mahalanobis distance. The intended
reference was the Markdown analysis file. Mahalanobis scoring has therefore been
removed completely. The implemented statistical detector is based on robust
z-scores using the median and median absolute deviation (MAD).

Cosine similarity is retained only as a logged diagnostic. It is never compared
with a threshold and cannot flag, penalize, remove, or select a client.

## Attack-type-independent combined detector

The server does not read the simulator's `attack_type` or the ground-truth
free-rider labels. Every client passes through the same combined rule.

For update norms:

```text
norm_median = median(client update norms)
norm_MAD    = median(abs(norm - norm_median))
norm_scale  = max(norm_MAD, 0.05)
norm_z      = (norm - norm_median) / norm_scale
```

For losses:

```text
loss_median = median(client losses)
loss_MAD    = median(abs(loss - loss_median))
loss_scale  = max(loss_MAD, loss_mad_floor)
loss_z      = (loss - loss_median) / loss_scale
```

The unified decision is:

```text
flag = near_zero_update
       OR norm_z > 3
       OR (observation_round <= 6 AND norm_z < -2 AND loss_z > 2)
```

- Near-zero updates target static/no-update behavior such as FR1.
- The large positive norm-z branch targets FR2.
- The low-norm AND high-loss branch targets FR3 during the empirically useful
  early-loss window.
- Adding the FR3 branch does not disable or weaken the FR2 branch; they are OR
  conditions evaluated for every client.
- Low norm alone and high loss alone are deliberately insufficient for the FR3
  branch, reducing honest false positives.

No percentile or quantile is used. Median and MAD still require order-statistic
selection internally, but the implementation does not rank clients for the
detection decision.

## Why the MAD floor and penalty decay are necessary

The analysis found that very small MAD values made minor honest norm differences
look extreme. The real `mad_floor=0.05` prevents this scale collapse.

An isolated honest anomaly can still occur, so a passed detection check subtracts
`penalty_decay=1` without allowing the cumulative penalty to become negative.
Repeated consistent anomalies therefore accumulate while occasional honest
outliers recover.

## Coverage sweep protocol

Coverage is evaluated as a complete experiment, not as unrelated per-round
decisions:

1. At the beginning of a coverage sweep, the server creates one trap model.
2. The exact trap-model weights are frozen for the complete sweep.
3. Active clients are randomly partitioned into small groups.
4. One group receives the frozen trap model per round.
5. The server stores each trapped client's delta, loss, and observation round.
6. No coverage client is flagged, penalized, or decayed during an incomplete
   sweep.
7. After the last group responds, median/MAD statistics are calculated over the
   complete set of stored coverage responses.
8. The combined detector is applied and all coverage penalties are assigned.
9. The frozen model and stored evidence are cleared.
10. A later coverage sweep creates a different frozen trap model.

This prevents an unlucky group containing a majority of free riders from defining
its own baseline. It also ensures that all clients in one coverage sweep are
compared after receiving the same model, rather than different random models.

The normal global model may continue evolving during the sweep, but trapped
updates are measured relative to the exact frozen model they received and are
excluded from global aggregation.

## Warm-up and the FR3 window

The analysis shows that FR3 loss is most separable during rounds 1-6 and overlaps
honest loss later. Detection therefore remains active during trap-selection
warm-up, when every active client in a round receives the same normal global
model. This preserves the early FR3 signal even though formal coverage begins
after warm-up by default.

For deferred coverage results, each client's stored observation round—not the
round in which the sweep finishes—determines whether its loss is eligible for the
rounds 1-6 rule.

## Suspicion phase and anchors

Suspicion-weighted selection prioritizes clients with accumulated penalties while
adding clients with the fewest historical flags and lowest penalties as anchors.
A falsely flagged client is therefore deprioritized as an anchor because its
historical flag count does not decay.

Anchors and reference vectors affect cosine diagnostics only. They do not define
the norm-z/MAD or loss-z/MAD flag rules, so a missed free rider selected as an
anchor cannot poison the active detector through cosine similarity.

## Penalties and removal

- Near-zero update: `penalty_zero_update` (default 4).
- Flag while trapped: `penalty_trap_flag` (default 2).
- Flag while not trapped: `penalty_normal_flag` (default 1).
- High-confidence early low-norm/high-loss evidence uses
  `ceil(removal_threshold / loss_check_rounds)` (never below the applicable
  ordinary flag penalty). This lets consistent FR3 evidence reach removal before
  its six-round signal disappears and scales correctly for 100- or 200-round runs.
- Passed evaluated check: subtract `penalty_decay` (default 1).
- Remove when cumulative penalty is greater than or equal to the configured
  removal threshold.

Trapped updates are excluded from aggregation regardless of their flag result.

## Logged evidence

`client_metrics.csv` records the diagnostic cosine value, delta norm, norm z-score,
norm median/MAD, loss z-score, loss median/MAD, detection reason, stored coverage
observation round, and loss used for detection. This makes later false-positive
analysis reproducible and distinguishes the observation round from the deferred
decision round.

## Known limitations

- Median/MAD assumes honest clients remain a strict majority. With 50% or more
  attackers, the robust baseline can itself represent malicious behavior.
- FR3 becomes statistically close to honest participation after the early loss
  window. Late FR3 detection remains inherently limited by the available
  server-side signals.
- Non-IID clients can naturally have higher losses. Requiring both low norm and
  high loss, plus cumulative penalties and decay, mitigates but does not eliminate
  this risk.
- Detection quality and global accuracy must still be validated across FR1-FR4,
  multiple free-rider percentages, non-IID settings, and multiple random seeds.
