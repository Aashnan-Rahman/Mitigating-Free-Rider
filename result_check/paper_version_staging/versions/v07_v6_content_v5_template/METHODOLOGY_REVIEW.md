# Section IV code review — 4 November 2026

Scope: manuscript, diagrams and reporting assets only. The experimental
implementation and stored results are unchanged. All six implementation hashes
in `generated/multiseed/provenance.json` match the working source after LF
normalization. Reviewed the helpers called by those modules as well.

| Paper element | Source checked | Result |
| --- | --- | --- |
| Main phase loop | `train_v15_4.py`, `run_experiment` | Warmup once, initial paired cycle, further paired cycles only for active review or probation, otherwise ordinary/sparse rounds. The training horizon terminates the loop. |
| Traps | `server/aggregation.py`, `make_trap_state`; engine cycle setup | Two independent Gaussian perturbations of one frozen cycle-start model. Population tensor SD, scale 0.01, floor 0.0001, floating buffers included, integer counters unchanged. The old antithetic `make_pair` helper is not used here. |
| Norm/profile summaries | `clients/attacks.py`, `flatten_delta`; `train.py`, `build_layer_profile` | Norm covers concatenated floating deltas. Profile entries are per-floating-tensor norms divided by their sum; zero vector below the configured 1e-6 denominator guard. |
| Same-trap reference | `server/v15_protocol.py`, `measurements` | Leave one client out. Include all other available active clients, including quarantined and unresolved clients. No passing-only or ground-truth filter. |
| Robust normalization | `server/preliminary_signals.py`, `robust` | Median/MAD with MAD divided by the standard-normal 0.75 quantile. Zero scale is undefined. Profile reference uses PyTorch's coordinatewise lower median for even peer counts. |
| Exact send-back | Engine response loop; `server/model_fingerprint.py` | Exactly zero floating delta norm OR returned fingerprint equal to the immediately preceding sent model. Fingerprints include every tensor, dtype, shape and name. A near-zero epsilon is not the send-back criterion. |
| Screening | `server/diagonal_decision.py`; `server/v15_protocol.py`, `screen` | Three diagonal-score views, sqrt-population histogram bins, joint client resampling, 1,000 replicates and 99% intervals. Lower average-view cohort must contain a majority of all active clients. Undefined/unstable split falls back to defined negative norm-z on both traps. Intervals do not bound false-removal probability. |
| Certificates | `server/v15_evidence.py`, `certificate`; `server/v15_strict_norm.py` | Supported screened minority. Raw norm requires core and full-peer gaps above cohort IQR. Raw profile requires the core gap and the full-peer-gap or spacing alternative. Per-client median direction and matching A/B component are required. Diagonal certification is diagnostic only. |
| Statistical memory | `server/v15_certificate_memory.py`, `CycleState.apply` | Fresh component-specific counts can confirm across nonconsecutive distinct cycles. Two consecutive complete R cycles clear counts. A fresh current matching certificate is required for removal. C never fabricates or renews evidence. |
| Exact confirmation | Inherited `server/v15_evidence.py`, `CycleState.apply` | Consecutive full paired send-back certificates. Statistical counts and exact streaks are separate. |
| Review vs category | `server/v15_evidence.py`, `monitored`/`quarantined`/`apply` | Active review budget, not every C/S diagnostic category, determines dense probing. Fresh strong evidence renews review/quarantine. Unconfirmed exclusion expires. Weak candidates and retained counts alone cannot force dense probing or renew quarantine. |
| Recovery | Same state class; base probation property | Two consecutive complete clear outcomes rehabilitate; another clear cycle completes probation. Unconfirmed release uses a cooldown of two audit opportunities. |
| Group scheduling | `server/v15_protocol.py`, `build_schedule` | Up to ten homogeneous groups, proportionally allocated with nearest rounding/ties down and pool-size bounds. Monitored clients get alternating traps throughout a cycle; other clients get one response per trap. One response slot per client/trap is sampled before observing scores. |
| Sparse audit | `server/v15_strict_norm.py`, `audit_anomalies`; inherited `escalate_audit` | All active clients receive one fresh trap. Strict single-trap norm/profile evidence or exact send-back opens eligible review without quarantine. No statistical-memory increment/clearance or removal. Cooldown is checked before decrement. Enrollment resets exact streaks but preserves statistical memory. |
| Aggregation | Engine response/decision loop; `fedavg_delta` | Ordinary recipients not quarantined at round start are eligible; remove new quarantines/removals before final aggregation. Equal-weight floating deltas, server integer counters unchanged, empty set leaves model unchanged. |

## Confirmed audit-clock edge case

In the sparse-audit branch, the engine sets `quiet_since` to `None` whenever
the *unfiltered* anomaly set is nonempty. `escalate_audit` may reject every
member because they were already in cooldown. Then no review opens, probation
is absent, and the quiet clock is unset. Subsequent rounds never meet either
the paired-cycle or sparse-audit condition, so ordinary training continues
without another audit.

A small check extracted and executed the original `escalate_audit` method and
the original audit-clock expression using only Python standard-library AST and
a one-client record. With review 0, cooldown 2 and that client flagged, the
result was review 0, cooldown 1, quiet clock `None`. No ML code was imported.

Inspected all 96 completed runs listed in `generated/multiseed/per_run.csv`.
None has a last audit with nonempty findings followed exclusively by ordinary
rounds before the horizon. This does not establish the edge case is impossible.
Algorithm IV reproduces the frozen clock assignment and the manuscript records
the limitation in the reproducibility appendix. A timer correction belongs in
a new experimental revision, not a silent change to this study's source.

## Editorial and layout decisions

- Exactly four algorithms, one per phase. The overall procedure is explained
  at the start of Section IV and through the diagram's feedback path, removing
  the duplicate fifth algorithm and the Overall Procedure subsection.
- Figure 2 uses explicit Phase I–IV labels and the same thin outer border as
  Figure 1. Text maps each phase to its diagram region and algorithm.
- Important algorithm statements have LaTeX line labels for response selection,
  certification, end-of-cycle filtering, fresh counts, removal, release,
  audit enrollment and the audit-clock update.
- Algorithms permit here/top/bottom placement rather than collecting at the
  end of the section. Placement is checked in the compiled PDF.

Validation: rebuilt the 30-page PDF and visually checked Figure 2 and the
algorithm/text layouts on pages 5–7. Exactly four phase algorithms remain.
Equation, algorithm and line references resolve, with no overflowing boxes or
oversized floats in the final log. The standalone diagram source matches its
paper-local copy, and PDF/PNG/SVG exports were refreshed. Experimental sources
remain unchanged.
