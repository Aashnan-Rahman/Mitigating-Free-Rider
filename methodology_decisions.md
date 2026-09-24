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

FR1 returns the currently received model unchanged, FR2 adds a bounded
memoryless random update, FR3 averages its received-model window, and FR4 predicts an update from
consecutive received-model differences plus calibrated noise. Secret trap models
are indistinguishable from other received models and therefore enter attack
history normally.

For update norms:

> **Current implementation note:** `swtcp_v11` replaces the anchor protocol and
> v10's raw-MAD/current-cycle reference trimming. Its authoritative rules are in
> `guidelines.md` and the v11 entry in `VERSION_HISTORY.md`.

```text
norm_median = median(client update norms)
norm_MAD    = median(abs(norm - norm_median))
norm_scale  = max(norm_MAD, 0.05)
norm_z      = (norm - norm_median) / norm_scale
```

For every nonzero checked update, v7 also forms a scale-free layer profile:

```text
profile[k] = norm(update tensor k) / sum_j(norm(update tensor j))
profile_score = L2 distance from the median reference profile
```

- Near-zero updates target static/no-update behavior such as FR1 and retain a
  permanent five-point evidence counter.
- Both unusually high and unusually low update norms are detected using
  `abs(norm_z)`, without selecting a branch based on attack type.
- A norm or layer-profile anomaly alone causes quarantine/confirmation but no
  magnitude penalty. Only both signals failing on the same response creates
  penalized joint gradient evidence.
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
disabled; instead, a candidate or suspicious client returns to the unflagged
pool after at least ten episode probes when no more than ten percent contain a
joint failure. Rehabilitation clears the current magnitude episode but preserves
all exact-zero evidence.

## Coverage sweep protocol

The initial coverage is evaluated as a complete experiment, not as unrelated per-round
decisions:

1. At the beginning of the initial coverage sweep, the server creates two
   distinct trap models from the same global base model.
2. Each trap model's exact weights are frozen for its complete pass.
3. Active clients are randomly partitioned into small groups.
4. Two distinct groups are probed per round. A randomized first pass gives every
   client trap A once; a separately randomized second pass gives every client
   trap B once, while avoiding repeated group-pairs where possible.
5. The server stores both of each client's deltas and observation rounds.
6. No coverage client is flagged, penalized, or decayed during an incomplete
   sweep.
7. After the last pair responds, median/MAD statistics are calculated separately
   for trap A and trap B, so responses to different models never define one
   another's baseline.
8. The two decisions are combined per client. A one-signal failure creates
   candidate evidence without a magnitude penalty; a joint norm/profile failure
   earns the configured trap penalty. Every near-zero response adds five points.
9. Both frozen models and the stored evidence are cleared.
10. The initial double sweep is not repeated; later unflagged surveillance uses
    ten single-check groups and a newly frozen model for each ten-round cycle.

This prevents an unlucky group containing a majority of free riders from defining
its own baseline. Within each pass, all clients are compared only after receiving
the same trap model; the second distinct trap makes repeated evasion harder.

The normal global model may continue evolving during the sweep, but trapped
updates are measured relative to the exact frozen model they received and are
excluded from global aggregation.

## Warm-up

Trap selection begins only after warm-up. During warm-up, the server performs
only the universal exact send-back check: it does not compute norm/profile flags
or create candidates from nonzero updates. No private client metric is requested
or trusted for detection.

## Suspicion phase and anchors

After the initial double-coverage sweep, clients are divided into unflagged (`U`),
candidate (`C`), and suspicious (`S`) states. A nonzero one-signal or joint
anomaly moves a client from U to C and quarantines its update. A candidate
receives fresh-trap confirmation against clean anchors. Two joint failures move
it to S by default; a fully normal response returns it immediately to U and
clears its current magnitude episode. Repeated one-signal-only responses are
eligible for the ten-probe rehabilitation rule. An exact send-back moves a
client directly to S.

Candidates and every client ever flagged are ineligible to act as anchors. If
`S` clients are suspicious, the server creates
`max(1, floor(S / 10))` groups and distributes every suspicious client among
them; ten is a target group size, not a maximum.

Every never-flagged U client belongs to the eligible anchor roster. At most ten
are active anchors in a round, with up to three assigned to each suspicious
group. A rotation queue avoids reusing an anchor until the eligible roster has
been traversed where possible. Suspects and active anchors are reshuffled between
groups every round. Every group receives its own fresh trap, and suspect norm and
profile scores are tested against the active anchors that received that model. A
joint failure receives three points; either signal alone receives none. Active
anchors supply both baselines but remain subject to exact-sendback detection.

Independently of the number of suspicious groups, all unflagged clients—including
off-duty members of the anchor roster—are partitioned into exactly ten Y groups.
The current Y group is excluded from active-anchor selection, receives the frozen
surveillance trap, and is excluded from aggregation. This periodically audits
anchor eligibility against the wider U population. A Y anomaly moves the client
to C and permanently disqualifies it from anchoring; only a joint failure adds
the surveillance penalty. Off-duty roster members outside the current Y group
receive the global model and aggregate normally. Later cycles continue even when
S is empty; the initial double check is not repeated.

Candidate and suspicious clients maintain episode probe and joint-failure counts.
After at least ten relevant probes, a client with a joint-failure rate at or
below ten percent returns to U. Its current magnitude penalty is cleared, exact-
zero points are retained, and episode counters reset.

## Penalties and removal

- Every near-zero update in any phase, including warm-up and each initial
  coverage probe, adds `penalty_zero_update` (default 5). Three exact send-backs
  therefore reach the removal threshold.
- A magnitude-only or profile-only response earns no magnitude points.
- A joint failure earns the phase-configured penalty: `penalty_trap_flag` in
  initial coverage, three points in frequent suspicion, and one in surveillance.
- There is no automatic per-pass penalty decay; rehabilitation is controlled by
  the dodge index.
- Three accumulated exact send-backs cause immediate removal, because their
  five-point penalties reach the fixed threshold of 15.
- Nonzero joint evidence cannot remove a client until it has received at least
  ten frequent S-state probes. Once that gate is met, total retained zero points
  plus current magnitude-episode points at or above 15 remove it. If the episode
  simultaneously qualifies for rehabilitation, rehabilitation wins and its
  magnitude points are cleared instead of removing the client.

Trapped updates are excluded from aggregation regardless of their flag result.
Candidate updates are also quarantined until confirmation; a clearing response
is excluded in its own round and normal aggregation resumes on the next round.

## Logged evidence

`client_metrics.csv` records the diagnostic cosine value, delta norm, norm z-score,
layer-profile score/z-score, both signal flags, joint evidence, detection reason,
and stored coverage observation round. Legacy
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
