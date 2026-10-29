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
added for the background discussion. Diagnostic figures and detailed case tables
are retained from v6. Table 1 and associated study claims now use all completed
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

Table 1 uses three completed v15.4 replications for every configuration, with
recorded seeds 42, 43, and 73. Run `./build_multiseed_table.ps1` from this
directory to validate and regenerate it. This checks 96 completed executions,
matching settings/policy and six recorded source hashes, initial paired coverage,
removal identities/counts, and final accuracy and round-time consistency. The
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
are updated accordingly. Individual diagnostic plots and case tables remain
explicitly identified as representative executions.

Build from any directory with:

```powershell
& 'D:\Code\Mitigating Free Rider\result_check\paper_version_staging\versions\v07_v6_content_v5_template\build.ps1'
```

PDFLaTeX, BibTeX and latexmk must be available. The build script compiles into
`build/` and copies the final PDF, bibliography (`paper_v7.bbl`), and resolved
citation state (`paper_v7.aux`) beside `paper_v7.tex`. This also makes existing
citations available to direct editor builds. Use the script again after changing
bibliography entries or citation keys; a single LuaLaTeX run does not run BibTeX.
