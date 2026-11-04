# Additional experiments and priorities

Based on `Ideas.txt` and the current v7 evidence, 4 November 2026.

Run each new experiment family with **one fixed seed first**. Establish coverage,
correctness and useful comparisons before spending compute on additional seeds.
Keep the original v15.4 results intact. Any corrected implementation must have
its own source hash, output directory and explicit protocol description.

## Priority order

| Order | Experiment | Question it answers | Initial scope |
|---|---|---|---|
| 0 | Corrected audit-clock validation | Does the eligible-set guard handle the blocked-findings case and preserve expected operation? | A deterministic edge-case test, then a small single-seed MNIST subset |
| 1 | Honest-only federations, 0% free riders | Does BaitFL falsely remove or exclude honest clients when no attack exists? | MNIST and CIFAR-10, IID and non-IID, with an all-honest no-defense control |
| 2 | Low free-rider proportions, 5%, 10%, 20% | Does detection work below the tested 30–40% range, especially near the cohort-support boundary? | Start with MNIST non-IID FR3/FR4, then cover both datasets, both partitions and FR1–FR4 |
| 3 | Passive-screening ablation | What do the traps add beyond ordinary-update statistics? | Full BaitFL versus the same detector using ordinary models instead of challenges |
| 4 | Detection-baseline validation and comparison | Is the comparison detector functioning, and how does BaitFL compare with a simple alternative? | STD-DAGMM reference-setting check, then matched STD-DAGMM and MAD-on-norm pilots |
| 5 | Honest-only oracle and controlled utility/timing comparison | How much of the observed benefit comes from removing free riders, and what does auditing cost? | BaitFL, attacked no-defense and an oracle on the same single-seed configurations |
| 6 | Published free-rider strategies | Does detection extend beyond the four current fabrication strategies? | Fraboni's decaying-noise and Zhu's scaled-delta attacks, starting on MNIST |
| 7 | Held-out dataset with frozen detector settings | Do the development choices transfer to an unseen dataset? | One Fashion-MNIST pilot grid, or a MedMNIST subset as an alternative |
| 8 — later | Targeted multi-seed expansion and baseline completion | Are the main findings stable across replications? | Prioritize non-IID FR3/FR4, then the most consequential new settings and missing matched baselines |
| 9 — optional extension | Adaptive attackers | What changes when attackers infer or react to audits? | A separate extension beyond the current non-adaptive threat model |

Order 0 is a correctness prerequisite. **Honest-only and low-proportion runs are
the first substantive experiments.** Orders 1–5 address the most immediate
evidence gaps. Orders 6–7 broaden the evaluation. Do not postpone orders 1–7 to
repeat the existing grid across more seeds. Adaptive attacks are an optional
scope expansion, rather than a prerequisite for every current-scope result.

## What to run and record

### 0. Validate the corrected guard before expanding the study

- Construct an audit with a nonempty raw finding set whose clients are all in
  cooldown. Verify that no review opens, the clock restarts, and a later sparse
  audit is scheduled. Also check empty findings and a mixture of eligible and
  blocked findings.
- Run a small matched subset with the corrected implementation and frozen
  settings. Start with MNIST non-IID FR3 and FR4 at 40%, using one seed and the
  full training horizon. Compare the clock, audit schedule, removals, quarantine
  and accuracy against the corresponding original runs.
- These runs validate the selected cases. They do not retroactively turn the
  existing 96-run study into a corrected-code evaluation. A claim about the whole
  corrected study would require the corresponding reruns.

### 1. Honest-only controls

- Use the same 100-client partitions, model initialization and local training
  settings for BaitFL and no defense. Start with MNIST non-IID, then its IID
  control and the two CIFAR-10 partitions.
- Report honest removals, clients ever quarantined, quarantine duration,
  unresolved clients at completion, and withheld responses separated into traps
  and other exclusions. Include accuracy and time to fixed accuracy targets.
- This comparison measures the cost of the defense when there are no free
  riders. Do not assume zero removals means zero participation cost.

### 2. Low-proportion attacks

- Add 5%, 10% and 20% free riders under IID and non-IID partitions. Begin with
  MNIST non-IID FR3/FR4 as a diagnostic pilot, then complete the single-seed
  coverage across both datasets and all four attacks.
- Record detection completion or non-completion, recall, honest removals and
  participation cost. Log the nominated-cohort size and why a certificate fails.
- At the initial population of 100 clients, statistical certification requires
  at least ten nominated clients. Five attackers may therefore be below that
  support boundary. Exact send-back follows a separate path. This is a boundary
  to test and report, not a reason to relax the gate after viewing the results.

### 3. Passive screening

- Replace challenge models with ordinary global models while keeping the
  norm/profile features, screening, confirmation settings and observation
  schedule comparable. Define explicitly how ordinary responses enter
  aggregation in this variant.
- Use the same initial model, partitions, attackers and local training budget.
  Start with non-IID FR3/FR4, with IID cases as controls.
- Compare detection, honest exclusions, final accuracy, detection delay and
  checking time. Keep the full BaitFL result as the reference. A failure of the
  passive variant is informative only if its implementation is sound.

### 4. A functioning detection baseline

- First reproduce STD-DAGMM's reference setting identified in `Ideas.txt`, IID
  MNIST with the random-weights attack. Check features, score direction, thresholding
  and training configuration against the original method before attributing
  its zero recall to an inherent weakness.
- Resolve implementation issues and choose settings on development cases.
  Freeze and disclose the configuration and fitting budget before comparison.
  Do not tune against the final evaluation labels merely to obtain good recall.
- Add the simpler MAD-on-update-norm baseline. Compare all methods on the same
  single-seed conditions, including honest-only and low-proportion cases.
- Use compatible endpoints. Report round-level flags separately from permanent
  removal. If a common confirmation/removal policy is added, describe it and
  report those results separately from the original baseline's flags.

### 5. Oracle, matched no defense and controlled timing

- Reuse existing matched no-defense runs for the selected seed where possible.
  Run missing single-seed controls before adding replications.
- The oracle uses the original client partition and honest-client data, excludes
  all free-rider responses from aggregation from the beginning, and performs no
  audits. Do not redistribute the attackers' data to the honest clients. Only
  the oracle may use ground-truth attacker identities for this purpose.
- Compare attacked no defense, BaitFL and the oracle under matched settings.
  Also retain the all-honest BaitFL/no-defense pair from order 1.
- Use common timer boundaries, hardware and thread settings. Record computation
  and elapsed time separately, with the same logging/checkpoint accounting.
  Freeze accuracy targets before the attacked-method comparison and retain
  explicit non-reached outcomes rather than assigning them a successful time.
- The oracle shows the gap to perfect filtering, which includes detection delay
  and withheld contributions. It does not by itself isolate checking overhead.
  The all-honest comparison and stage timers provide complementary evidence.
- Five raw baseline timing logs referenced by the current paired exports are
  missing from this checkout. Recover them before rerunning those configurations
  unnecessarily or claiming complete raw-data reproduction.

### 6. Published attacks

- Implement the decaying-noise and scaled-delta strategies from their original
  formulations. Check the formulas, initialization and available attacker
  information rather than treating FR2 or FR4 as exact substitutes.
- Start on MNIST with one seed, then extend to CIFAR-10 and both partitions.
  Include the original 30–40% settings and a low-proportion case once the pilot
  implementation is verified. Report failures and incomplete detection as well
  as successful cases.

### 7. Held-out validation

- Freeze detector parameters before the unseen-dataset evaluation. Fashion-MNIST
  is the first suggested pilot. A MedMNIST subset is an alternative extension,
  not an additional requirement for the initial pass.
- Include honest-only, a low free-rider proportion and a harder history-based
  attack setting. Use one seed initially. Separate required task/model changes
  from detector tuning, and disclose any tuning that becomes necessary.

### 8. Replication — deliberately later

- After the earlier pilots are validated, expand the original non-IID FR3/FR4
  configurations at 30% and 40% toward at least five total seeds. Reuse existing
  runs only when the implementation and protocol match the evaluated variant.
- Replicate the new settings that carry the main claims, particularly
  honest-only safety, low-proportion detection, passive screening and the oracle
  comparison. Include unfavorable pilot findings rather than selecting only
  successful conditions for replication.
- Complete the missing matched no-defense seeds alongside the corresponding
  BaitFL replications. This is the place to finish the multi-seed baseline grid,
  rather than delaying the new experiment families to do it first.
- Report per-run outcomes and accuracy variation. Estimate uncertainty at the
  run/seed level as the design permits. Do not treat thousands of clients from
  shared federations as independent trials to obtain artificially narrow bounds.

## Reporting work that does not require new training

- Retain per-run outcomes, honest exclusions and failed-detection cases now.
- Keep pooled detection percentages descriptive and distinguish them from
  averages of run-level percentages.
- Preserve the current time-to-target caution. It measures the combined
  workflow and is not an isolated estimate of auditing cost.
- Recover missing evidence, document source hashes and prepare an immutable
  archive separately from the experiment queue. Publishing an archive is not an
  experiment and is not performed by this plan.
- The writing, notation, caption and precision-arithmetic corrections repeated
  in `Ideas.txt` are already addressed in the current manuscript. They are not
  additional experiments.

This document is a plan only. No training runs are launched.
