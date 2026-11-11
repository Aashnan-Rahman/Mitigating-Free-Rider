# BaitFL v7.2 — evidence and reviewer revision

Created 11 November 2026 from the exact v7.1 source used for the reviewed
all-in-one PDF. The v7.1 manuscript, export, PDFs and bibliography are preserved.
The verified build has 15 main-paper pages, seven supplementary pages,
31 main references and a 219-word abstract.

- Main deliverable: **`paper_v7_2_all_in_one.pdf`** and self-contained
  `paper_v7_2_all_in_one.tex`.
- Editable modular source/PDF: `paper_v7_2.tex`, `paper_v7_2.pdf`.
- Separate supplement: **`paper_v7_2_supplement.pdf`** and its source.
- Point-by-point response: `REVIEW_RESPONSE.md`.
- Template, length and fee check: `VENUE_AND_BUILD_NOTES.md`.
- Machine-readable verification: `VALIDATION.json`, `VERSION_PROVENANCE.json`,
  `export_manifest.json`, and `generated/revision/provenance.json`.

The main paper uses the local IEEEtran **journal** template rather than the
earlier conference option. The working and all-in-one versions have identical
pagination. The latter is also compiled in an isolated directory containing
only its TeX source. No project graphics, bibliography or data files are needed
to compile that export; the standard TeX packages are still required.

## Evidence included

The original 96-run 30%/40% study remains distinct from the prospective review
experiments. At the evidence cutoff, four honest-only and 26 low-prevalence
runs are complete. Four honest-only runs remove no honest client. The complete
non-IID 5/10/20% grid is displayed, including the FR2–FR4 misses at 5% and the
single honest removal in CIFAR-10 FR3 at 10%. Two completed IID MNIST 5% misses
are also disclosed. Pending experiments are not counted as evidence.

A new diagnostic replays all 72 original FR2–FR4 initial pairs and must
reproduce their stored certificate decisions exactly before stress testing.
It then gives the adversary oracle honest-median norm matching while holding
scale-free profiles fixed. This is **feature-level and single-cycle**, not a
new end-to-end attack run, a detector refit or a confirmed-removal result.
Its limitations and low FR3/FR4 certificate coverage are explicit.

The no-defense comparison is refreshed to **81 validated matched pairs**:
33 MNIST and all 48 CIFAR-10. Fifteen MNIST replications remain. Coverage and
time-to-target graphs now refer to this newer snapshot. The older 16.48-minute
MNIST value was correct for its previous snapshot; it is not forced onto the
newly averaged data.

The detailed 16-panel geometry grids, operation-level cost and payload tables,
qualitative requirements table, attack-level honest-cost table, and all four
expanded phase algorithms remain in the supplement. The main paper uses a
compact overall algorithm whose final-cycle aggregation follows state changes,
matching the engine. Every labeled equation is referenced.

## Experiments and reproducibility

The running experiment engine, frozen source files, registered plans, active
selector and queue order were not modified by this revision. Further seed work
remains last. At the cutoff, the low-share batch was waiting for its operational
2 GiB available-RAM guard after completing 26/48 cases. Startup/logon/five-minute
checkpoint recovery remains the existing mechanism. The queue resumes when
resources permit.

The recorded queue snapshot is a dated research inventory, not a live status
display. Use the repository's watch command for current progress. Running
`analyze_evidence.py` again can discover subsequently completed runs; the prose
and its evidence-cutoff statement must then be reviewed deliberately. It does
not run automatically during a paper build.

## Build

From this directory:

```powershell
./build.ps1
./export.ps1
New-Item -ItemType Directory -Force build/isolated | Out-Null
Copy-Item paper_v7_2_all_in_one.tex build/isolated/
Push-Location build/isolated
latexmk -pdf -interaction=nonstopmode -halt-on-error paper_v7_2_all_in_one.tex
Pop-Location
Copy-Item build/isolated/paper_v7_2_all_in_one.pdf paper_v7_2_all_in_one.pdf
./validate.ps1
```

`build.ps1 -SkipFigures` skips rebuilding unchanged vector diagrams.
Regeneration of analytical exports is separate: the repository environment can
run `analyze_evidence.py` and `format_evidence.py`; the baseline, time-to-target,
accuracy and timing PowerShell builders validate their input records before
writing exports. They do not train clients or alter detector parameters.

The single-file export has no review header, version banner, file-hash banner
or figure guide. Provenance hashes remain in separate metadata files. No
public DOI, new completed attack experiment or universal recall guarantee is
invented. The existing source/data repository remains the public code link.
