# Manuscript corrections — 4 November 2026

Historical revision note: `REVIEW_RESPONSE_UPDATE_4.md` supersedes the
eligible-set pseudocode account below. Algorithm 4 now matches the implemented
raw-finding guard. The eligible-set alternative has not been used for new
training runs.

1. **Audit-clock account.** Move the implementation/trace discussion from the
   methodology and limitations to Appendix A. The methodology explains the
   eligible-set rule and points to the appendix. State that the guards agree on
   all 622 recorded audits, without claiming general equivalence. The check still
   finds 609 empty and 13 nonempty audits. No corrected-engine reruns are made.

2. **Notation and line references.** Keep `S` in calligraphic form for client
   records. Replace letter-coded cycle outcomes with `strong`, `unresolved` and
   `clear`. Use calligraphic `E` for paired decisions and `F_elig` for eligible
   sparse findings. Table II defines these roles. Section IV-E uses resolved
   references to Algorithm 4 lines 8 and 11 instead of the earlier line range.

3. **Computation versus participation cost.** The abstract explicitly says
   "lightweight in server computation" and notes that IID settings withhold
   about 11% of honest responses. The results and complexity text retain this
   distinction. New Figure 6 reports logged time to first crossing at illustrative
   targets of 98% MNIST and 70% CIFAR-10, selected for this analysis. All included
   executions reach these targets. Average matched seeds within attack and then
   the four attacks equally, using 16 MNIST and 47 CIFAR-10 pairs. The manuscript
   explicitly describes timer-boundary and execution-load differences. It does
   not claim a controlled speedup or an advantage at every accuracy target.

   `build_time_target.ps1` generates the figure and per-case/aggregate CSVs under
   `generated/comparison/`. The endpoint is a first crossing, not sustained
   attainment. Higher illustrative targets remain in the case export, including
   non-reached outcomes without imputing a crossing time. Round order, finite
   values, complete horizons, mean durations and final accuracy are checked
   against the saved matched summaries. The complete 63-pair exports remain the
   data basis. Of 126 underlying round logs, 121 are available and match their
   recorded hashes. Five CIFAR-10 seed-43 baseline logs are absent from this
   checkout and the published snapshot. Their exported trajectories are present.
   `time_target_provenance.json` records the exact missing paths and input hashes.
   Full raw baseline regeneration requires recovering those five logs to retain
   the current 63-pair coverage.

4. **Precision calculation.** The 12 MNIST non-IID 40% runs contain 480 true
   positives, three false positives and no false negatives. Pooled precision is
   `480/483 * 100 = 99.3788819876%`, which rounds to 99.38%. The previous 99.39%
   was the mean of seed-level rates: `(100 + 160/163*100 + 100)/3`, or 99.3865%.
   Table III now consistently pools removal counts across attacks and seeds.
   The text states the denominator and aggregation. The generator retains the
   seed-level means and standard deviations in separate CSV fields. Accuracy
   means, raw observations and overall pooled precision remain unchanged.

Validation: revalidate all 96 detection runs and the audit trace check, regenerate
the affected tables and target-time data, compile the 20-page PDF, and visually
inspect the abstract, notation, Algorithms 3–4, new figure and appendix. No
undefined citations/references, overfull boxes or oversized floats are reported.
No new training experiments or changes to the six frozen study source files.
