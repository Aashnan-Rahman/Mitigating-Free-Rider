# SWT-CP: Suspicion-Weighted Trap Detection with Cumulative Penalty
## Build Specification for Federated Learning Free-Rider Simulation

This document is a complete implementation spec. Every numeric constant below is a
named configuration variable, not a hardcoded value — the code should be built so
that changing any single value in the config does not require touching logic
elsewhere.

> **Current protocol:** `swtcp_v13`. Historical sections remain for provenance.
> The v13 rules below override them when `methodology_version="swtcp_v13"`.

## V15 cycle confirmation (`swtcp_v15`)

### V15.4 fresh certificate memory (`swtcp_v15_4`)

Keep the entire v15.3 screening/certificate gate unchanged. Remember counts
separately for norm_low and profile_high. A newly issued full A/B certificate
increments only its own component, at most once per distinct completed cycle.
The configured confirmation count (two in this plan) need not be consecutive.
A C/ambiguous cycle pauses, never increments or erases these counts. Clear
statistical memory after the configured number of consecutive complete R cycles
(two in this plan). Mixed components never combine into a removal certificate.
Single-trap audits cannot confirm or clear memory. Exact sendback keeps its
existing consecutive-full-cycle path. Duplicate/older cycles are rejected.

Retained evidence does not by itself start/renew quarantine or force dense
probing. Preserve bounded v15.3 review, release, cooldown, rehabilitation,
grouping, trap schedules and training. A removal still requires a FRESH current
certificate for the component whose retained count reaches confirmation.
There is no median-only confirmation, attack-window reconstruction, attacker
label, known prevalence, removal quota, fitted z cutoff, or round-60 exception.
There ARE fixed design choices/support requirements and no calibrated error
guarantee: correlated false certificates may accumulate over a long lifetime.
Evidence has no arbitrary round-based expiry, but clean cycles clear it.

Checkpoint the small per-client count dictionary and clean streak. Decisions
log fresh_certificate_counts, certificate_clean_cycles and confirmed components;
removals distinguish repeated_fresh_component_certificates from the unchanged
exact/consecutive path. Frozen source hashes include v15.3 and v15.4 gates.
Do not modify source-hashed files for paused v15.3 recovery.

Cleanup update (2026-10-15): the unfinished prior CIFAR run and its remaining
queue were discarded at user request. Completed results remain preserved;
STOP_REQUESTED prevents restart. See result_check/cleanup_2026_10_15.json.

Original launch instruction: preserve/pause the prior CIFAR batch. Run
`configs/v15_4_cifar10_seed42_fr40_plan.json`: CIFAR-10, seed 42, 100 clients,
40% free riders, 100 rounds; non-IID FR3/FR4/FR2/FR1 before IID FR4/FR3/FR2/FR1.
The updated resume task runs at logon and every five minutes while logged on,
uses a launcher mutex/duplicate-runner guard and ignores parallel task starts.
It resumes the latest published checkpoint and skips completed experiments;
an intentional STOP_REQUESTED marker blocks automatic restart. Interrupted
training is recovered after the machine/user session is available again, not
while powered off. Old-decision replays are eligibility checks, not promised
counterfactual fresh-run recall or honest-removal rates.

### V15.3 strict norm removal (`swtcp_v15_3`)

Keep v15.1 screening, bounded review, two-trap/two-consecutive-cycle confirmation,
training and trap settings. A low-norm cohort can authorize removal ONLY when
the existing core gap exceeds its IQR AND the gap from its upper quartile to
the smallest peer norm exceeds that same cohort IQR, on BOTH selected traps.
The density/concentration alternative no longer authorizes norm removal.
Overlapping norm cohorts remain candidates without removal strikes or automatic
quarantine; weak evidence cannot indefinitely renew exclusion. Profile-distance
certificates retain the v15.1 gate. Exact current/previous sendback remains a
separate confirmation channel. Diagonal scores are diagnostic only, since they
contain negative norm-z and must not bypass a rejected norm certificate.

The identical rule applies in every cycle, with no round-30 switch, population
quota, attack labels, known prevalence, learned classifier or fitted z cutoff.
It is a conservative geometric heuristic, not a false-positive guarantee, and
can delay/miss free riders: recorded seed-73 non-IID FR4 loses its round-30
norm certificate, whereas seed-42 non-IID FR4 retains it. Recorded replay
eligibility is not a counterfactual rerun or promised detection rate.

The compact detector retains no extra full-response histories or training work.
`diagnostic_certified_channels` logs the former v15.1 certificates; enforcing
channels exclude diagonal and require strict norm separation. Use the isolated
`train_v15_3.py` engine so source-hashed files of the still-running v15.1 batch
remain unchanged/resumable. Its provenance hashes both evidence modules and the
new engine. Future changes to either gate reject v15.3 checkpoint resume.

Queue `configs/v15_3_mnist_seed42_fr40_plan.json` ONLY after the entire
`v15_1_mnist_seed42_fr40` batch completes successfully: MNIST, 100 clients,
40% free riders, 100 rounds, non-IID FR3/FR4/FR2/FR1 then IID FR4/FR3/FR2/FR1.
`queued_experiments.ps1` waits for existing runners, recovers the prerequisite
first after an outage, honours either batch's STOP_REQUESTED marker, and starts
or resumes the new batch only after all prerequisite completion markers exist.
Preserve all previous results and never retune this policy to obtain 40 removals.

### V15.2 individual follow-up (`swtcp_v15_2`)

Initial screening/cohort certificates and trap/training settings are unchanged.
Only a fresh cohort certificate can enrol a client/component on the individual
watchlist. Neither a weak candidate flag nor individual followup can invent
that initial permission. Exact sendback stays on its existing separate path.
Previously certified clients need not pass the combined-score nomination or
meet a minimum cohort size again to confirm their own previously certified
component. Fresh matching evidence must still occur on BOTH selected traps:
norm-z below its same-trap leave-one-out median centre; profile-z above its
same-trap leave-one-out median centre; or diagonal score above the same-trap
leave-one-out diagonal median. Zero for the signed z scores denotes a measured
median, not an attack-fitted z cutoff. Undefined measurements never confirm.
Diagonal medians use central order-statistic selection, not a client-score sort.

Removal still requires the SAME component in consecutive full cycles. A mixed
or undefined pair interrupts its confirmation streak but does not certify
clearance. Retain the compact watch until two complete consecutive clean cycles
clear the previously certified component. Quarantine/review remains bounded;
after exclusion expires an unresolved client may aggregate on ordinary rounds
but continues targeted paired probing. A single audit cannot confirm or clear
this watch. Fresh full certificates can enrol new components; removed clients
leave the watch permanently. One extra clean-cycle reference probation follows
rehabilitation as before. No round-30 switch, attack type, known prevalence,
labels, private loss, sample count or telemetry participates in these rules.

The checkpointed state keeps pending components, clean counts and certification
origin cycles (O(N*components), no response-vector history). Logged decisions
distinguish cohort_certified_channels, followup_matched_channels,
followup_clean_channels and pending/origin fields. Removal reasons distinguish
fresh repeated certificates from prior-certificate paired followup. This is
more permissive than v15.1 and may increase honest removals; it is not a
statistical error guarantee or universal zero-miss detector.

Run the same eight MNIST seed-73, 40%-FR, 100-round cases into
`results/v15_2_mnist_seed73_fr40`, non-IID FR4/FR3/FR2/FR1 before IID. Preserve
the completed v15.1 snapshot/results. `replay_v15_followup.py` checks recorded
round-20/30 eligibility without exposing labels to scoring. This is a
development replay/rerun; fresh results, especially later honest removals,
must be evaluated separately. Do not retune to achieve a desired removal count.

### V15.1 evidence gate (`swtcp_v15_1`)

This revision keeps the old screening as diagnostics, but removes its direct
removal authority. A screened S cohort must be a strict minority with at least
ceil(N/ceil(sqrt(N))) members; this population-derived support requirement does
not use the configured attack prevalence. Independently test low raw update
norm, high raw profile distance, and high diagonal score. On each trap, require
disjoint interquartile cores with a gap larger than the screened cohort's IQR.
Additionally require either that this gap persists against the full peer range
or that the cohort's IQR/(cohort size-1) is smaller than the peers' IQR/(peer
size-1). The latter prevents a smaller slice of a continuous population from
appearing artificially cohesive merely because it has fewer members.
An individual must also lie on the claimed side of the peer median; a
wrong-direction outlier cannot inherit a cohort's separation certificate.
No z
cutoff, attack-specific parameter, class labels, known-prevalence selection,
external calibration artifact or learned classifier enters this rule.

The SAME evidence component must certify the client on both traps and in
consecutive complete cycles to authorize removal. Repeated exact current/previous
sendback on both selected responses remains a separate evidence component.
Changing from norm evidence to profile evidence does not continue the removal
streak. Missing or weak evidence interrupts it. This is a geometric screening
heuristic, not a calibrated error guarantee or proof of non-training.

Weak S/C diagnostics become C without removal strikes or automatic quarantine.
Only certified S starts quarantine. Single-trap certified audit proposals start
bounded followup, not quarantine or a confirmation strike. Followup and existing
quarantine expire after the configured review budget if no strong evidence
returns; weak evidence cannot renew the budget. Release of unconfirmed evidence
is logged separately from rehabilitation and does not certify honesty. Review
cooldowns expire on audits, not on a cycle counter that could stall in quiet
mode. Fresh paired strong evidence overrides cooldown. Quiet audits begin when
no pending review or clean-cycle reference probation remains, even if weak C
diagnostics remain. Released/weak candidates can aggregate on non-trap rounds.

Exactly the same gate applies at round 20, 30 and later; there is no round-30
switch and no assumption that removed clients exhaust all attackers. New gate
work is a few scalar quantiles per signal/trap; existing screening/bootstrap
and compact measurement costs are unchanged. No extra model training or full
response history is required. `cycle_decisions.csv` records screen_state,
strong_channels, evidence_strength, quarantine and remaining review budget.
`cycle_policy.csv` records measured gaps/spreads and certificate rejection reasons.
`candidate_events.csv` distinguishes unconfirmed releases from rehabilitation.

Keep v15 outputs intact. Rerun all eight MNIST seed-73 40%-FR cases into
`v15_1_mnist_seed73_fr40`, non-IID before IID, with the unchanged 100-round
horizon/training/trap strengths. Offline replays on old trajectories only check
eligibility; they are NOT counterfactual accuracy/removal estimates. The rule
was developed after examining prior results, so these are development reruns,
not held-out validation. Do not retune it to the new batch outcomes.

This opt-in version overrides older removal, anchor and penalty rules. Warmup
is rounds 1-10; rounds 11-20 give every client two independent traps around a
frozen round-10 global model. Each dense cycle lasts ten rounds. Decision rule:
the unchanged diagonal histogram/bootstrap screening; if its population split
is unsupported, fall back to below-peer-median norm on both traps (S), one
trap/undefined evidence (C), or neither (R). Exact current/previous model
send-back on both selected trap responses independently implies S. Warmup
send-backs are diagnostic, never an immediate-removal bypass.

After the first cycle, create at most ten groups, with S/C in a monitored pool
separate from R. Allocate proportionally, nearest rounding with ties down
(42/100 => 4 monitored groups; 45 => 4; 46 => 5), bounded by pool sizes.
Monitored clients receive a trap every round, alternating A/B. Each R group
receives each trap once; use two R groups in a round where required for full
coverage. Fresh balanced grouping and fresh independent trap models each
cycle. All schedules depend only on public IDs and inferred state.

One A/B response pair per client is preselected uniformly from the schedule
before any scores are observed. It supplies the same exact same-trap
leave-one-out norm/profile statistics as v14.1; all active clients contribute
one response per trap, including unknown attackers. Additional monitored
responses are logged, never counted as extra removal strikes. No cosine or
full response histories are retained. Persistent detector memory is O(N*L),
apart from the two trap models, ordinary per-round training and simulator
attack histories. Bootstrap scratch space is unchanged.

Only S in two consecutive completed double-trap cycles removes (earliest
round 30). Any C/R result interrupts confirmation. New S waits for the next
complete cycle. S/C stay excluded from aggregation until two consecutive
complete R cycles; C or missing data interrupts clearance. Rehabilitated R
aggregates again but has one extra clean-cycle reference probation. References
for the present score remain the whole population, not filtered R anchors.
Trap responses never aggregate; newly flagged/removed responses also cannot
aggregate on the decision round. If all clients are quarantined, keep the
previous global model, not an empty/invalid average.

When no S/C or probation remains, use one all-client single-trap audit every
ten rounds; this may only escalate to C and a fresh dense cycle. It cannot
remove, confirm S or rehabilitate. Population/group counts shrink after removal;
fewer than ten remaining clients use fewer nonempty groups. No new clients
enter these fixed-population experiments. Permanent removal has no automatic
re-entry. A completed single audit with degenerate scores supplies no proof of
honesty; the periodic audit continues.

Server scoring, schedule and state transitions have no attack type, labels,
private loss, sample counts, telemetry or history-window inputs. Evaluation
labels are appended after decisions. The simulator necessarily uses attack
configuration to fabricate responses, separately from detection. The frozen
decision policy, independent stream seeds and source hashes are recorded in
`protocol.json`; checkpoints preserve selected pairs, traps, states, RNGs and
data-loader/attacker history and reject changed policy/settings/source hashes.

Outputs: `cycle_probes.csv`, `cycle_groups.csv`, `cycle_signals.csv`,
`cycle_decisions.csv`, `cycle_decision_summary.csv`, `cycle_policy.csv`, actual
removals/rehabilitations and global/aggregation diagnostics. Suspected screening
recall is distinct from permanent-removal recall. This is an empirical
high-recall policy, NOT a guaranteed false-positive bound: persistent honest
low updates may fail consecutive cycles. The previous 24 runs were development
backtests. The new eight-run MNIST seed-73, 40%-FR, 100-round plan is fresh
validation, with non-IID FR4/FR3/FR2/FR1 before IID. No tuning to seed-73 results.

## Current v13 corrections

### V14.1 preliminary comparison (`v14_1_preli`)

Optional `preliminary_diagonal_decisions` adds observational round-20 R/C/S
assignments, without changing aggregation or removing anyone. Frozen before the
CIFAR-10 seed-42 batch: D = profile-z minus signed norm-z on each trap;
three views are D_A, D_B and their average. Each histogram uses ceil(sqrt(N))
bins and an Otsu between-class-variance boundary. Resample whole client pairs
1,000 times (fixed bootstrap seed 20261011), retaining a 99% boundary-stability
band. All three views below their lower boundaries => R; all above their upper
boundaries => S; otherwise C. Both exact-zero trap responses independently imply
S. Invalid/degenerate evidence defers, and the average-view lower cohort must
contain a strict majority of all evaluated clients. No attack type, prevalence,
label, private loss or history-window knowledge enters classification.

This split is provisional: Otsu can split honest heterogeneity as well as
attacks, and bootstrap stability is NOT a calibrated false-positive guarantee.
The score direction was selected using MNIST development evidence; CIFAR is
fresh evaluation, not proof of universal attack coverage. No parameters are
retuned to CIFAR outcomes. Logs `preliminary_decisions.csv` and
`preliminary_decision_summary.csv` distinguish S/C/R from actual removals;
`preliminary_decision_policy.json` records the rule and learned boundary bands.
The additional decision uses O(bootstrap_replicates * N) scalar scratch space,
no extra training or model histories. Existing exact-cosine diagnostics still
temporarily retain full response vectors; that baseline cost is separate.

MNIST, seed 42, 40% free riders; eight IID/non-IID FR1-FR4 runs. Rounds 1-10
are warmup, 11-20 cover all clients under two independent, parameter-relative
perturbations of a frozen round-10 model. Ten shuffled groups receive each
trap exactly once per client; trap responses do not aggregate. All clients,
including exact send-backs, remain active through round 20. No statistical or
send-back removal, quarantine, shadow calibration, or paired-gain classification.

At round 20, `preliminary_signals.csv` contains one row per client per trap:
raw update norm, signed robust norm-z (normal-consistent MAD, no threshold/floor),
exact cosine against the leave-one-out same-trap mean update, and normalized
layer profile plus distance/profile-z against leave-one-out median profiles.
Zero response/reference cosine and degenerate MAD scores are undefined, not
zero-filled. References contain unknown attackers; cosine is descriptive, not
proof of honesty. It differs from v8's coverage coordinate-median reference.

`preliminary_comparison.csv` supplies means, medians, quartiles, ranges and
undefined counts by trap, class and signal. Ground truth is appended only for
evaluation after all measurements; it cannot select references. Independent
random streams and checkpointed partial coverage are retained. No FedProx or
increased trap strength is included in this baseline experiment.

Exact post-sweep cosine needs temporarily stored CPU response vectors (O(NP)
memory for a single sweep), unlike the earlier compact shadow summaries. The
buffers are discarded after comparison, and successful-run checkpoints are
cleaned up. This is a diagnostic memory tradeoff, not an unbounded model history.

### Frozen combined shadow rule (`paired_combined_shadow_v1`)

`paired_shadow_calibration` enables shadow proposals ONLY within paired
measurement mode. It never changes aggregation, C/S state, statistical penalties
or actual removals. The exact-sendback path remains separate and enforced.

For each complete pair, collect signed gain, the mean log update norm, log
profile difference, and signed per-layer gains. Over three consecutive paired
cycles, take the median of each component. Compare these medians in both
directions against a frozen honest-only fitting center and MAD scale. The score
is the maximum absolute standardized component, without attack-specific weights,
history reconstruction, signature values, or a personal-baseline veto.

Calibrate that whole maximum score on a separate complete honest-only run, not
on current peers or filtered passing clients. With n calibration windows and
preselected alpha=0.01, the boundary is rank ceil((n+1)(1-alpha)); strict greater
than rejection. Unsupported rank resolution defers. Degenerate fitting scales
fail calibration instead of silently inventing floors. Invalid observations or
cycle gaps defer/restart a window, not certify clearance. Windows do not overlap.

Development fitting uses completed clean seed-42 controls; separate clean
seed-44 controls calibrate each IID/non-IID context with 100 client windows.
Neither source contains attackers. Artifact provenance records source hashes;
fresh-run plans pin artifact SHA-256, protocol, context, and the unchanged risk
budget. Seeds 46/47 and replay-history variants are evaluation, not calibration.
No automatic retuning or enabling removals based on these results.

This is EMPIRICAL, not a guaranteed 1% deployment or lifetime false-removal rate.
Client windows share training trajectories and need not be exchangeable with
fresh attacker-containing runs. Dataset, partition skew, training settings,
perturbation settings, and run horizon must match the calibration context.
Shadow results must report attacker misses and honest proposals separately;
zero actual removals is not evidence of low statistical false-positive rates.

Runtime keeps up to three short feature vectors per client, a calibration
vector, and client IDs. It retains no full response histories. Checkpoints
preserve partial windows and reject a changed calibration fingerprint. Decisions
and reasons are in `paired_shadow_decisions.csv`; ground truth is appended only
for evaluation after scoring and cannot influence the decision.

### Paired validation mode (`paired_measurement_v1`)

When `paired_measurement_only=true`, the following overrides statistical v13
classification. Exact current/previous send-back strikes remain active.

- Generate plus/minus perturbations around one frozen cycle model. Keep the
  existing parameter-relative perturbation amplitude; do not fit it to outcomes.
- Randomize each group's first sign; the complementary second half gives each
  client both signs with the same round gap. Fresh randomness every cycle.
  Both trap responses are excluded from aggregation. Every cycle stays paired.
- Record directional response gain, per-layer gains, norms, and profile change.
  Keep only O(clients * layers) scalar summaries between probe rounds.
- No population-tail thresholds, personal-baseline vetoes, statistical flags,
  quarantine or statistical removals. This is measurement, not a new validated
  detector. Non-IID distributions, chronology and SGD noise can still overlap.
- Independent, checkpointed random streams cover partitioning, attacker
  selection, initialization, training, scheduling, trap directions and attacks.
  Explicit per-stream seed overrides permit one-factor comparisons. Attack draws
  cannot consume trap randomness. Attacks can still affect the learned base
  model, so actual trap weights need not match between different attacks.
- `paired_responses.csv` ground truth is evaluation-only, added after feature
  extraction. Feature functions accept no attack configuration or labels.
- Freeze this protocol before observing held-out seeds 44/45. The fresh 26-run
  MNIST validation plan uses 100 clients and 40 rounds: matched honest-only/FR4
  controls, isolated partition/trap/attack seed changes, held-out IID/non-IID,
  alternate replay histories, and FR1-FR3 IID/non-IID. No auto-tuning to results.
- Resume rejects changed paired seeds/settings and preserves partial pairs,
  logs, client data-loader states, attack RNG and simulation history.

The previous batch is stopped and preserved. Validation output uses a fresh
directory. Zero FR4 removals in this mode is expected; evaluate response
separation and honest variability before authorizing a classification rule.

- Use only update norm and normalized layer-profile evidence. Do not reconstruct
  averaging windows or model trajectories, and do not use attack parameters,
  private data/sample counts, client loss, or client telemetry for decisions.
- Replace three-client anchors with complete same-trap batches and leave the
  evaluated client out of its peer reference. A too-small batch cannot support
  statistical removal. No current outlier trimming/recomputed narrow baseline.
- Apply log-norm robust statistics, normal-consistent MAD and historical scales.
  Derive cutoffs from prior complete-cycle score ranks, excluding the client's
  own scores and matching probe counts. Include flagged scores to avoid a
  passing-only truncated calibration tail. No Gaussian bootstrap or chosen z
  threshold. Insufficient calibration defers statistical decisions.
- Keep small personal residual histories only from fully clear, calibrated
  cycles. Consistency may weaken confirmation, but cannot erase population
  screening or teach a flagged client its own baseline.
- Strong evidence requires the same anomalous component/direction on both
  distinct traps and confirmation in consecutive fresh cycles. Norm-only or
  profile-only evidence can qualify; joint norm/profile failure is not required.
- Weak or clean cycles interrupt confirmation, but retain bounded follow-up
  records. Old evidence expires; unconfirmed
  quarantine is bounded by a configured review deadline. After release, weak
  evidence has a cooldown; strong evidence can still trigger fresh confirmation.
- If references are insufficient, release quarantine rather than hold it
  indefinitely. Continue fresh audits. Reference eligibility is recoverable.
- Retain passive current/previous exact-sendback checks and their permanent
  five-strike path. Never combine sendback strikes with statistical penalties.
- Report honest quarantine and excluded active client-rounds as well as honest
  permanent removal. Resume must preserve all detector and random-generator state.
- Schedule all MNIST runs together, with non-IID FR4 seeds 42, 43, 46 first,
  then other non-IID cases and finally IID, at 40% free riders and 100 rounds.
- Paired differential challenges are deferred pending separate validation.

### Calibration contract (revision `empirical_combined_v2`)

Each cycle score is the maximum of absolute norm-z and positive profile-z over
all probes. Given n earlier matching-probe scores and a preselected risk budget
alpha, use sorted rank ceil((n+1)(1-alpha)), with strict greater-than rejection.
If that rank exceeds n, defer. The existing deployment alpha remains 0.01;
at least 99 peer observations are needed for a finite boundary. This is a
policy error budget, not a value selected to catch an attack in saved results.

The rank rule has its usual error interpretation only for exchangeable null
scores. Federated scores drift, repeat clients, and include unknown attackers;
therefore this implementation is empirical screening, NOT a guaranteed 1%
honest-removal rate or lifetime error bound. Contaminated calibration can mask
attacks. Consecutive confirmation is not an independence/alpha-squared claim.
Robust peer centering assumes an honest majority, and norm/profile alone cannot
distinguish an attacker that reproduces honest observable behavior. Report both
misses and honest quarantine/removal; do not tune thresholds to those outcomes.

Original v13 checkpoints are incompatible with this revision and are rejected.
Keep old outputs intact. The scheduled experiment batch remains user-stopped;
new experiments require explicit authorization and a fresh output directory.

## Current v12 corrections

- Retain a deterministic 32-value linear sketch of each server-sent model and
  returned update. Full client deltas are still discarded after the round.
- Test whether an update can be reconstructed from only models previously sent
  to that client: an average-of-received-models hypothesis and a recent model-
  trajectory hypothesis. Neither test receives an attack label.
- Calibrate reconstruction scores with high-side robust statistics whose scale
  uses only the lower side of the majority distribution, preventing a high
  minority from widening its own threshold.
- A history or static signature is removal-strength evidence only when its
  coherent cohort exceeds the binomial bound derived from
  `cycle_target_false_alarm_rate`. Isolated profile or history matches remain
  weak C evidence and add no penalty.
- When a cohort has the more specific mean-replay explanation, suppress the
  less specific trajectory hypothesis for that cycle. This prevents ordinary
  training aligned with the global trajectory from being promoted.
- Probe intensity responds to new coherent strong evidence in the completed
  cycle, not merely to the continued existence of an old weak candidate.

## Historical v11 corrections

- Convert MAD to a robust standard-deviation estimate with the mathematical
  normal-consistency factor `1 / Phi^-1(0.75)` (approximately `1.4826`).
- Derive the cycle cutoff from `cycle_target_false_alarm_rate` and prior completed
  R-cycle calibration scores. A client never helps set the cutoff used to judge
  its current response.
- Stabilize current scales with recent trusted-reference scales using a
  sample-size-weighted prior. Absolute MAD floors remain legacy settings and are
  not v11 detector thresholds.
- Freeze the reference roster and cutoff at cycle start. Do not remove provisional
  outliers and recompute a narrower baseline within the current cycle.
- An OR anomaly is weak screening evidence: it moves R to C but adds no score.
  Strong evidence requires the same signature (`norm_high`, `norm_low`, or
  `profile_high`) under both frozen traps.
- Retain only scalar norms and small layer-profile vectors between probe rounds;
  do not checkpoint full flattened client deltas.
- Detector decisions may use only sent/returned models and prior server-side
  state. Ground-truth labels and `attack_type` are evaluation inputs only and may
  not select a detector rule.

## Historical v10 protocol

- Rounds 1–10 are warm-up. No statistical traps run. FR1 is checked in exactly
  two ways: an unchanged current model (`delta < zero_update_epsilon`) and an
  exact fingerprint match with the immediately previous model sent to that same
  client. Either event adds one permanent send-back strike, capped at one strike
  per client per round. Five strikes remove the client, but warm-up removal is
  applied only at the end of round 10.
- The first cycle (rounds 11–20 with 100 active clients) builds exactly ten
  balanced groups and freezes two trap models. Two groups are probed per round;
  every client receives each trap exactly once. Only clients trapped in the
  current round are excluded from aggregation. The initial comparison population
  contains all responses that received the same trap.
- A probe fails when either the two-sided robust update-norm test or the
  layer-profile test fails. The raw norm/profile thresholds are dynamic because
  their median and MAD are recomputed from the applicable population; the robust
  z multipliers remain configured at 3.0.
- At the first cycle boundary, zero failed probes means R, one means C, and two
  means S. Later cycles retain exactly ten state-homogeneous, balanced groups
  across R/C/S (or one group per active client when fewer than ten remain).
- Later comparisons use only reference-eligible R clients that received the same
  frozen trap. Provisional anomalous R references are removed, the baseline is
  recomputed once, and those clients enter C. If fewer than
  `cycle_min_reference_clients` clean references remain, statistical transitions
  are deferred and double probing continues.
- From round 21 onward, every C/S client is quarantined throughout the complete
  cycle. Only nontrapped R clients aggregate. An R anomaly always enters C first,
  even if both probes fail; independent later confirmation is required.
- Scores never become positive: a clean cycle adds 0.5 only while the score is
  negative, one failed probe costs 1, and two failed probes cost 2. Statistical
  removal requires score <= -4, at least two strong (two-failure) cycles, and at
  least one such confirmation against a trusted R reference.
- C returns to R after two consecutive fully clean cycles. S first returns to C
  after two clean cycles, then needs two more clean C cycles to return to R. Any
  anomaly resets the clean streak. A rehabilitated R aggregates immediately but
  completes one additional clean cycle before becoming reference-eligible.
- Double probing continues until C/S are empty and two consecutive double cycles
  are clean. The detector then runs single-probe ten-group cycles. An anomaly
  restores double mode; two clean single cycles enter dormancy. Dormancy performs
  only passive send-back checks for 20 rounds, then runs one single audit cycle;
  a clean audit returns to dormancy and an anomaly returns to double mode.
- State changes occur only at complete cycle boundaries. A clearing response is
  excluded for its entire clearing cycle and can aggregate starting next cycle.

---

## 1. Framework & Environment

- **Language / Framework:** Python, PyTorch (torch, torchvision).
- **Reproducibility:** a single global `seed` (int) config value must seed
  `random`, `numpy`, and `torch` (CPU + CUDA if available) at the start of every run.
- **Device:** auto-detect CUDA, fall back to CPU. Should be a config override
  (`"auto" | "cpu" | "cuda"`).
- **Modularity requirement:** the codebase should be structured so that dataset,
  model architecture, non-IID partitioning, attack strategy, and detection
  hyperparameters are all swappable via a single config object (dataclass or YAML/JSON
  config), not scattered as magic numbers across files. See Section 9 for suggested
  file layout.

---

## 2. Configuration Variables (all must be adjustable, with defaults shown)

| Variable | Default | Description |
|---|---|---|
| `methodology_version` | `"swtcp_v11"` | Rejects checkpoints produced by an incompatible detector protocol |
| `dataset` | `"mnist"` | `"mnist"` or `"cifar10"` |
| `distribution` | `"iid"` | `"iid"` or `"noniid"` |
| `dirichlet_alpha` | `0.5` | Concentration parameter for Non-IID Dirichlet partitioning. Lower = more skewed. Only used if `distribution == "noniid"` |
| `num_clients` (N) | `100` | Total registered clients |
| `num_rounds` (T) | `100` | Total communication rounds. Also supports `200` |
| `free_rider_pct` | `0.10` | Fraction of clients that are free riders. Also test `0.20`, `0.40` |
| `attack_type` | `"FR1"` | One of `"FR1"`, `"FR2"`, `"FR3"`, `"FR4"` — see Section 4. Exactly one attack type active per run |
| `local_epochs` (E) | `3` | Local training epochs per client per round |
| `batch_size` | `32` | Local training batch size |
| `optimizer` | `"sgd"` | `"sgd"` or `"adam"` |
| `learning_rate` | `0.01` | Local optimizer learning rate |
| `momentum` | `0.9` | Only used if `optimizer == "sgd"` |
| `warmup_rounds` (n_w) | `10` | Rounds before trap selection activates; passive update detection still runs |
| `trap_fraction` (rho) | `0.10` | Base group size for the initial double-coverage sweep |
| `coverage_checks_per_client` | `2` | Coverage observations per client; `2` enables balanced double checking, while `1` retains the original single sweep |
| `candidate_confirmation_flags` | `2` | Joint norm/profile failures required to enter S; any single-signal anomaly enters C |
| `anchors_per_suspicion_group` | `3` | Maximum low-suspicion anchors assigned to each suspicious group |
| `max_suspicion_anchors` | `10` | Maximum total anchors excluded in one round |
| `surveillance_groups` | `10` | Fixed number of groups in every post-initial unflagged sweep |
| `penalty_zero_update` | `5` | Penalty for near-zero delta (static replay / no training) |
| `penalty_trap_flag` | `2` | Penalty for a joint norm/profile failure in an initial coverage probe |
| `penalty_normal_flag` | `1` | Penalty for a joint failure in one-check surveillance |
| `penalty_suspicion_flag` | `3` | Penalty for an anchor-relative joint failure |
| `removal_threshold_points` | `15` | Fixed cumulative penalty required for removal |
| `dodge_min_probes` | `10` | Minimum frequent-suspicion probes before rehabilitation |
| `dodge_max_flag_rate` | `0.10` | Maximum per-episode trap-flag rate allowed for rehabilitation |
| `zero_update_epsilon` | `1e-6` | Numerical tolerance for "delta ≈ 0" check (L2 norm below this counts as zero) |
| `magnitude_z_threshold` | `3.0` | Two-sided robust norm z-score boundary used for every attack |
| `mad_floor` | `0.05` | Real minimum MAD scale, preventing small-batch threshold collapse |
| `profile_z_threshold` | `3.0` | High-sided robust z-score boundary for layer-profile distance |
| `profile_mad_floor` | `0.01` | Minimum MAD scale for layer-profile distances |
| `fr2_update_range` | `1e-3` | Half-width of the bounded uniform random update used by FR2 |
| `fr3_window` | `5` | Maximum number of received models averaged by FR3 |
| `fr4_history_size` | `5` | Maximum number of received-model deltas averaged by FR4 |
| `fr4_noise_fraction` | `0.1` | FR4 noise norm as a fraction of its predicted update norm |
| `fr4_cold_start_scale` | `1e-4` | FR4 Gaussian update scale before a historical delta exists |
| `sendback_history_size` | `1` | Per-client immediately previous sent-model fingerprint retained for exact replay detection |
| `sendback_removal_count` | `5` | Permanent send-back strikes required for removal |
| `cycle_candidate_clean_cycles` | `2` | Consecutive clean cycles required for C to return to R |
| `cycle_suspect_clean_cycles` | `2` | Consecutive clean cycles required for S to step down to C |
| `cycle_reference_probation_cycles` | `1` | Additional clean R cycle required after rehabilitation before reference eligibility |
| `cycle_strong_cycles_for_removal` | `2` | Strong cycles required for statistical removal |
| `cycle_double_clean_cycles_before_single` | `2` | Clean double cycles required before single probing |
| `cycle_single_clean_cycles_before_dormant` | `2` | Clean single cycles required before dormancy |
| `cycle_dormant_rounds` | `20` | Passive rounds between single-cycle audits in dormancy |
| `cycle_min_reference_clients` | `10` | Minimum clean R reference population for a statistical decision |
| `cycle_target_false_alarm_rate` | `0.01` | Per-client complete-cycle false-alarm budget used to derive the v11 cutoff |
| `cycle_calibration_window_cycles` | `3` | Prior trusted-R cycles used for cutoff and scale calibration |
| `cycle_scale_prior_strength` | `20.0` | Sample-size prior controlling how quickly robust scale can change |
| `cycle_scale_epsilon` | `1e-8` | Numerical division safeguard, not a detector threshold |
| `full_participation` | `true` | All active clients train every round (no dropout simulated) — see Section 3.1 |
| `seed` | `42` | Global random seed |
| `output_dir` | `"./results/"` | Where all CSV/log outputs are written |
| `run_name` | auto-generated | e.g. `"{dataset}_{distribution}_{attack_type}_fr{free_rider_pct}_{timestamp}"`, used as subfolder / filename prefix |
| `save_checkpoints` | `true` | Save a complete recovery checkpoint after every round |
| `checkpoint_keep_last` | `5` | While running, retain only the newest numbered checkpoints; delete all recovery checkpoints after success |

---

## 3. System Model

### 3.1 Participation Model
Every active client trains every round (`full_participation = true`). There is no
random per-round training-sample subset — this differs from standard FedAvg papers
that use a participation rate `C`, and is a deliberate simplification since this is
a simulation with no real device dropout. The **only** subset selected each round is
the trap subset `T_t` (Section 3.3), which is drawn from the full active pool.

### 3.2 Roles per Round
Each active client in round `t` is either:
- **Trapped** (`i ∈ T_t`): receives the corrupted/trap model, its update is
  **excluded from aggregation** regardless of outcome, but is still checked for flags.
- **Candidate** (`i ∈ C`): quarantined after a one-signal or joint anomaly; its update is
  excluded until its confirmation result is resolved.
- **Normal**: receives the true global model and is aggregated when it is not
  simultaneously selected for a trap or held in C.

### 3.3 Phases

**Phase 0 — Warm-Up (rounds 1 to `warmup_rounds`)**
No trapping. Only exact-zero/send-back detection is active; nonzero magnitude
and layer-profile checks do not run and cannot create candidates. The five-point
send-back penalty applies from round one.

**Phase 1 — Coverage Sweep (immediately after warm-up)**
- Generate two distinct trap models from the same global base at the beginning
  of the initial sweep and freeze each model for its complete pass.
- Partition all currently active clients into consecutive groups of size
  `m = ceil(rho * |active_clients|)`.
- Trap two distinct groups per round. In the first randomized pass every client
  receives trap A once; in the second randomized pass every client receives trap
  B once. Avoid repeating a group-pair where possible.
- Store each trapped response without flagging or penalizing it immediately.
- After the final pair responds, compute norm and layer-profile median/MAD
  baselines separately for the complete trap-A and trap-B passes. Either signal
  alone creates candidate evidence without points; only a joint failure earns
  `penalty_trap_flag`. Every zero update applies five points.
- Each trap pass's median delta is used as its diagnostic reference vector.
- When the queue of groups is exhausted, transition to Phase 2.

**Phase 2 — Suspicion-Flagged Sweep (ongoing)**
- Maintain unflagged (`U`), candidate (`C`), and suspicious (`S`) pools.
- Any one-signal or joint anomaly moves U to quarantined C. Confirm C on fresh
  group traps against never-flagged anchors: two joint failures move it to S; a
  fully normal response returns it to U and clears the current magnitude episode.
  An exact send-back moves it directly to S.
- Build `X = max(1, floor(|S| / 10))` groups when `S` is non-empty. Every
  suspicious client is included, so group size is not capped at ten.
- Treat every never-flagged U client as eligible for the anchor roster. Select at
  most ten active anchors per round and assign up to three per suspicious or
  confirmation group. Rotate through the eligible roster before reusing anchors
  where possible. A candidate or any previously flagged client can never anchor.
  Shuffle suspects and active anchors among groups every round.
- Give every suspicious group its own fresh trap model. Compare suspect update
  norms and layer profiles with baselines from that group's anchors. A joint
  failure adds three points; either signal alone adds none. An exact send-back adds five and a zero-update anchor
  is excluded from the magnitude baseline.
- Independently partition all U clients, including off-duty anchor-roster members,
  into exactly ten Y surveillance groups. Exclude the current Y group from active
  anchor selection, probe it with the cycle's frozen surveillance model, and
  evaluate the complete sweep together. A flagged Y client loses anchor
  eligibility permanently.
- Off-duty anchor-roster members receive the normal global model and contribute
  to aggregation unless they are the current Y group.
- A surveillance anomaly moves the client to C; only a joint failure adds one point.
- After ten episode probes, a C or S client with at most a ten-percent joint-
  failure rate returns to U. Its magnitude episode is cleared while exact-zero
  evidence remains.
- When `S` is empty, continue ten-group single-check surveillance sweeps. The
  initial double-coverage sweep is not repeated.

---

## 4. Free-Rider Attack Types (implement all four, select one per run via `attack_type`)

- **`FR1` (Direct Send-Back):** client performs no training and returns the model
  received in the current participation unchanged. Its update delta is therefore
  exactly zero on every round, including rounds in which it receives a trap.
- **`FR2` (Bounded Random Update):** client adds an independently sampled update
  from `Uniform(-fr2_update_range, fr2_update_range)` to every floating-point
  parameter of the currently received model. It is memoryless and uses no
  privileged information.
- **`FR3` (Sliding-Window Average):** client maintains a buffer of up to its last
  `fr3_window` received models and returns their element-wise average.
- **`FR4` (Distribution-Aware Adaptive):** client records differences between
  consecutive models it receives, averages up to `fr4_history_size` recent
  differences, and adds isotropic noise whose norm is
  `fr4_noise_fraction` of that predicted update norm. Before one difference is
  available, it adds Gaussian noise scaled by `fr4_cold_start_scale`.

All attackers have only client-observable information: client identity, round,
the current received model, models previously sent to that same client, public
configuration, and local randomness. The server never discloses whether a model
is a trap. Consequently, every received model enters FR3/FR4 history under the
same rules, including a secret trap model. FR1 simply returns that current model
unchanged and does not need historical state to fabricate its response.

Free riders are assigned once at the start of the run: `ceil(free_rider_pct * N)`
clients are randomly selected and flagged internally as free riders (ground truth,
used only for evaluation metrics, never exposed to the detection logic).

---

## 5. Per-Round Detection Logic (applies to checked clients)

1. **Send-back checks:** if `||delta|| < zero_update_epsilon`, record a direct
  zero-update send-back. For a nonzero response, compare its deterministic model
  fingerprint with the immediately previous model sent to that same client and
  record an exact replay when it matches. Either outcome contributes one
  permanent send-back count, with at most one count per client per round. This
  applies during warm-up as well as coverage and suspicion. Skip the cosine
  diagnostic for a zero update.
2. **Robust norm-z check** (only if step 1 did not trigger): during coverage or
  surveillance, compute the complete sweep's norm median/MAD and apply the
  configured two-sided robust-z boundary. During frequent suspicion probing, use
  only the two or three anchors that received the same trap, and flag the
  suspect when `abs((norm - anchor_median) / max(anchor_MAD, mad_floor))`
  exceeds `magnitude_z_threshold`.
3. **Layer-profile check:** normalize the per-parameter-tensor update norms to
   sum to one, measure distance from the phase median profile, and robustly score
   that distance. One failed signal creates C evidence without a penalty. Both
   norm and profile must fail on the same response to earn the phase penalty.
4. **Cosine diagnostic:** compute cosine similarity against the phase reference
  and write it to client metrics. It is currently not used to flag or
  penalize a client.
5. **Rehabilitation:** after at least ten episode probes, return C or S to U when
   its joint-failure rate is at most ten percent. Clear current magnitude points,
   preserve exact-zero points, and reset episode counters.
6. **Removal check:** three accumulated exact send-backs remove immediately.
   Nonzero joint evidence additionally requires at least ten completed S-state
   probes before `P_i >= 15` can remove the client. A qualifying low joint-rate
   rehabilitation takes precedence over nonzero-evidence removal. Log the event.
7. **Aggregation:** global model for round `t+1` = mean of deltas from all
   clients that are neither trapped nor quarantined candidates in round `t`.
   A candidate clearing response is still excluded in its confirmation round;
   ordinary aggregation resumes in the next round.

Client-local loss and accuracy may be recorded by the simulator for evaluation,
but they are not detector inputs and cannot change suspicion or penalties.

---

## 6. Models

Keep architectures simple and swappable via a `get_model(dataset_name)` factory
function.

- **MNIST:** small CNN — e.g. 2 conv layers (16, 32 filters, 3x3, ReLU, maxpool)
  followed by 2 fully connected layers ending in a 10-way softmax.
- **CIFAR-10:** slightly deeper CNN — e.g. 3 conv blocks (32, 64, 128 filters,
  3x3, ReLU, batchnorm, maxpool) followed by 2 fully connected layers ending in a
  10-way softmax.

Both should be defined as standard `torch.nn.Module` subclasses so they can later
be swapped for other architectures without touching the training loop.

---

## 7. Data Partitioning

- **IID:** shuffle the full training set, split into `num_clients` equal shards.
- **Non-IID:** Dirichlet-based partitioning using `dirichlet_alpha` — for each
  class, draw a proportion vector over clients from `Dirichlet(alpha)` and assign
  samples of that class accordingly, so lower `alpha` produces more label-skewed
  clients.

---

## 8. Required Outputs (all under `output_dir/run_name/`)

1. **`trap_matrix.csv`** — rows = rounds (1..T), columns = client IDs (0..N-1).
   Cell value: `1` if that client was trapped that round, `0` otherwise. Include a
   `phase` column per row (`warmup`, `coverage`, `confirmation`, `suspicion`, or
   `surveillance`).
2. **`global_metrics.csv`** — one row per round: `round, global_accuracy,
   global_loss, num_active_clients, num_candidate_clients,
   num_suspected_clients, num_trapped, num_aggregated, round_time_seconds`.
3. **`client_metrics.csv`** — one row per (round, client): `round, client_id,
   is_free_rider (ground truth), was_trapped, local_accuracy, local_loss,
   cosine_similarity, delta_norm, norm_z_score, norm_median, norm_mad,
   profile_score, profile_z_score, magnitude_flag, profile_flag,
   joint_flag_count, detection_reason,
   flagged (bool), penalty_added_this_round`.
   Local accuracy/loss are simulator diagnostics only. Legacy loss-z fields may
   remain present but blank for compatibility and are not detector inputs.
4. **`penalty_tracker.csv`** — one row per (round, client), including cumulative
   penalty, C/S state, candidate-episode flags, exact-zero count, and lifetime
   flag/trap counts.
5. **`removals.csv`** — one row per removal event: `round, client_id,
   is_free_rider (ground truth), final_penalty, removal_basis,
   zero_update_count, suspicion_probes`.
6. **`run_config.csv`** (or `.json`, whichever is easier to generate) — a full dump
   of every config variable in Section 2 for that run, plus `run_name`, `seed`,
   `device`, start/end timestamp, and total wall-clock runtime.
7. **`candidate_events.csv`** — U-to-C entries, additional candidate evidence,
   C-to-S confirmations, and confirmation passes that return C to U.

All files for a given run should share a common `run_name` prefix or live in a
common per-run folder so multiple experiment configurations (different datasets,
distributions, free-rider percentages, attack types) don't overwrite each other.

---

## 9. Suggested Project Structure

```
project/
├── config.py            # Config dataclass, defaults from Section 2
├── data/
│   ├── loaders.py        # MNIST/CIFAR-10 loading
│   └── partition.py       # IID / Dirichlet Non-IID partitioning
├── models/
│   └── architectures.py  # get_model(dataset_name)
├── clients/
│   └── attacks.py         # FR1–FR4 implementations, applied per client per round
├── server/
│   ├── trap_selection.py  # Warmup, coverage, and suspicion-flagged trap queues
│   ├── detection.py       # zero-update and norm-outlier checks, penalty logic
│   └── aggregation.py     # FedAvg over non-trapped clients
├── train.py               # main training loop orchestrating the above
├── logging_utils.py       # CSV writers for Section 8 outputs
└── run_experiment.py      # entry point, reads config, calls train.py
```
---

## 10. Notes / Assumptions Carried Over From Design Discussion

- Detection never causes the whole round to be discarded. Trapped and candidate
  clients' updates are excluded; other active clients aggregate normally.
- Reference populations differ by phase: complete stored responses during
  coverage/surveillance and same-model anchors during frequent suspicion.
  Cosine similarity remains diagnostic only.
- `P_max` is a fixed 15 evidence points, independent of experiment length.
- Ground-truth free-rider labels must be tracked internally for evaluation
  metrics (precision/recall/F1 of detection, false-positive removal rate) but must
  never be accessible to the detection/trap-selection logic itself — the whole
  point is that detection works without knowing this in advance.
