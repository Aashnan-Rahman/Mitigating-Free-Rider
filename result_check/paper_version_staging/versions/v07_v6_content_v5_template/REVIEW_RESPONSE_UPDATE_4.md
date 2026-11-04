# Vocabulary and implementation alignment — 4 November 2026

- Figure 2 now uses Clear, Unresolved and Strong, matching the cycle-outcome
  vocabulary in the text. Remove the old R/C/S suffixes and replace candidate or
  suspected wording in the rehabilitation paragraph, screening text, evaluation
  metrics and honest-client discussion. Table IV uses the same vocabulary. The
  internal experimental CSV field names remain unchanged.
- Figure 6's caption explicitly states that BaitFL is the left bar and no
  defense is the right bar in each pair. The generator retains this caption.
- Section VII-E now requests controlled time-to-accuracy comparisons extending
  Figure 6, with an honest-only oracle baseline without auditing. It no longer
  describes all target-accuracy timing as wholly unmeasured.
- Algorithm 4 line 14 now uses the raw finding set, exactly as the evaluated
  `train_v15_4.py` implementation. Enrollment still uses eligible findings after
  cooldown filtering. Section IV-E and Appendix A explain that distinction.
  The appendix documents the all-findings-blocked edge case, absent from the
  622 recorded audits, without presenting the eligible-set alternative as
  evaluated code. The earlier correction patch remains unapplied. A corrected
  training subset was not run: the available Python command resolves to a
  Windows Store alias that fails to launch, and no project virtual environment
  or standard per-user Python installation was found in this session.
- Figure 6 describes combined removal and audit effects. Removing fabricated
  responses can reduce update dilution, so the comparison does not isolate
  auditing overhead. Retain the controlled-advantage caution and keep target
  timing out of the abstract. The numerical example is 16.5 versus 23.3 minutes
  for MNIST 40% non-IID. The 24.2-minute baseline is MNIST 30% non-IID.

Validation: the saved 622-audit check passes and verifies the six frozen source
hashes. All five checked measurement exports retain their SHA-256 hashes.
Rebuild the native methodology diagram and time-target caption, compile the
19-page paper, and inspect Figures 2/6, Algorithm 4, Table IV and the appendix.
No undefined citations/references, overfull boxes or oversized floats are
reported. No new training experiments or changes to the study implementation.
