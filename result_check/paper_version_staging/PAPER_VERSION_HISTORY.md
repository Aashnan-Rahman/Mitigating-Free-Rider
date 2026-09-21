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
- Added a separate execution-cost table covering device, time per round, reconstructed 100-round duration, peak process memory, and mean updates included in aggregation.
- Compiled successfully as a five-page IEEE-format preprint after the methodology and result-table revisions.

Archived files: `versions/v02_introduction_draft/paper.tex`, `paper.pdf`, and `refs.bib`.

## Versioning procedure

For each substantive revision:

1. Continue editing the working `Paper/paper.tex`.
2. Compile and validate citations and references.
3. Copy the validated source, PDF, and bibliography into a new immutable `versions/vNN_description/` directory.
4. Add a concise entry here recording content changes and validation status.
