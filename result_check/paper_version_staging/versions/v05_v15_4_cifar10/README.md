# Paper v5: v15.4 CIFAR-10

Author/method source: `paper_body.tex`. Previous paper versions are untouched.

- `paper_v5_template.pdf`: permanent blank result-table and figure template.
- `paper_v5.pdf`: draft populated automatically only after both eight-run
  CIFAR-10 seed-42 batches (30% and 40%) complete and validate.
- `generated/paper_status.json`: template/waiting/ready/blocked status.
- `generated/per_run_statistics.csv`: generated from the complete grid only.
- `generated/provenance.json` and `evidence/source/`: input hashes and frozen
  implementation snapshots, not claims of independent validation.

Initial blank PDFs (from the repository root, before automatic population):

```powershell
.\.venv\Scripts\python.exe build_paper_v5_v15_4.py --template-only --compile
```

Completion check, table/figure population and compilation:

```powershell
.\.venv\Scripts\python.exe build_paper_v5_v15_4.py --update-if-ready --compile
```

The experiment recovery launcher calls this check when its selected batch is
complete. Its existing recovery schedule retries failed paper builds without
rerunning completed experiments. No task/account/credential change is required.
Before-login operation depends on that task's actual Windows login mode.

The builder never modifies experiment results. It does not fill partial data
with zeros, omit completed detection failures, substitute older-method MNIST
data, or count candidate flags as removals. Only generated files are replaced;
author source and previous paper versions are preserved. Local PDF generation
does not publish or submit the paper externally.
