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

Table reporting and Figure 3 revision, 31 October 2026:

- Simplify the free-rider response preamble to its notation definition.
- Remove explanations beneath numeric tables and integrate definitions and
  aggregation rules into the relevant manuscript segments with table references.
- Extend the validated three-seed reporting to honest-client exclusion, CPU
  resources, and both detailed attack tables. Include all honest removals and
  quarantine cases. Table 2 groups dataset/partition labels and separates client
  counts from exclusion-duration columns.
- Regenerate historical and native-workflow timing comparisons from their own
  measured inputs, retaining matched single-case conditions. Recalculate the
  architecture-derived payload table. Do not pool these comparisons into study
  means or alter experimental source logs.
- Redesign Figure 3 into chronological rows with common axes, a separate legend,
  outside annotations, and an evidence-confirmation diagram. Verify histogram
  population totals and paired norm-certificate counts. Preserve Figure 1.
- Update the manuscript revision date to 31 October 2026.
- PDFLaTeX/BibTeX compilation passes without unresolved citations/references,
  overfull boxes, or oversized floats. Visually inspect the redesigned Figure 3
  and grouped Table 2. All numeric table notes are removed from beneath tables.

Baseline comparisons and figure revision, 1 November 2026:

- Make Experimental Setup black. Keep subsequent result text red and retain
  code v15.4 and paper v7 in the updated revision stamp.
- Expand the two score figures to 16 panels per dataset with four columns,
  both attacker proportions and partitions, short captions, and separate legends.
  Explain the diagnostics in referenced prose. Add multirows to Table 3.
- Replace Table 4's previous-version comparison with the completed no-defense
  FedAvg baseline grid. Validate all 32 primary matched pairs and three additional
  CIFAR-10 pairs, including identical warmup accuracies and all-client aggregation.
  Keep the additional incomplete-grid replication separate in the appendix.
- Add matched baseline accuracy trajectories, accuracy changes, timing changes,
  and measured late-round variability. Preserve individual accuracy losses and
  increases in execution time rather than reporting only improvements.
- Replace the overlapping resource figure with baseline changes. Rebuild the
  timing breakdown as BaitFL round phases beside STD-DAGMM computation stages,
  followed by full-horizon mean round time and actual timing-difference plots.
  Report missing BaitFL operation timers plainly in the text.
- Retain all raw experiment logs and measured values. Add source-hashed paired
  comparison exports and a reporting regeneration script. Remove the historical
  code-version comparison from the manuscript and active table generator.
- Compile the 28-page PDF with PDFLaTeX/BibTeX, resolving all references and
  citations without overfull boxes or oversized floats. Visually inspect setup
  color, grouped Tables 3/4, the expanded score figures, baseline effects, and
  timing breakdowns. Widen plot separation to remove label collisions and keep
  figure groups near their referenced discussions.

Instrumented MNIST timing integration, 3 November 2026:

- Import 27 byte-verified evidence files from study commit
  `8519fe180f337486e18dfc752cfedfcef64eaf53`, including the completed BaitFL
  and STD-DAGMM timing records and instrumentation sources. Keep paper/code
  versions at v7/v15.4 and update the revision stamp.
- Validate both 100-round runs, matching experimental settings, the frozen
  engine hash, component sums, elapsed accounting, fitting-substage bounds,
  and complete phase coverage. Verify all 100 BaitFL accuracy observations
  agree with the corresponding study run. Do not add these timing runs to
  detection-study averages or mix them into the older no-defense comparison.
- Rebuild Tables V–VII and Figures 7–9 using 36.92/52.26 s computation means
  and 40.92/62.83 s elapsed means for MNIST. Report trap, scheduling, feature,
  decision, logging, checkpoint, and harness costs with their actual boundaries.
  Retain CIFAR-10's existing measurements and mark absent operation/wall timers.
- Keep decision-block timing distinct from an isolated removal-operation cost.
  Keep joint training and mixture finalization within STD fitting. Correctly
  classify single audits separately from complete screening cycles.
- Update the abstract, timing analysis, computational discussion, conclusion,
  and reproducibility notes. Preserve the blue abstract, black setup, existing
  baseline results, and all experimental source logs.
- Regenerate the complete reporting pipeline and compile the 28-page PDF.
  Component/wall accounting and phase coverage pass. Citations and references
  resolve without overfull boxes or oversized floats. Visually inspect the
  computation/elapsed tables, component plots, and timing-gap figures.

Instrumented CIFAR-10 timing and wider score panels, 4 November 2026:

- Keep the working paper at v7/code v15.4. Widen Figures 1 and 2 with explicit
  plotting-area dimensions; preserve all 16 panels, points and independent ranges.
- Import 27 byte-verified CIFAR-10 timing evidence files from study commit
  `182ba40c3d036d7dc1cbe07975d6c0a62b1cefd2` without switching branches.
  Share the import and validation scripts across MNIST/CIFAR-10, retaining the
  previous MNIST entry points and its original evidence commit.
- Replace the old CIFAR timing case in Tables V–VII and Figures 7–9 with the
  completed instrumented 100-round pair. Include matching stages, elapsed time,
  phase costs, full trajectories and both computation/elapsed differences.
  Update the abstract, timing analysis, conclusion and reproducibility notes.
- Validate completion, source/configuration provenance, all per-round sums,
  nested fitting timers and phase coverage. All 100 BaitFL accuracies match the
  corresponding original study execution on each dataset. Keep these cases
  separate from replicated detection and no-defense averages.
- Compile and visually inspect the 28-page PDF: widened score panels, combined
  timing tables, stage bars and computation/elapsed traces. No overfull boxes,
  oversized floats, unresolved references or citations remain.

Methodology overview and free-rider illustration, 4 November 2026:

- Insert the approved BaitFL overview at the start of Proposed Methodology,
  removing its internal heading and subtitle and retaining no round numbers.
- Draw a vector illustration of three devices training on private local data
  and one free rider returning a perturbed response without training. Place it
  beside the Introduction's explanation of free riding. Local data/resource
  conditions are illustrative and are not information sent to the server.
- Keep editable standalone TikZ sources and vector PDFs under `figures/`.
  Build them through `build_diagrams.ps1` before the paper; preserve standalone
  PDF/SVG/PNG previews under `analysis/`. Use LaTeX labels for automatic figure
  numbering and cross-references.
- Compile and visually check the 29-page PDF. The attack illustration appears
  on page 2 and the methodology overview on page 5, with the heading removed.
  No overflowing boxes, oversized floats or unresolved references remain.

Section II language and limitations, 4 November 2026:

- Rewrite the related-work discussion with varied sentence construction and
  restrained limitations tied to each approach. Separate low utility or an
  anomaly score from proof of missing training.
- Check the original Lin, Fraboni, Zhu, PASS and FRIDA manuscripts. Discuss
  auxiliary-model fitting, peer-evaluation work, canary training, auxiliary data
  and property inference without claiming that peer auditing gives the server
  raw datasets or that inference automatically invalidates federated learning.
- Acknowledge FRIDA's reported adaptive cosine/loss distinction and privacy
  protections, and retain BaitFL's individual-response visibility and withheld
  trap-contribution costs. Record interpretation limits in `CITATION_REVIEW.md`.
- Rebuild and visually inspect the 29-page PDF. Citations and references resolve
  without overflowing boxes or oversized floats. No experiment data or detector
  code changes are included.

Section III tone and attack-definition layout, 4 November 2026:

- Rewrite the threat model with varied sentences while preserving the trusted
  server, complete participation, fixed population, honest-majority and
  persistent non-adaptive attack assumptions and the server's knowledge limits.
- Add space before FR1 and place every attack description beneath its bold
  title. Shorten repeated explanation and align FR4's difference/response
  equations. Keep the four definitions together at the normal body-text size.
- Preserve all attack equations, noise parameters, floating-entry scope,
  histories, cold-start behavior and cross-references. Visually confirm that
  FR1–FR4 fit in the left column on page 4. Compile without unresolved
  references, overflowing boxes or oversized floats.

Section IV implementation audit and phase layout, 4 November 2026:

- Check all six recorded v15.4 source hashes and called helpers. Match trap
  generation, profiles, robust scores, screening, certificates, exact replay,
  confirmation, grouping, review, recovery, cooldown and aggregation to code.
  Record the mapping in `METHODOLOGY_REVIEW.md`.
- Keep four algorithms, one per phase, with important line labels. Remove the
  duplicate overall procedure subsection/algorithm and explain the main loop
  in the section opening and Figure 2's feedback path. Add Phase I–IV diagram
  labels and match Figure 1's outer border.
- Explain the profile-score equation, lower-middle coordinatewise profile
  median, exact-zero/fingerprint send-back check, all-active references,
  nonconsecutive fresh statistical certificates and bounded review separately.
- Confirm a frozen-engine edge case: cooldown-only audit findings can clear
  the quiet clock without opening review. Reproduce the original control flow
  with a small standard-library-only check. No matching last-audit/ordinary-tail
  pattern was observed in the 96 completed runs. Preserve the implemented
  algorithm and disclose the limitation in the reproducibility appendix.
- Distribute algorithms with nearby explanatory text before Results. Preserve
  the experimental code and records; this is a manuscript/diagram revision.
- Compile the 30-page PDF and inspect the phase diagram and algorithm/text
  layouts on pages 5–7. Exactly four algorithms remain. References resolve
  without overflowing boxes or oversized floats; refresh vector/PNG previews.

Section V results, data refresh and visual consolidation, 4 November 2026:

- Validate all 96 primary multi-seed executions. Refresh no-defense comparisons
  from 62 completed matched pairs, using verified published snapshots for
  records missing in the local checkout. Keep baseline coverage provisional,
  exclude partial executions and average matched seeds within attacks before
  weighting attacks equally. Preserve running experiments and detector code.
- Keep Evaluation Metrics red, cover every reported measure and timer boundary,
  and remove textbook metric equations. Separate model test accuracy from
  detection performance and quarantine from permanent removal.
- Improve Tables I/II with partition dividers and integer ranges. Preserve
  Figures 3/4. Replace the histogram with an evidence/removal timeline, cover
  all attacks in score trends and simplify matched accuracy into eight panels.
- Remove duplicate baseline bars and overlapping native timing tables/plots.
  Keep one stage/percentage table and the requested average-time chart
  (formerly Figure 10, now Figure 8). State measured checking shares and
  whole-workflow timing limitations. Retain raw timing artifacts.
- Check equal-weight means, unique pairs and accuracy plot/table agreement.
  Compile and visually inspect the tables and figures with resolved references
  and no overflowing boxes. Document the revision in `RESULTS_REVIEW.md`.

Merged results discussion and closing-section revision, 4 November 2026:

- Merge Results and Result Analysis into Results and Discussion. Organize the
  red Evaluation Metrics subsection by detection, accuracy/honest participation
  and lightweightness. Keep the overall test-accuracy range and multi-seed
  wording, and remove procedural table narration and fractional-client phrasing.
- Verify the three honest-removal triggers from completed decision records:
  two repeated profile-distance cases in MNIST non-IID FR3, and a late repeated
  norm case in FR4. Explain persistent legitimate heterogeneity and the overlap
  caused by FR3's received-model history without claiming perfect imitation.
- Remove the evidence timeline, mean score trends and redundant accuracy plots
  from the manuscript. Keep score geometry and the requested average-time chart,
  now Figure 5. Table V reports seconds saved per round alongside percentages.
- Rewrite complexity, security, future work, conclusion and abstract. Include
  sparse audits in the total detector-work bound, distinguish payloads from
  process RSS, and retain the scope of the measured timing comparisons.
- Preserve experimental code, all result records and the running queue. Compile
  and inspect the merged section, timing table and chart, complexity, security
  and closing sections. Record the review in `RESULTS_REVIEW.md`.

Timing figures, round variability and appendix visibility, 4 November 2026:

- Make Evaluation Metrics black. Use ragged-bottom layout from Results onward
  and compact float spacing to avoid stretched paragraph gaps.
- Redesign Figure 5 with adjacent BaitFL/STD-DAGMM bars for computation and
  elapsed time, using teal/orange method colors. Add Figure 6 with multi-seed
  mean complete-removal rounds and observed minimum–maximum ranges.
- Add mean/sample SD to Table V. Calculate combined-stage and checking SDs
  from per-round sums, preserving covariance. Keep savings and percentage
  shares as full-horizon aggregates and export detailed table statistics.
- Expand Table IV's pp abbreviation to percentage points. Temporarily comment
  out the appendix source and remove all active appendix references.
- Validate native timing records, SD calculations and completion summaries.
  Compile and inspect metrics, table labels, both new charts and spacing.
  Experiment code, frozen evidence and the running queue remain unchanged.

Supplied reviewer-report revision, 4 November 2026:

- Track feasible review fixes and remaining experiments in `REVIEW_RESPONSE.md`.
  Retain three seeds and distinguish descriptive pooled outcomes from run-level
  uncertainty. Refresh 63 completed matched baseline pairs.
- Add 17 source-checked references and remove the medical framing/reference.
  Cover robust aggregation, heterogeneous optimization, proof of learning,
  verifiable training, Shapley valuation and update leakage. Add a qualitative
  requirements table without claiming an empirical ranking across all methods.
- Shorten the abstract, lead with checking shares, state three seeds, remove
  thesis/version labels and update the roadmap. Add method intuition and a
  notation/settings table. Explain fixed design choices and the profile gate.
- Add accuracy SDs, include all attacks in honest-impact reporting, clarify
  resource/exclusion units and remove duplicate round time. Explain unassigned
  runtime separately from computation-stage measurements.
- Generate ordinary/challenge norm boxplots from recorded first-cycle responses,
  with per-client summaries and hashes. Label them observational, not an ablation.
  Merge security and future work into Discussion and Limitations, state evidence
  availability and preserve the disclosed audit-clock implementation limitation.
- Compile with 31 resolved references and inspect tables, attack layout, diagrams
  and boxplots. Keep appendix source commented out. Experimental code and the
  running queue are unchanged; no unperformed tests or results are invented.

Figure 5 redesign after reviewer-response follow-up, 4 November 2026:

- Replace the initial ordinary/challenge boxplots with paired client scatters.
  Match each client's eight-response ordinary mean to its two-challenge mean,
  retain the asinh transform and use shared scales within each dataset.
  The diagonal indicates equal response sizes. Count coincident FR1 zero
  responses explicitly, without adding display jitter.
- Export 800 paired client records and a standalone vector/raster preview.
  Update the manuscript and review tracker while preserving the diagnostic's
  observational scope and the three-seed primary evaluation.

Distribution-curve alternative for Figure 5, 4 November 2026:

- Replace the paired scatter with empirical cumulative response-size curves
  to distinguish Figure 5 from the norm/profile scatter panels in Figures 3/4.
  Color identifies client class, line style ordinary/challenge condition.
- Normalize each class to 100% using exact empirical ranks, with no histogram
  bins or density smoothing. Retain per-client means and shared dataset scales.
  Export cumulative counts and refresh the standalone figure preview.
- Explain curve heights and the descriptive scope. Condition averages do not
  replace the detector's separate selected-response certificate checks.

Aggregate accuracy alternative for Figure 5, 4 November 2026:

- Replace the representative-run response diagnostic with accuracy versus
  training round across both datasets, partitions and attacker proportions.
  Use all three BaitFL replications, averaging within attack then equally
  across FR1–FR4. Baseline curves use available completed records, with
  their unequal coverage explicitly labeled.
- Place the figure in the model-utility comparison. Keep matched accuracy-gain
  estimates in the paired table. Display rounds 20–100 and share a vertical
  scale across each dataset row. Retain full 100-round exported trajectories.
- Add `build_accuracy_comparison.ps1` to reporting, validate endpoint/table
  agreement and source hashes, and refresh the standalone figure preview.

Second review revision, 4 November 2026:

- Address `v7 update 2.txt` using the existing records only. Preserve the current
  black manuscript, diagrams, 31-reference literature review, updated CIFAR-10
  timings, 63 matched baseline records, and commented appendices.
- Lead with 100% recall across 96 runs and three honest removals in two runs.
  Retain pooled precision as descriptive. Replace systematic accuracy-gain
  wording with comparable/slightly higher paired means and state coverage limits.
- Clarify candidate labels and their limited diagnostic value. Resolve notation
  conflicts, restore concise round/axis/coverage context in captions, and rename
  the timing I/O row. Keep the repository URL clickable and compact.
- Verify the cooldown-aware clock guard against all 622 logged audits. Both
  guards agree in all 609 empty and 13 nonempty cases. Correct the pseudocode,
  disclose its conditional equivalence, and provide an unapplied engine patch.
  Do not change the frozen engine, raw results, or protocol settings.
- Report STD-DAGMM's existing roundwise flags under its declared timing recipe,
  without treating them as a matched permanent-removal benchmark. Defer new
  experiments and public DOI release. Record dispositions and trace hashes in
  `REVIEW_RESPONSE_UPDATE_2.md` and `generated/review2/`.
- Compile and inspect the 20-page PDF. Citation/reference checks pass without
  overfull boxes or oversized floats. The proposed engine patch passes a dry-run
  application check and remains unapplied; all six study source hashes match.

### v07 layout follow-up — 4 November 2026

- Reorganize Table IV into a complete eight-row overview of all 32 settings and
  six rows of exclusion details. State explicitly that omitted event counts are
  zero. Retain the means and observed ranges, remove redundant decimal zeros,
  and move the table definitions into the results text.
- Remove the unnecessary pre-plot float barrier, prevent stretched gaps on float
  pages, and adjust placements so Tables III–IV precede the score panels and the
  accuracy/timing figures share pages with other content.
- Revalidate all 96 study runs and retain the original totals of three honest
  removals, 32 quarantine client-cases and 620 quarantine client-rounds. Compile
  and visually inspect the revised 19-page PDF. No overfull boxes, oversized
  floats or undefined citations/references remain. No new experiments are run.

### v07 subsequent review corrections — 4 November 2026

- Move the audit-clock trace account to Appendix A and state agreement on all
  622 recorded audits only. Resolve state/outcome and evidence/eligibility
  notation clashes and Algorithm 4 line references.
- Restrict the abstract's lightweightness claim to server computation and
  acknowledge the roughly 11% honest-response cost in IID settings.
- Use pooled detection counts consistently in Table III. MNIST non-IID 40%
  precision is 480/483 = 99.38%. Retain the previous seed-level mean separately.
- Add Figure 6 for descriptive time to first target crossing from 63 saved
  matched exports. Record 121 verified underlying logs and five missing baseline
  logs explicitly in provenance. No new training runs or engine changes.
- Revalidate the 96-run study, trace agreement and target-time calculations.
  Compile and inspect the 20-page PDF without undefined references/citations,
  overfull boxes or oversized floats. See `REVIEW_RESPONSE_UPDATE_3.md`.

### v07 spacing pass — 4 November 2026

- Allow text beneath the MNIST and CIFAR-10 score panels, replacing their
  dedicated float-page placement. Keep the inputs beside the score discussion.
- Use consistent 8-point spacing around floats and in-text algorithms, removing
  the results-only spacing override. Retain readable panel sizes and labels.
- Reduce the PDF from 20 to 19 pages. Verify that manuscript content is unchanged
  after excluding layout settings and moved figure inputs. Inspect all pages
  and larger score-panel/methodology previews. No undefined citations/references,
  overfull boxes or oversized floats are reported. No data or experiments change.

### v07 vocabulary and implementation alignment — 4 November 2026

- Unify Figure 2, Table IV and live prose under strong/unresolved/clear. State
  Figure 6's bar order in the caption and update Section VII-E for controlled
  target-accuracy comparisons with an honest-only oracle.
- Align Algorithm 4's clock assignment with the raw-finding guard used in the
  experiments. Appendix A describes its cooldown edge case and distinguishes
  the eligible-set alternative, which has not been rerun. The Python command
  available in this session is an unusable Windows alias.
- Explain that Figure 6 combines removal effects and auditing costs. Retain the
  controlled-advantage caution and keep target timing out of the abstract.
- Verify all 622 saved audits and the six study source hashes, retain all five
  checked measurement-export hashes, and inspect the rebuilt 19-page PDF.
  Compilation, citation/reference and overflow checks pass. No new training.
  See `REVIEW_RESPONSE_UPDATE_4.md` for dispositions.

For each substantive revision:

1. Continue editing the working `Paper/paper.tex`.
2. Compile and validate citations and references.
3. Copy the validated source, PDF, and bibliography into a new immutable `versions/vNN_description/` directory.
4. Add a concise entry here recording content changes and validation status.
