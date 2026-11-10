# Figure guide for BaitFL v7.1

This guide describes the figures in the current full manuscript. It is review
material, not additional manuscript text. The same guide is included as comments
at the start of `paper_v7_1_all_in_one.tex`.

The diagrams are written in **TikZ**. The charts use **PGFPlots**, built on TikZ.
Both are vector graphics. The regular manuscript includes separately compiled
PDFs for Figures 1, 2, 3a, 3b and 4. The review export instead embeds their actual
TikZ code, along with all plotted data, so it needs no figure PDFs, CSVs or DATs.
Comments marked `BEGIN SOURCE` identify the original source of each block.

When asking another system to review the paper, ask it to read the manuscript
and this guide, check equations against the algorithms, and distinguish
illustrative diagrams from measured results. Code and descriptions explain
content, but judging overlaps, spacing and print readability still requires a
rendered preview. Standard LaTeX packages are required to compile the export.

## Figure 1: Free riding in federated learning

- Layout: federated server above three device cards, two honest and one free rider.
- Purple arrows go from server to every device and carry the same global model
  `w_t`. Green arrows return trained local models from honest devices. The orange
  dashed arrow returns a fabricated local model from the free rider.
- Honest devices contain a private-data cylinder and a laptop showing a small
  neural-network model icon.
  The free rider's laptop contains a fabricated model symbol and says it skips
  local training. The legend explains the three arrows and the data cylinder.
- Meaning: receiving and returning a model does not itself demonstrate local
  optimization. This is a problem illustration. It contains no challenge or
  detector and does not assert that a free rider lacks data or computing power.
- Drawing source: `figures/free_rider_attack.tex`.

## Figure 2: Illustrative audit schedule

- Read the horizontal round axis from left to right: ticks 0, 10, 20, 30, 40, 50.
- Warmup occupies rounds 1-10. Two example ten-round paired cycles follow,
  each collecting responses to traps A and B. The earliest-removal callout is
  at round 30. Ordinary training follows on the illustrated path.
- Teal diamonds at 40 and 50 indicate sparse audits, ten quiet rounds apart.
  The bottom rules say that review or probation repeats paired cycles, whereas
  neither being active permits ordinary training and sparse auditing.
- Meaning: this is an example path through the schedule, not a promise that
  every execution enters ordinary training at round 30. Review and probation
  can extend paired operation. Removal requires repeated fresh evidence.
- Drawing source: `figures/audit_schedule.tex`.

## Figure 3a: Challenge construction and response comparison

- A frozen model `w^(c)` branches into two independently perturbed copies,
  `tau_A` and `tau_B`. Both go to the same client group in separately scheduled
  rounds. Each returned response is compared with peers receiving that trap.
- The comparison block contains update norm `r`, tensor profile `p`, and their
  normalized scores `z^n` and `z^p`. Below it is `D_i^a = z_i^{p,a} - z_i^{n,a}`.
- Teal marks the challenge path. The diagram explains the measured features
  and paired coverage. It is not a chart of measured client outcomes.
- Drawing source: `figures/challenge_path.tex`.

## Figure 3b: Representative paired-response scores

- Measured setting: CIFAR-10, non-IID, FR3 history averaging, 40% free riders,
  round 20, representative seed 42. There are 60 honest and 40 free-rider
  responses. Identical points overlap, so visible marks can be fewer than clients.
- Horizontal axis: inverse-hyperbolic-sine transform of the paired mean norm
  score. Vertical axis: the same transform of the paired mean profile score.
- Open gray circles represent honest clients. Open black triangles represent
  free riders. These truth labels are for evaluation, not detector inputs.
- Meaning: the scatter shows geometry for one recorded setting. It is not a
  decision boundary, an aggregate across seeds, or evidence that every strategy
  is separable. Repeated confirmation is governed by the algorithms.
- Drawing source: `figures/challenge_scores.tex`.

## Figure 4: Client participation and review states

- Five state nodes: Eligible at the top, Quarantined in the middle, Probation
  on the left, Cooldown on the right, Removed at the bottom.
- Eligible -> Quarantined: strong paired evidence, with a two-cycle review budget.
- Quarantined -> Probation: two consecutive clear cycles. Probation -> Eligible:
  one additional clear cycle. The return path is dashed.
- Quarantined -> Cooldown: review budget expires. Cooldown -> Eligible: after
  two sparse audits. This return path is also dashed.
- Fresh confirmation points toward permanent removal in red. The Eligible
  self-loop means an audit can open review without immediate quarantine.
- The in-image legend distinguishes transition, return and removal arrows.
- Meaning: these are principal participation paths. The confirmation rule can
  remove any nonremoved client once the same component has sufficient fresh
  evidence. Removal is not restricted to clients currently drawn in quarantine.
  Strong/unresolved/clear are evidence outcomes, not extra participation states.
- Drawing source: `figures/client_states.tex`.

## Figures 5 and 6: MNIST and CIFAR-10 score geometry

- Each figure has 16 panels. Columns are FR1 unchanged response, FR2 random
  fabrication, FR3 history averaging and FR4 received-trajectory imitation.
- Rows are 30% IID, 30% non-IID, 40% IID and 40% non-IID, in that order.
- Horizontal and vertical axes are the transformed paired mean norm and profile
  scores used in Figure 3b. Blue open circles are honest clients. Orange filled
  triangles are free riders. These are evaluation labels, not detector inputs.
- Each panel represents round 20 of a recorded execution with 100 clients. These plots
  show response geometry and possible overlap, not pooled three-seed outcomes.
  Do not infer the final removal decision from distance on this plot alone.
- Sources: `generated/geometry_mnist.tex`, `generated/geometry_cifar10.tex`.

## Figure 7: Accuracy trajectories

- Eight panels: MNIST on the first row, CIFAR-10 on the second. Columns cover
  30% IID, 30% non-IID, 40% IID and 40% non-IID.
- Horizontal axis is communication round, displayed from round 20 onward.
  Vertical axis is test accuracy. The embedded source tables retain all 100 rounds.
- Teal denotes BaitFL. Orange denotes no-defense federated averaging. BaitFL
  uses three seeds. Baseline coverage is one seed per MNIST setting and two
  or three per CIFAR-10 setting. Refer to the manuscript for averaging details.
- Meaning: these are observed learning trajectories under persistent free
  riding. Coverage is unequal. They do not isolate the cost of auditing or
  supply an honest-only oracle comparison.
- Source: `figures/accuracy_comparison_layout.tex`.

## Figure 8: Time to target accuracy

- Two panels: MNIST target 98%, CIFAR-10 target 70%. Each contains four paired
  bars for 30% IID, 30% non-IID, 40% IID and 40% non-IID.
- In every pair, the left teal bar is BaitFL and the right orange bar is no
  defense. Vertical axis is summed logged time to first target crossing, in minutes.
- The analysis uses 63 matched run pairs. Seed results are averaged within an
  attack setting, then the four attacks receive equal weight. The targets were
  chosen for this retrospective comparison.
- Meaning: shorter time can result from removing fabricated contributions that
  dilute aggregation. It does not establish a controlled audit-overhead advantage.
  Exact bar values are in the adjacent TikZ `coordinates` lists.
- Source: `generated/time_target_figure.tex`.

## Figure 9: Instrumented round timing

- Two dataset panels compare BaitFL and STD-DAGMM in separately instrumented
  100-round executions using non-IID FR3 at 40% free riders.
- Vertical axis is average seconds per round. The figure distinguishes recorded
  computation and elapsed time. In each pair, the left teal bar is BaitFL and
  the right orange bar is STD-DAGMM. The timing table supplies the phase breakdown.
- Checking accounts for 0.58% of MNIST computation and 0.89% of CIFAR-10
  computation in these runs. These are fractions of measured computation time,
  not communication time, all deployments, or total training rounds.
- STD-DAGMM uses five auxiliary training epochs per round in this timing
  configuration and retains clients. This measures that configuration's cost.
  It is not a validated convergence or detection-performance comparison.
- Source: `generated/timing_phases_figure.tex`.

## Figure 10: Complete-removal round

- Two panels: MNIST and CIFAR-10. Horizontal categories are FR1 through FR4.
  Vertical axis is the round when all free riders have been permanently removed.
- Teal open circle: 30% IID. Teal filled square: 40% IID. Violet open circle:
  30% non-IID. Violet filled square: 40% non-IID. Small horizontal offsets make
  the four series distinguishable within each attack category.
- A point is the mean over three seeds. Whiskers span the observed minimum and
  maximum, not a confidence interval. Coincident endpoints make some whiskers
  invisible. Across settings, completion ranges from round 30 to round 90.
- Meaning: the plot reports completion speed. Precision, honest removals and
  withholding costs must be read from the associated tables and discussion.
- Source: `generated/completion_rounds_figure.tex`.
