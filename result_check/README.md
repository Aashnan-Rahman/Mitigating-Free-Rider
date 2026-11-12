# Papers and research records

## Current paper: BaitFL v7.3

This is the latest revision of the **v7 paper**. Start here:

| Task | File |
| --- | --- |
| Read the current paper | [v7.3 all-in-one PDF](paper_version_staging/versions/v07_3_saudi_review/paper_v7_3_all_in_one.pdf) |
| Edit the paper | [Modular LaTeX source](paper_version_staging/versions/v07_3_saudi_review/paper_v7_3.tex) |
| Use a single-file LaTeX export | [All-in-one source](paper_version_staging/versions/v07_3_saudi_review/paper_v7_3_all_in_one.tex) |
| Read the supplement | [Supplement PDF](paper_version_staging/versions/v07_3_saudi_review/paper_v7_3_supplement.pdf) |
| Check reviewer fixes | [Review response](paper_version_staging/versions/v07_3_saudi_review/REVIEW_RESPONSE.md) |
| Build or validate | [Current version's instructions](paper_version_staging/versions/v07_3_saudi_review/README.md#build) |

Edit the modular source, then regenerate the all-in-one export. The export is
generated, so editing both independently can produce conflicting versions.

## Folder map

| Location | Contents |
| --- | --- |
| [paper_version_staging](paper_version_staging/README.md) | Manuscripts, figures, bibliography, paper builders and supporting evidence. The index identifies the current version. |
| [results_v8_organized](results_v8_organized/README.md) | Historical v8 evidence used by earlier paper analyses. These are not current experiment outputs. |
| [archive](archive/README.md) | Early V1/V2 analyses, old non-IID comparisons and superseded thesis drafts. |
| [Recovery record](RECOVERY_20261106.md) | The November code/data recovery and synchronization record. |
| [Cleanup record](cleanup_2026_10_15.json) | Historical run-discard decisions referenced by repository documentation. |

The training implementation lives outside this folder. This folder **does contain
code for building papers and analyzing evidence**, so its established paper and
evidence paths are preserved. Live experiments, checkpoints and monitoring remain
under the repository's `results/` directory and experiment tools.

Older papers and research results are retained for traceability. They are not
alternative copies of the current manuscript. See the [version index](paper_version_staging/versions/README.md)
when you need a previous revision.
