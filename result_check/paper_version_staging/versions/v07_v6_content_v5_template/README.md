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
21.91 s elapsed gap are reported separately. CIFAR-10 retains its existing
logged round/phase comparison and STD stage measurements; absent operation
and wall-time measurements are not fabricated. No-defense comparisons remain
in Table IV and Figures 5/6, using their original matched executions.

Run `./rebuild_reporting.ps1` to validate and regenerate the study tables,
baseline comparisons, and figures in the required order. It calls
`build_multiseed_table.ps1`, `build_baseline_comparison.ps1`,
`build_norm_figure.ps1`, and `build_review_figures.ps1`. The figure builder
validates the instrumented MNIST evidence and regenerates the timing tables
and macros. Run `./build.ps1` afterward to compile. The manuscript date is
3 November 2026.

Build from any directory with:

```powershell
& 'D:\Code\Mitigating Free Rider\result_check\paper_version_staging\versions\v07_v6_content_v5_template\build.ps1'
```

PDFLaTeX, BibTeX and latexmk must be available. The build script compiles into
`build/` and copies the final PDF, bibliography (`paper_v7.bbl`), and resolved
citation state (`paper_v7.aux`) beside `paper_v7.tex`. This also makes existing
citations available to direct editor builds. Use the script again after changing
bibliography entries or citation keys; a single LuaLaTeX run does not run BibTeX.
