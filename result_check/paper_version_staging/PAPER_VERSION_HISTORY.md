# Paper Version History

The files directly inside `Paper/` are the current working version. Completed revisions are preserved under `Paper/versions/` and should not be edited after they are archived.

## v01 — Pooled V8 results

Date archived: 2026-09-21

- Added dedicated related-work coverage of FRAD, PASS, FRIDA, statistical detection, and verification approaches.
- Defined FR1–FR4 and the attacker knowledge assumptions.
- Added algorithmic SWT-CP methodology and lightweight complexity discussion.
- Combined repeated MNIST IID and non-IID experiments into pooled 30% and 40% attacker results without seed-specific table rows.
- Retained failed experiments inside pooled statistics rather than selecting only favorable repetitions.
- Documented FR4 instability, anchor contamination, candidate quarantine, limitations, and execution cost.
- Compiled successfully as a four-page IEEE-format preprint.

Archived files: `versions/v01_pooled_v8/paper.tex`, `paper.pdf`, and `refs.bib`.

## v02 — Introduction draft

Date archived: 2026-09-21

- Left the abstract empty for later drafting.
- Rewrote the introduction to begin with the purpose and standard training process of federated learning.
- Introduced free riding as failure to contribute meaningful local work because of limited data, limited resources, or resource-saving incentives.
- Distinguished free riding from active poisoning: its primary harm is omitted useful contribution rather than deliberate corruption.
- Explained the counterfactual cost of missing honest updates and the resulting dependence on the remaining clients.
- Kept detailed server-observability and threat-model discussion out of the introduction for placement in a later section.
- Reduced the method transition to a short high-level introduction of SWT-CP.
- Left the final bullet-point contribution statement empty for later drafting.
- Reorganized and condensed Related Work into three parts: free-rider attacks, statistical/learning-based detection, and challenge-based/verifiable computation.
- Focused the discussion of FRAD, PASS, and FRIDA on their principal contributions and limitations rather than acronym expansion or implementation detail.
- Explicitly identified gaps involving adaptive imitation, auxiliary-model overhead, calibration under heterogeneity, public canary objectives, attributable-update access, and hardware/cryptographic deployment cost.
- Expanded FR1--FR4 into separate attack definitions with equations, operational behavior, attacker knowledge, and trap interaction.
- Reorganized SWT-CP methodology into four phases: warm-up, double coverage, surveillance/candidate confirmation, and weighted suspicion/decision.
- Added a separate algorithm for each phase and retained the shared norm/profile evidence equations and lightweight-complexity analysis.
- Presented detection primitives and lightweight implementation as framing text rather than additional phases.
- Added automatic references from every phase description to its corresponding algorithm.
- Added concise design rationales for the trap scale and floor, robust thresholds and MAD floors, warm-up and sweep lengths, group and anchor counts, confirmation requirements, penalty weights, removal threshold, and rehabilitation rule.
- Added MNIST and CIFAR-10 best-observed multi-seed result tables without seed identifiers or execution-count columns.
- Replaced the earlier pooled-run tables with configuration-level precision/recall/F1/accuracy and attack-level F1 summaries.
- Explicitly labeled the selected figures as best-observed capability results rather than averages or robustness estimates.
- Consolidated MNIST and CIFAR-10 IID/non-IID performance into one table grouped by 30\% and 40\% free-rider share, marking unavailable CIFAR-10 30\% results with dashes.
- Added a reproducible eight-panel cumulative-detection grid: FR1--FR4 by column and MNIST/CIFAR-10 by row, including the round-30 guide and the longer non-IID FR4 tails.
- Added a compact execution-cost table containing device, mean seconds per round, and peak process memory; omitted redundant derived duration and aggregation-count columns.
- Compiled successfully as a six-page IEEE-format preprint after adding the detection-progress figure.
- Completed the abstract with the problem, server-side method, evaluation scope, best-observed detection results, and principal remaining limitation.
- Completed the introduction's contribution list, emphasizing lightweight hidden challenges, dual robust evidence, staged confirmation and rehabilitation, the four-attack evaluation, and transparent reporting of heterogeneous-data sensitivity.
- Enlarged the eight-panel detection-progress figure and its inter-row spacing to improve readability in the two-column layout.
- Added the completed CIFAR-10 30% IID and non-IID results to the performance table, detection curves, execution-cost table, abstract, and discussion.
- Reported the strong IID result and the substantially weaker non-IID precision explicitly; the completed non-IID runs are not disguised as unevaluated data.
- Removed the provisional SWT-CP method name and adopted the descriptive working title ``Lightweight Trap-Based Free-Rider Detection and Mitigation in Federated Learning.''
- Reworked the introduction's contributions into bold label-and-explanation bullets covering lightweight server-side operation, trap-based challenges, robust detection and mitigation, and evaluation across four attacks, two datasets, and IID/non-IID settings.
- Removed the visible qquad text caused by missing LaTeX command markers and reformatted the affected threat-model equations as aligned multiline expressions.
- Restored the paired threat-model expressions to a single line using a valid LaTeX quad separator.
- Added comparative result analysis by attacker share, dataset, data partition, and attack type.
- Removed the discussion paragraph emphasizing intentional selection of the best seed observation.
- Added a dedicated assumptions and future-work section covering a fixed client population and attacker behavior, honest-majority operation, no new or on-off free riders, non-collusion, defense knowledge, dropout, partial training, mixed attacks, and secure aggregation.
- Simplified the result table and figure captions and added a float barrier so all result visuals appear before the discussion, conclusion, and references.
- Expanded the explanation of Figure 1, especially the gradual FR4 staircase under 40\% non-IID data, and connected it to trajectory imitation, wider honest-update variation, repeated traps, and cumulative penalties.
- Revised the abstract for clearer result wording and removed semicolons and dash-based asides from the paper's prose where natural sentences were clearer.
- Removed the student ID and added ``MSc Thesis'' and ``Last updated on 24 September 2026'' to the author block.
- Moved the last-updated date from the centered author block to the upper-right corner of the first page.

Archived files: `versions/v02_introduction_draft/paper.tex`, `paper.pdf`, and `refs.bib`.

## v04 — V8 all-run attack-behavior statistics

Date: 2026-10-08

- New revision based on v2's v8 methodology; v2/v3 archives remain unchanged.
- Analyze all 67 completed v8 runs across all 32 dataset/partition/share/attack
  combinations, excluding the 16 baseline-detector entries.
- Add attack-specific tables for both shares and all four dataset/partition
  settings, with mean/sample-SD recall, ranges, pooled precision/F1, honest
  removals, full-detection success counts, conditional completion timing and
  final model accuracy. Failed runs remain in detection summaries.
- Add round-20 norm/profile evidence tables and exported score quartiles;
  explicitly distinguish client summary flags from per-probe joint evidence.
- Replace best-observed abstract/results/conclusion claims with all-run findings
  and limitations. Keep later paired/shadow experiments outside this revision.
- Export per-run and grouped CSVs, configuration checks and source-file hashes.
- Reproduce using `build_paper_v4_v8_statistics.py`; source/PDF/data live under
  `versions/v04_v8_behavior_statistics/`.
- Aggregation unit test passed; PDF compiled with BibTeX and resolved references.
  Outcome and evidence pages were visually checked for clipping/readability.

## v05 — V15.4 CIFAR-10 fresh-certificate memory

Date: 2026-10-15

- New source and permanent blank-template PDF under
  `versions/v05_v15_4_cifar10/`; earlier versions remain unchanged.
- Replace v8 anchors/penalties and previous-model FR1 with the actual v15.4
  method: strict norm certificates, diagnostic diagonal score, non-consecutive
  fresh same-component confirmation, clean-cycle clearance and bounded review.
- Blank tables cover all sixteen CIFAR-10 seed-42 runs at 30% and 40%, IID and
  non-IID, FR1-FR4. Older MNIST versions are not mixed into this evaluation.
- Separate removal quality, temporary honest exclusion, candidate flags, model
  accuracy and whole-simulator resources. Isolated detector overhead is not
  inferred from simulator RSS or round time.
- `build_paper_v5_v15_4.py` fills tables/curves only after both batches complete
  and logs/provenance validate; completed detection failures remain included.
- The recovery launcher checks this after completion, without changing training
  or task credentials. The permanent blank template remains available.
- Single-seed/development selection and correlated-certificate risks are
  explicit. This is a local draft requiring author review, not a submission.

## v06 — V2-style full v15.4 study

Date: 2026-10-17

- Rewrote the manuscript as a full paper following v02's organization and tone:
  Abstract, Introduction, Literature Review, Threat Model, Proposed Methodology,
  Results, Result Analysis, Security Analysis, Conclusion, and appendices.
- Include all 32 completed v15.4 runs: MNIST/CIFAR-10, IID/non-IID, 30%/40%,
  FR1–FR4, seed 42; no older-method data or best-seed selection.
- Separate permanent removal from candidate flags, temporary quarantine, trap
  exclusion, utility, detection latency, and whole-process cost.
- Add eight-panel detection and accuracy figures, grouped performance/safety/cost
  tables, and complete per-run appendix tables with machine-readable exports.
- Give explicit confirmation invariants and discuss identifiability, adaptive
  evasion, trap secrecy, evidence dependence, long-lived false evidence, honest
  majority, secure aggregation, availability and computational limitations.
- Correct current FR1 semantics and avoid importing the old v8 anchors/penalties.
  Keep single-development-seed and missing-control/ablation limitations explicit.
- Validate all logs and recorded detector source hashes; preserve previous paper
  versions and experiment inputs. Rebuild with `build_paper_v6_full_study.py`.
- Source and PDF: `versions/v06_v15_4_full_study/paper_v6.tex` and `paper_v6.pdf`.

Visual/analysis revision requested 2026-10-18:

- Replace repetitive perfect-outcome columns with grouped precision/recall,
  separate FR1–FR4 final test accuracies and round time. Expand FR3 honest impact
  into run-level candidate, quarantine, trap and additional-exclusion counts.
- Move recall curves to the appendix; add client score clouds at both shares,
  raw-norm histograms and mean/IQR score evolution. Zoom late-accuracy panels
  with explicit independent scales; retain full trajectories in the appendix.
- Expand measured resource ranges and compare only completed matching v15.3
  executions. Add architecture-derived payload sizes and a separate complexity
  section including median sorting, quadratic comparisons and retained logging.
- Do not change detector code, thresholds, experiment data or detection totals;
  computed resource estimates are explicitly not isolated overhead measurements.

## Versioning procedure

Full-horizon STD-DAGMM update, 18 October 2026:

- Replace ten-round projections with both completed actual 100-round executions.
  Refresh component tables, full trajectories, measured sums, source provenance
  and standalone timing report; keep earlier pilots separately.
- Report the selected non-IID FR3 reproduction's poor flagging honestly: zero
  free riders ever flagged and all 60 honest clients flagged at least once in
  both datasets; flags are observational, not permanent removals. Keep the
  five-epoch/author-code-fidelity and CIFAR memory-pressure caveats.

Additional timing/layout revision, 18 October 2026 (v06 working manuscript):

- Add segmented native STD-DAGMM timings for MNIST/CIFAR-10 (ten actual rounds
  each), actual 100-round v15.4 means, explicit conditional STD projections,
  full-round phase amortization and measured round trajectories. Preserve
  missing task/communication measurements and host/memory-pressure caveats.
- Widen eight-panel score/accuracy figures to two columns and enlarge the
  histogram, score-trend and resource panels. Preserve data and detector code.
- Standalone tables/vector charts: `analysis/timing_breakdown/timing_report.pdf`.

## v07 — V6 content in the V5 template

Date: 2026-10-30

- Preserve v6's full v15.4 manuscript, results, figures, tables, references,
  appendices, generated assets and evidence in a new independent directory.
- Restore v5's IEEEtran conference layout and Times typography, default float
  spacing, author block, and centered revision line. Make the abstract bold.
- Remove the duplicated Introduction heading and update the revision's build
  instructions. No experimental values or detector behavior are changed.
- Source/PDF: `versions/v07_v6_content_v5_template/paper_v7.tex` and
  `paper_v7.pdf`; rebuild with the accompanying `build.ps1`.
- PDFLaTeX/BibTeX compilation passed (25 pages), with no unresolved citations,
  references or overfull boxes. First page and an eight-panel figure were
  visually inspected; copied assets and the scientific body were checked
  against v6.

BaitFL introduction revision, 30 October 2026:

- Name the method BaitFL in the title, PDF metadata, abstract, and introduction.
- Rewrite the introduction around federated training, sensitive-data use cases,
  free riding, heterogeneous honest updates, and challenge-based auditing.
  Distinguish data locality from guaranteed privacy and qualify communication
  savings. Add Kairouz et al. (2021) and Rieke et al. (2020) as background sources.
- State four contributions: lightweight server-side detection, repeated-evidence
  confirmation, bounded mitigation/rehabilitation, and four-behavior evaluation.
- Move code v15.4, paper v7, and the date to the first-page top right. Color the
  bold abstract blue. Preserve the remaining study and experiment-derived assets.

Author introduction follow-up, 30 October 2026:

- Retain the author's revised introduction with small edits for claim precision
  and grammar. Replace the detailed method transition with one summary sentence.
- Bold the contribution lead-in and preserve bold labels. Add explicit TeX Gyre
  font selection for LuaLaTeX/XeLaTeX after the editor's LuaLaTeX output lost
  Times bold/italic styles through font substitution.
- Mark sections from Literature Review onward red, retaining the blue abstract
  and black introduction. Experimental text and values are unchanged.

Citation and literature-review revision, 30 October 2026:

- Sort/compress IEEE numerical citations; repair compound-author parsing,
  proceedings metadata, article numbers, preprint classification, and source links.
- Reorganize the red literature review into approach, contribution, and limitation
  paragraphs covering attack evolution, STD-DAGMM, FRAD, PASS, FRIDA, and secure
  aggregation. Link STD-DAGMM fitting cost to the later native-workflow experiment.
- Distinguish peer-audit privacy exposure from a demonstrated breach, acknowledge
  PASS's protections, and separate FRIDA's membership and property variants.
  Record sources and review limits in the v7 `CITATION_REVIEW.md`.
- Preserve the introduction, abstract, method, and experiment-derived assets.

Threat-model revision and editor citation repair, 30 October 2026:

- Preserve the author's literature-review edits and black text. Rewrite the
  threat model in black with natural participant, server, scope, and attack
  descriptions; keep later sections red.
- Define persistent non-training clients, whether unable or unwilling to train;
  explicitly exclude partial/on-off training, collusion, identity changes,
  arrivals/dropouts, and audit-adaptive response strategies. Retain an honest
  majority and fixed per-experiment fabrication strategy.
- Remove simulator-label bookkeeping, previous-manuscript comparisons, and
  parameter-generalization commentary from the threat model while preserving
  the four attack equations and their numerical settings.
- Diagnose direct editor builds missing `paper_v7.bbl`; publish the generated
  bibliography and citation state beside the source through `build.ps1`.

Methodology and algorithm revision, 30 October 2026:

- Generalize FR3 to history length H and record H = 5 in the experiment setup.
  Preserve the experimental data and other attack parameters.
- Rewrite Proposed Methodology in natural prose without semicolons or prose
  dashes. Remove commentary about unused features and earlier implementation
  variants while retaining the operational definitions and numerical settings.
- Add algorithms for warmup, paired coverage, confirmation/review, sparse audits,
  and the overall procedure. Refer to the algorithms and selected line ranges
  through labels. Check scheduling, component memory, exact replay, review expiry,
  cooldown, and aggregation order against v15.4.
- Keep methodology black and Results onward red. Flush methodology algorithms
  before Results so the presentation follows the procedure's sequence.
- PDFLaTeX/BibTeX validation passed (26 pages). All five algorithm references
  and selected line references resolve, with no overfull boxes. Algorithm pages
  and the black-to-red transition at Results were visually inspected.

Threat-model precision follow-up, 30 October 2026:

- Merge participation assumptions, explicitly exclude client sampling, distinguish
  responses from aggregation, allow heterogeneous honest data, explain the
  honest majority, and state the absence of secure aggregation.
- Connect fabricated and returned-model notation, index noise and differences by
  client, and state floating-state arithmetic with integer entries copied intact.
- Replace the FR4 noise prose with the implemented vector scaling equation,
  retaining the numerical floor in both norms and the distinct cold start.
  Explain the effect of received traps on its history.
- Reference the existing evasion subsection. Keep persistent non-training as a
  scope assumption without asserting that trap construction cannot be known.

Multiple-seed Table 1 and experimental setup revision, 30 October 2026:

- Replace the informal setup/grid description with a formal account of two
  datasets, four attack types, IID/non-IID partitions, two attacker proportions,
  repeated seeds, and fixed training conditions. Omit seed values and total
  execution count from the setup prose and Table 1 caption.
- Validate the complete three-seed grid (42, 43, 73) using
  `build_multiseed_table.ps1`. Check completed status, settings/policy, source
  hashes, initial coverage, removal labels/counts, and utility/timing consistency.
  Retain per-run values, means, accuracy SDs and provenance in `generated/multiseed/`.
- Recalculate Table 1, group detection/accuracy columns, merge repeated dataset
  and partition labels, and separate MNIST/CIFAR-10 blocks with a rule.
- Include all three honest removals from added replications. Update study-wide
  claims, latency range, and limitations. Label retained score plots, detailed
  exclusion records and resource case studies as representative diagnostics.
- Preserve raw experiment logs and previous paper versions. Snapshot source
  hashes match the recorded implementation after LF normalization of checkout
  line endings; retain raw and normalized hashes in the new provenance.
- Compilation and citation/reference checks pass with no overfull boxes. The
  setup and revised Table 1 were visually inspected. Table 1 precedes the
  diagnostic figures and retains all three-seed outcomes, including false removals.

For each substantive revision:

1. Continue editing the working `Paper/paper.tex`.
2. Compile and validate citations and references.
3. Copy the validated source, PDF, and bibliography into a new immutable `versions/vNN_description/` directory.
4. Add a concise entry here recording content changes and validation status.
