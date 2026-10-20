# Timing breakdown

| Dataset | Method/horizon | Mean s/round | Sum min |
|---|---|---:|---:|
| mnist | ours_100 | 34.41 | 57.35 |
| mnist | std_100 | 50.19 | 83.64 |
| cifar10 | ours_100 | 84.85 | 141.41 |
| cifar10 | std_100 | 127.24 | 212.06 |

See timing_report.pdf for enlarged vector charts and tables. Component CSVs,
100 actual round records, phase summaries and input hashes are saved alongside
this report and in the paper's generated/timing folder. Our gray totals cannot
be split retrospectively.
The phase figure separates within-category round cost (left) from its weighted
contribution to the full-run average (right); counts explain the difference.
These are whole-round categories, not isolated detector/trap costs.
STD's 100-round figures now use 100 actual measured rounds, not projections.
No network transfer was timed. No new experiment or detector change was made.
This is a native-workflow comparison, not a matched detector-only speedup test.
Removing non-training free riders need not reduce honest SGD jobs; a smaller
active population does not imply proportionally smaller client-training time.
