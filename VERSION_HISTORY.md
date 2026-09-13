# SWT-CP Version History

This file records methodology changes. Results from different versions must not
be pooled as if they used the same detector.

## v4 — Original statistical trap protocol

- Used server-side trap responses, update norms, median/MAD baselines, and
  cumulative penalties.
- The four attacks shared one server detector and clients were not told which
  models were traps.
- Representative MNIST IID, 40% results: FR1 removed 40/40 free riders and 6
  honest clients; FR2 removed 0/40 and 19 honest clients; FR3 removed 40/40 and
  9 honest clients; FR4 removed 0/40 and 3 honest clients.
- Main limitation: FR2 and FR4 were poorly separated, while isolated magnitude
  deviations could become false removals.

## v5 — Two-sided norm correction

- Corrected magnitude detection to use `abs(norm_z)`, so unusually small and
  unusually large nonzero updates are treated symmetrically.
- This was a transitional detector correction rather than the final staged
  protocol; no complete comparable four-attack result set is attributed to v5.

## v6 — Candidate state and repeated secret probes

- Added U/C/S states, candidate quarantine and confirmation, never-flagged
  anchors, a 15-point removal threshold, and a ten-probe rehabilitation gate.
- Added two distinct trap models to the initial double coverage sweep and a
  later single-check surveillance cycle.
- Kept exact send-back penalties active in every phase and retained the newest
  five recovery checkpoints while a run was incomplete.
- Representative MNIST IID, 40% results: FR1 40/40 with 12 honest removals; FR2
  40/40 with 8; FR3 40/40 with 8; FR4 40/40 with 15. Final accuracies were
  0.9879, 0.9886, 0.9881, and 0.9874 respectively.
- Main limitation: all honest removals were produced by persistent norm-only
  evidence. Repeated probing converted stable honest norm tails into permanent
  penalties, so rehabilitation often happened too late to help.

## v7 — Joint gradient evidence and reversible magnitude episodes

- Warm-up performs only the exact-zero/send-back check. Nonzero norm and layer
  profile scoring begins with secret trap probes.
- Adds a scale-free layer profile: each floating parameter tensor's update norm
  divided by the sum of all tensor update norms.
- A norm anomaly or a layer-profile anomaly alone places an unflagged client in
  C for fresh-trap confirmation, but adds no magnitude penalty. Only a response
  that fails both signals jointly earns the phase penalty.
- Two joint failures confirm S by default. An exact-zero response remains strong
  evidence, adds five permanent points, and moves the client directly to S.
- A fully normal confirmation clears C immediately. C or S clients with at
  least ten episode probes and a joint-failure rate at or below 10% are
  rehabilitated.
- Rehabilitation and clean candidate clearance erase only the current magnitude
  episode. Exact-zero evidence is permanent and is never forgiven.
- When a nonzero-evidence removal threshold and the low joint-rate rehabilitation
  rule become eligible together, rehabilitation is applied first; exact-sendback
  removal is never overridden.
- Checkpoints now preserve profiles, separate zero/magnitude penalties, and
  candidate probe counters. Logs expose both individual signals, joint evidence,
  and their matrices.
- v7 has not yet been experimentally validated. It is intended to reduce v6's
  honest norm-tail removals while retaining general, attack-independent evidence
  for FR2 and FR4; that expectation must be tested across attacks and seeds.
