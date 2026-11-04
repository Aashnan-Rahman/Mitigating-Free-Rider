# Paper v7 — v6 content in the v5 template

Created 30 October 2026. Uses v5's IEEEtran conference template, default Times
typography and float spacing, and author block. Code v15.4, paper v7, and the
revision date appear at the top right of the first page. The abstract is bold
and blue. V6's additional plotting libraries and colors are
retained to support its figures.

The title is "BaitFL: Lightweight Trap-Based Free-Rider Detection and Mitigation
in Federated Learning." The introduction was rewritten around federated
learning, resource-saving free riders, detection under heterogeneity, and the
BaitFL approach, followed by four contributions. Two supporting references were
added for the background discussion. Diagnostic figures illustrate individual
executions. All primary study tables and associated claims use all completed
replications described below. The duplicated Introduction heading is removed
and build notes are updated. Experiment logs are unchanged. V5 and v6 are preserved.

The author's subsequent introduction rewrite is retained with small precision
edits. Its BaitFL transition is one high-level sentence, followed by the
contributions with bold labels. The abstract is blue; the introduction,
author-edited literature review, revised threat model, and methodology are black.
Results and later sections remain red. FR3 is defined with a general history
length H, with H = 5 stated
in the experimental setup. The methodology now contains one algorithm for
each of its four phases and an overall BaitFL algorithm. Text references use
LaTeX labels for both algorithm and line numbers. The pseudocode was checked
against the v15.4 scheduling, certificate memory, review, and aggregation code.
LuaLaTeX/XeLaTeX select TeX Gyre fonts explicitly so bold and italic
styles remain available, matching the Times-style PDFLaTeX layout.

The literature review was subsequently revised into approach/contribution/
limitation paragraphs, with source-backed discussion of auxiliary fitting,
peer-audit exposure, canary training, and property inference. Citation groups
are sorted using `cite`, and bibliography metadata and links are corrected.
`CITATION_REVIEW.md` records the supporting sources and interpretation limits.

The threat model states the study's persistent non-training scope, including
clients without training resources and clients choosing not to use available
resources. It defines the trusted server, fixed identities/population, full
participation, honest majority, no collusion, and fixed response strategies.
Partial and on/off training are excluded assumptions, not claimed physical
impossibilities. Earlier-draft comparisons and simulator bookkeeping are removed
from the threat model; attack equations and numerical settings are retained.

The threat model also distinguishes response participation from aggregation,
allows heterogeneous honest data, explains the honest majority assumption,
and states that the server sees individual responses without secure aggregation.
Noise and trajectory notation carry client indices. FR4's equation matches the
implemented scaling over all floating model entries, with a numerical floor in
both norms and a separate Gaussian cold start. Adaptive behavior is linked to
the existing evasion discussion without assuming the trap construction is
unknowable to attackers.

`generated/` and `evidence/` initially came from v6; `refs.bib` extends its
bibliography. Legacy generated status/provenance files describe the original
diagnostic replication. The current primary summary is
`generated/multiseed/summary.json` and its associated provenance.

The detection, honest-client exclusion, CPU resource, and detailed attack tables
use three completed v15.4 replications for every configuration, with
recorded seeds 42, 43, and 73. Run `./build_multiseed_table.ps1` from this
directory to validate and regenerate them. This checks 96 completed executions,
matching settings/policy and six recorded source hashes, initial paired coverage,
removal identities/counts, client-level exclusion records, and final accuracy
and round-time consistency. It calls `write_study_tables.ps1` for the additional
study tables and `refresh_context_tables.ps1` for measured STD-DAGMM component
times and calculated payloads. Their existing comparison
conditions remain separate from the replicated study. The
source snapshots match recorded hashes after normalizing checkout line endings;
both raw and normalized hashes are retained in the provenance file.

Precision and recall pool the four attacks within each seed and then average
those seed-level values. Accuracy averages three seeds independently for each
attack. Round time averages all attacks and seeds with equal weight. Per-run
values, grouped means, accuracy standard deviations, and input hashes are saved
under `generated/multiseed/`. No incomplete, failed-detection, or false-removal
case is silently dropped.

The repeated experiments remove all free riders but include three honest
removals, two in MNIST non-IID FR3 at 40% and one in its FR4 counterpart.
Overall pooled precision is 99.91%; the mean precision in Table 1's MNIST
non-IID 40% group is 99.39%. Abstract, results, analysis, and conclusion claims
are updated accordingly. Individual diagnostic plots remain explicitly
identified as representative executions.

The 31 October revision removes explanatory notes beneath tables and moves
their definitions into the referenced result segments. Table 2 uses grouped
client/client-round headers, merged dataset and partition labels, and separate
dataset blocks. It includes all FR3 configurations and the FR4 configurations
with honest quarantine or removal. Counts and per-execution exclusion percentages
are averaged across seeds. All 32 honest quarantine cases, 620 quarantine
client rounds, and three permanent honest removals are retained.

Figure 3 is rebuilt with `./build_norm_figure.ps1`. It has one chronological row
per attacker proportion, common axis limits, a separate color legend, counts
below the axes, and a diagram showing evidence retention and later confirmation.
The script verifies every plotted population and fresh paired norm-certificate
count. The threat-model preamble now only introduces the free-rider response
notation.

The 1 November revision makes Experimental Setup black and expands Figures 1
and 2 to 16 panels each, covering both shares, both partitions, and all attacks.
Four panels appear per row, with a separate class legend and short captions.
The manuscript text explains score averaging, the display transform, and axes.
Table 3 now merges repeated dataset and partition labels.

Table 4 replaces the previous-code-version comparison with actual no-defense
FedAvg results. `build_baseline_comparison.ps1` validates the complete shared
seed-42 grid (32 matched cases), plus three completed CIFAR-10 seed-73 cases.
It checks matching configurations, exact warmup accuracy agreement, every
round and client response, and absence of traps, filters, or removals. The
primary table averages four attacks within each configuration. The additional
three cases have a separate appendix table. These comparisons do not pool a
single baseline seed with three BaitFL seeds. Paired records, trajectories,
summary statistics, and input hashes are in `generated/comparison/`.

Figure 5 adds no-defense accuracy curves with interquartile bands across
matched attack/partition settings. Figure 6 replaces overlapping process-resource
bars with accuracy and timing changes against that baseline.

The 3 November revision incorporates the completed paired MNIST segment-timing
experiment from `v15.4-completed-study`, pinned to commit
`8519fe180f337486e18dfc752cfedfcef64eaf53`. A byte-verified snapshot and its
import manifest are in `evidence/timing_mnist_20261103/`. The snapshot includes
both timing CSVs, completion/configuration records, and the instrumentation
sources. `import_mnist_timing.ps1` can reproduce it from the local Git object
database without switching branches. The paper-local `.gitattributes` preserves
its original bytes across checkouts.

`build_instrumented_mnist_timing.ps1` checks the snapshot hashes, completed
100-round runs, matching settings, frozen engine hash, instrumentation sources,
exclusive component sums, nested fitting timers, elapsed accounting, and phase
coverage. All 100 MNIST accuracies match the corresponding study execution.
The instrumented pair is not added as another detection replication or pooled
with the three-seed study means and matched no-defense cases.

Table V now reports both MNIST workflows by stage, including separate trap
construction, scheduling, features/preparation, decisions, and research I/O.
Tables VI/VII and Figures 7–9 distinguish computation from elapsed time and
show the measured phase/decision-block costs. The decision block includes
screening, audits, and state changes, including removal. It is not a timer for
the removal operation alone. Nested STD joint-training and mixture-finalization
times remain inside fitting and are not added twice.

Mean MNIST computation is 36.92 s for BaitFL and 52.26 s for STD-DAGMM.
Elapsed round means are 40.92 and 62.83 s. The 15.34 s computation gap and
21.91 s elapsed gap are reported separately. The 4 November revision below
adds the completed CIFAR-10 instrumented pair. No-defense comparisons remain
in Table IV and Figures 5/6, using their original matched executions.

Run `./rebuild_reporting.ps1` to validate and regenerate the study tables,
baseline comparisons, and figures in the required order. It calls
`build_multiseed_table.ps1`, `build_baseline_comparison.ps1`,
`build_norm_figure.ps1`, and `build_review_figures.ps1`. The figure builder
validates both instrumented datasets and regenerates the timing tables
and macros. Run `./build.ps1` afterward to compile. The manuscript date is
4 November 2026.

The 4 November revision widens the plotting areas in Figures 1 and 2 using
`scale only axis`. All 16 panels per dataset remain, with nearly square axes
spread across the text width. Tick labels no longer consume the requested
plotting width. No score coordinates, axis ranges or class labels change.

The CIFAR-10 pair is pinned to study commit
`182ba40c3d036d7dc1cbe07975d6c0a62b1cefd2`, with 27 byte-verified evidence
files under `evidence/timing_cifar10_20261103/`. Reproduce the import with
`./import_instrumented_timing.ps1 -Dataset cifar10`; the MNIST import retains
its original commit. Both imports read Git objects without switching branches.
`build_instrumented_timing.ps1 -Dataset cifar10` validates the complete pair,
source provenance, configurations, exclusive component sums, nested fitting,
elapsed accounting and phase coverage. All 100 BaitFL accuracies also match
the corresponding original CIFAR-10 study execution. The old MNIST-named
scripts remain compatibility entry points to the shared scripts.

Table V now places both datasets' stage means and sample standard deviations
side by side. Tables VI/VII include measured CIFAR-10 elapsed and decision-block
times. Figures 7–9 use both instrumented pairs for matching stage breakdowns,
computation/elapsed bars and full 100-round traces with both timing gaps.
CIFAR-10 averages 88.56/120.05 s of computation and 99.95/137.30 s of elapsed
round time for BaitFL/STD-DAGMM. STD fitting averages 42.09 s/round; BaitFL's
trap, scheduling, feature/preparation and decision timers sum to 0.791 s/round.
These are measured workflow differences, not a controlled detector-only speedup.
Neither simulator measures network communication. Detection-study averages and
matched no-defense comparisons are unchanged.

The diagram integration adds a free-rider illustration to the Introduction
and the BaitFL workflow overview to Proposed Methodology. The attack figure
shows four devices: three train on private data and one skips training and
returns a perturbed response. Local data/resource conditions are illustrative,
not telemetry available to the server. The workflow diagram has no internal
title, subtitle or round numbers. All figure references renumber automatically;
the score-geometry panels now follow these two new figures.

The editable, self-contained TikZ sources and vector PDFs live in `figures/`.
`build.ps1` runs `build_diagrams.ps1` before compiling the paper; diagram PDFs
are regenerated when a source is newer or the PDF is missing. Matching SVG/PNG
previews are also available under the repository's `analysis/baitfl_methodology/`
and `analysis/free_rider_attack/` directories.

The Section I refinement merges the Figure 1 reference into the preceding
paragraph and shortens its caption. Figure 1 has a thin outer border. Checked
processor icons show training resources on Devices 1–3; a crossed processor
replaces Device 4's battery. The device labels and caption use sentences
without semicolons. That refinement changed Section I only.

Section II was subsequently rewritten with varied sentence structure and
source-checked limitations. It distinguishes unusual or low-utility responses
from proof of non-training, auxiliary fitting from universal runtime claims,
peer auditing from server access to raw data, and canary training from property
inference. FRIDA's reported difference between its adaptive cosine and loss
tests is acknowledged. BaitFL's own aggregation and response-visibility costs
remain explicit. `CITATION_REVIEW.md` records sources and separates reported
findings from deployment considerations. The 29-page PDF compiles with resolved
citations and references and no overflowing boxes; Section II was visually
checked. Experimental data and policy were not changed.

Section III now uses shorter, varied sentences while preserving its participation,
server-knowledge and attacker assumptions. The attack definitions have space
before FR1 and separate lines for each bold title and its description. A block
at the normal body-text size keeps FR1–FR4 together in the left column on page 4.
FR4's difference and response equations are aligned to save space without
changing their definitions. Noise scales, cold start, histories and all equation
references are retained. The rebuilt PDF was visually checked.

Section IV was checked against the six source-hashed v15.4 files and their
called trap, aggregation, profile, robust-statistic and fingerprint helpers.
`METHODOLOGY_REVIEW.md` maps the text/equations to the code and records the
review. The section now has exactly four algorithms, one per phase, with
important line references and text explaining their roles in Figure 2. The
duplicate overall algorithm and Overall Procedure subsection are removed;
the opening paragraphs and feedback arrow explain the training loop instead.
Figure 2 labels Phases I–IV and has the same outer border as Figure 1.
Here/top/bottom algorithm placement distributes the procedures near their text.

The audit clarifies exact send-back, all-active peer references, the profile
median convention, statistical nomination versus certification, and the
separation of retained evidence from active review/quarantine. It also confirms
a cooldown-only audit-clock edge case in the frozen engine. No matching pattern
was found in the 96 completed study runs inspected. Algorithm IV preserves the
actual clock update, and Appendix C records the limitation. No experimental
source, detector policy or stored result was changed.

The Results revision of 4 November supersedes the older figure/table inventory
above. Main tables use the complete multi-seed detection grid. The provisional
no-defense comparison uses 63 completed matched pairs, including verified
published records in `evidence/completed_baselines/`, with equal attack weights
after seed averaging. Evaluation Metrics is black and covers all reported
measures and timer boundaries without metric formulas.

Results and Discussion now form one section. Metrics are organized by purpose,
and interpretation focuses on important outcomes, including the logged causes
of honest removals. Table I separates IID/non-IID, and Table II distinguishes
mean removals from quarantine. Figures 3/4 are preserved. The timeline,
class-mean score trends and accuracy plots are omitted from the manuscript.
Table IV provides baseline comparisons. Table V combines native timing stages
with explicit seconds saved per round and percentages. The original average-time
chart is redesigned as Figure 5 with adjacent teal/orange method bars. Table V
includes sample SDs calculated across the full 100-round timing horizon. A new
Figure 6 shows mean complete-removal rounds and observed ranges across the
multi-seed study. Appendix source is temporarily commented out, with no active
references to it. Table IV spells out percentage-point differences, and compact
float spacing avoids stretched gaps. Complexity includes sparse-audit costs, security
language is revised, and the closing sections include Limitations and Future
Work, Conclusion and an updated abstract.
`RESULTS_REVIEW.md` records selections, averaging, coverage and validation.

The supplied-review response supersedes the preceding figure/table inventory.
`REVIEW_RESPONSE.md` records fixes and remaining experiments. The paper now
states three seeds, cites 31 works, removes healthcare/thesis framing, adds
method requirements and notation tables, and explains protocol defaults.
Accuracy has across-run SDs, every attack appears in honest-impact reporting,
and the resource table owns the round-time column. Figure 5 now shows global
test accuracy over rounds 20–100, using all three BaitFL replications and
available completed baseline records. The caption identifies unequal coverage.
`build_accuracy_comparison.ps1` validates the trajectories and endpoints and
retains means, coverage and source hashes. `build/figure5_preview.tex` can be
compiled from this directory for a standalone vector preview. The former
representative-run norm diagnostics remain archived but are not rendered.
The accuracy plots precede the retained
timing and completion-round plots. Security and future work are merged into
Discussion and Limitations. Appendix source stays commented out.

To refresh the data and plots first, run `./rebuild_reporting.ps1`. It excludes
incomplete live runs and can incorporate newly completed baseline partners.
From this directory, compile with:

```powershell
./build.ps1
```

PDFLaTeX, BibTeX and latexmk must be available. The build script compiles into
`build/` and copies the final PDF, bibliography (`paper_v7.bbl`), and resolved
citation state (`paper_v7.aux`) beside `paper_v7.tex`. This also makes existing
citations available to direct editor builds. Use the script again after changing
bibliography entries or citation keys; a single LuaLaTeX run does not run BibTeX.
