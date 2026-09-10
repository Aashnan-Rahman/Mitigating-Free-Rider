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

## Attacker information boundary

Attackers are not told the server's trap-selection decision. Their fabrication
interface receives only client-observable information: client identity, round,
the model sent to that client, public configuration, local received-model
history, and local randomness. In particular, there is no `was_trapped` input.

FR1 replays the last received model, FR2 adds a bounded memoryless random update,
FR3 averages its received-model window, and FR4 predicts an update from
consecutive received-model differences plus calibrated noise. Secret trap models
are indistinguishable from other received models and therefore enter attack
history normally.

For update norms:

```text
norm_median = median(client update norms)
norm_MAD    = median(abs(norm - norm_median))
norm_scale  = max(norm_MAD, 0.05)
norm_z      = (norm - norm_median) / norm_scale
```

The unified decision is:

```text
flag = near_zero_update
       OR phase-appropriate robust norm outlier
```

- Near-zero updates target static/no-update behavior such as FR1.
- The large positive norm-z branch targets FR2.
- FR3 and FR4 are tested through the same secret-model probes and statistical
  response rules; the server does not select a detector branch by attack type.
- Client-local accuracy and loss are never trusted detector inputs. They may be
  logged by the simulator for research evaluation only.

No percentile or quantile is used. Median and MAD still require order-statistic
selection internally, but the implementation does not rank clients for the
detection decision.

## Why the MAD floor and dodge rehabilitation are necessary

The analysis found that very small MAD values made minor honest norm differences
look extreme. The real `mad_floor=0.05` prevents this scale collapse.

An isolated honest anomaly can still occur. Automatic per-round penalty decay is
disabled; instead, a suspicious client returns to the unflagged pool after at
least ten frequent probes when no more than ten percent are flagged. This keeps
its accumulated evidence while allowing a consistently normal client to leave
the expensive suspicion path.

## Coverage sweep protocol

The initial coverage is evaluated as a complete experiment, not as unrelated per-round
decisions:

1. At the beginning of a coverage sweep, the server creates one trap model.
2. The exact trap-model weights are frozen for the complete sweep.
3. Active clients are randomly partitioned into small groups.
4. Two distinct groups receive the frozen trap model per round. The randomized
   schedule contains no repeated group-pair and gives every group exactly two
   probes during the sweep.
5. The server stores both of each client's deltas and observation rounds.
6. No coverage client is flagged, penalized, or decayed during an incomplete
   sweep.
7. After the last pair responds, median/MAD statistics are calculated over all
   stored probe responses from the complete sweep.
8. The two decisions are combined per client: each magnitude flag adds one point
   and every near-zero response adds the five-point zero-update penalty.
9. The frozen model and stored evidence are cleared.
10. The initial double sweep is not repeated; later unflagged surveillance uses
    ten single-check groups and a newly frozen model for each ten-round cycle.

This prevents an unlucky group containing a majority of free riders from defining
its own baseline. It also ensures that all clients in one coverage sweep are
compared after receiving the same model, rather than different random models.

The normal global model may continue evolving during the sweep, but trapped
updates are measured relative to the exact frozen model they received and are
excluded from global aggregation.

## Warm-up

Trap selection begins only after warm-up, but the universal exact send-back and
server-observed update checks remain active from round one. No private client
metric is requested or trusted for detection.

## Suspicion phase and anchors

After the initial double-coverage sweep, clients flagged at least once enter a
separate suspicious pool. If `S` clients are suspicious, the server creates
`max(1, floor(S / 10))` groups and distributes every suspicious client among
them; ten is a target group size, not a maximum.

At most ten low-suspicion anchors are selected for a ten-round surveillance
cycle, with up to three assigned to each suspicious group. Suspects and anchors
are reshuffled between groups every round. Every group receives its own newly
generated trap model, and suspect update norms are tested against the median/MAD
interval of the anchors that received that same model. An out-of-range suspect
receives three penalty points. Anchors supply the magnitude baseline but remain
subject to the five-point exact send-back check; a zero-update anchor is excluded
from the group baseline so it cannot collapse the reference.

Independently of the number of suspicious groups, all non-anchor unflagged
clients are partitioned into exactly ten surveillance groups. One group receives
the same frozen surveillance trap per round and is excluded from aggregation.
After all ten groups have been processed, their responses are evaluated together;
a magnitude flag adds one point and moves the client into the suspicious pool.
Released anchors and rehabilitated suspects are inserted into a not-yet-processed
surveillance group when one remains. Later surveillance cycles use one check even
when the suspicious pool is empty; the initial double check is not repeated.

Suspicious clients maintain per-episode probe and flag counts. After at least ten
suspicion probes, a client with a flag rate at or below ten percent is returned
to the unflagged pool. Its cumulative penalty is retained, while its episode
counters reset. Lifetime trap and flag counts remain available for analysis.

## Penalties and removal

- Every near-zero update in any phase, including warm-up and each initial
  coverage probe, adds `penalty_zero_update` (default 5). Three exact send-backs
  therefore reach the removal threshold.
- Coverage magnitude flag: one point per flagged probe, giving one point for one
  of two checks or two points for both.
- Anchor-relative flag during frequent suspicion probing: three points.
- Flag during the one-check unflagged surveillance sweep: one point.
- There is no automatic per-pass penalty decay; rehabilitation is controlled by
  the dodge index.
- Remove when cumulative penalty is greater than or equal to the configured
  fixed removal threshold of 15. Three exact send-backs therefore cause removal.

Trapped updates are excluded from aggregation regardless of their flag result.

## Logged evidence

`client_metrics.csv` records the diagnostic cosine value, delta norm, norm z-score,
norm median/MAD, detection reason, and stored coverage observation round. Legacy
loss-z columns may remain blank for result-schema compatibility. Locally computed
loss and accuracy are simulation evaluation metrics and are never used for a flag.

## Known limitations

- Median/MAD assumes honest clients remain a strict majority. With 50% or more
  attackers, the robust baseline can itself represent malicious behavior.
- FR3 or FR4 can become statistically close to honest participation. Detection is
  inherently limited when their returned gradients are indistinguishable from
  honest gradients under the available secret probes.
- Detection quality and global accuracy must still be validated across FR1-FR4,
  multiple free-rider percentages, non-IID settings, and multiple random seeds.
