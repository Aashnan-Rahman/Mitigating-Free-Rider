# BaitFL paper v7.1 — figure redesign

Created 10 November 2026 from the full v7 paper. Updated 11 November 2026.

- Manuscript: `paper_v7_1.pdf` and `paper_v7_1.tex`.
- Current length: 19 pages including references.
- Rebuild from this directory: `./build.ps1` with TeX Live available.
- Validate: `./validate.ps1`.
- Base: `../v07_v6_content_v5_template/paper_v7.tex`.

The current figure designs are:

1. **Single-column illustrated overview.** `figures/free_rider_attack.tex`
   restores a server rack, model graph, private-data cylinders and laptops.
   Two honest devices train locally while the free rider fabricates a response.
   No claim is made that the free rider lacks data or computation. This is a basic
   FL/free-rider illustration: every device receives the same global model and
   returns a trained or fabricated local model. Purple outgoing arrows and green
   or orange returns are explained in a compact left-hand legend, with a local-
   data cylinder key on the right. No trap is drawn here. The laptops show model icons,
   and the tiny overlapping arrows inside the device cards are removed.
2. **Horizontal schedule at single-column width.** `figures/audit_schedule.tex`
   uses short phase labels above a shared horizontal round axis. Warmup and
   paired cycles occupy ten rounds each, followed by ordinary training with
   audit markers. The earliest-removal callout and continuation rules sit below
   the axis. The drawing is designed at its printed width rather than reduced
   from the earlier wide timeline. The vertical layout is superseded.
3. **Two separately captioned subfigures.** `figures/challenge_path.tex`
   supplies panel (a), while `figures/challenge_scores.tex` supplies panel
   (b). The manuscript uses IEEE-compatible subfig captions and labels 3a/3b.
   The representative scores are unchanged: CIFAR-10, non-IID, FR3, 40% free
   riders, round 20. Seed 42 is retained in the surrounding reproducibility
   prose and this record, not in figure titles or captions. The former combined
   `challenge_mechanism.tex/pdf` remains a superseded design and is not built
   or included in the manuscript.
4. **Single-column participation diagram.** `figures/client_states.tex`
   contains five unique states. Eligibility, quarantine and removal form the
   central path, with probation and cooldown at either side. Dashed paths
   return to the single eligible state. The one-clear-cycle and two-clear-cycle
   labels are separated along their corresponding paths. Arrow meanings appear
   in an image legend. Confirmation and rehabilitation rules are discussed in
   the body text rather than listed in the caption. Review remains distinct
   from quarantine.

All five active panels use native TikZ/PGFPlots, Times labels and LaTeX
mathematics. There are no raster assets. Grayscale and print-size previews
are kept under `build/`. The manuscript's other result figures are retained.

All 339 reporting exports, the bibliography, algorithms, measurements and study
code remain unchanged. The response scatter reads the same recorded coordinates.
The diagram is not a passive-detector ablation. Evaluation limitations and the
audit-clock disclosure remain in the full paper.

Reporting exports and the bibliography are copied here so the manuscript builds
independently. Original study evidence and regeneration scripts remain in the
base version. `figures/accuracy_comparison_layout.tex` differs from its original
export only by relaxing `[!t]` to `[t]` to prevent float overflow after reflow.
Validation checks this exact difference.

`BASE_VERSION.json` records hashes of the base full and short papers and
their overview/methodology diagrams. The build and validation check those eight
files. On 11 November 2026, the user requested model icons in Figure 1 in both
versions. The base Figure 1 and full PDF are rebuilt for that change, and the
corresponding baseline hashes are refreshed. The preceding files and manifest
are preserved under `build/before_model_icon_20261111/`. The base short paper,
methodology diagram and manuscript text are unchanged.

Previous v7.1 designs are backed up under `build/readability_before/` and
`build/design_before_20261111/`. The latest detail-refinement backup is
`build/detail_refinement_20261111/`. No new experiment or external publication
is performed. The vertical Figure 2 and preceding PDF are additionally backed
up under `build/horizontal_schedule_20261111/`.

## Single-file review export

`paper_v7_1_all_in_one.tex` contains the current full manuscript, equations,
four algorithms, all tables, the 31 formatted references, all active vector
figure code and the data from 80 plot files. It has no external project-file
dependencies. Standard LaTeX packages are still needed to compile it.

The header includes the plain-language guide from `figure_review_guide.md`,
resolved label and citation numbers, and source hashes. Figure descriptions
are comments for review, not added manuscript claims. Source-boundary comments
identify the embedded blocks. Numeric macros are expanded to their values.
Unused macros and obsolete commented-out draft material are omitted.

Regenerate with `./export_review.ps1`. The script writes provenance and data-row
counts to `review_export_manifest.json` without modifying the working paper.
The export was compiled independently under `build/review_standalone/` to
19 pages, with no unresolved references, unresolved citations or overfull boxes.
