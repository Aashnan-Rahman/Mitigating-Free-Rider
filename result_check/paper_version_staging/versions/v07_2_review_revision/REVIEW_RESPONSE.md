# Response to the v7.1 review — v7.2

Evidence cutoff: 11 November 2026. This response distinguishes editorial fixes,
newly analysed evidence and experiments that remain pending. The original
v7.1 source used for its reviewed all-in-one export was verified by hash.

| Feedback | v7.2 action and scope |
|---|---|
| Build with the local template | Built with local TeX Live's IEEEtran v1.8b in journal mode. Modular, isolated all-in-one and supplement builds are checked for missing references, overflows and figure/font problems. The exact class path/hash is recorded in `VALIDATION.json`. |
| Representative plots contradict the overlap claim | The main text now states that the seed-42 round-20 panels show norm separation. They are moved intact to Supplementary Figures S1–S2. New main Figure 5 shows the recorded MNIST non-IID FR3 40% seed-43 error case at rounds 20/30, with the two removed honest clients marked. Its transformed paired-mean norm ranges overlap at round 30; this is not claimed to prove overlap on every individual trap or in the original seed-42 panels. |
| Attacks favor low-norm detection | The text acknowledges this favorable structure and avoids claiming that averaging must make every fake update smaller than every honest update. A 72-case oracle norm-matching feature diagnostic is added. Stored decisions must first replay exactly; labels construct the stress input but never reach the detector. |
| What does the profile score add? | New Table IV separates norm, profile and either-channel paired certificates. Under oracle norm matching the norm channel certifies no attackers; profile coverage is 61.9% for FR2, 10.7% for FR3 and 17.9% for FR4, with ten honest certificates. This shows some magnitude-independent evidence and a substantial remaining gap, not general robustness. |
| Need an actual norm-matched attack | **Partially addressed.** The diagnostic does not materialize complete model responses, rerun local training, test their future trajectories or establish permanent removal. An end-to-end magnitude-calibrated/adaptive attack remains necessary. It is not relabeled as an executed published attack. |
| Removal arrow appears only from quarantine | Figure 4's caption explicitly states that fresh matching confirmation is tested for all non-removed clients, including after release. The red arrow is illustrative rather than the only legal predecessor. The required evidence counts and clearance rules still apply; a participation-state label does not override them. |
| Only about four triangles visible for 40 free riders | Figure 3's caption explicitly states that 40 points are present and coincident score pairs hide individual triangle locations. |
| Inconsistent class/method colours | Honest clients are blue and free riders orange in the overview and all score plots. BaitFL workflow comparisons are teal; no-defense/STD-DAGMM comparators are gray. Purple ordinary-model arrows and red removal transitions have separate explicit meanings. |
| Remove review header | The all-in-one source begins directly with its document class. No code/paper banner, checksum header, resolved-reference map or figure guide is embedded. Hashes and provenance are separate artifacts. |
| Stray black declarations and groups | The main source's review colour declarations and abstract/evaluation groups are removed. Necessary local groups around embedded vector styles remain implementation scoping, not review formatting. |
| Odd noindent braces | The contribution lead-in and repository link are cleaned up. |
| Unused Table II symbols and P_ref clash | The compact notation table drops design-only unused symbols. Bootstrap count B remains; confidence and confirmation/review/cooldown/probation choices are described in the method. P denotes floating coordinates, not reference probation. |
| Redundant g > 0 | Removed; g > I_U is retained with nonnegative IQR. |
| Nine equation labels never referenced | Every labeled method equation is cited where used; the support and certificate equations also appear in the overall algorithm. The complexity bound is labeled and referenced. |
| Thousands formatting | The rendered honest-case total is 6,240. Numeric CSV/JSON data remain numerical records. |
| VeriML key | Renamed consistently to `zhao2021veriml`; the previously verified published metadata are retained. |
| Length | Large geometry grids, detailed complexity/payload tables and four expanded algorithms are online-supplement material. Related work is condensed. The main paper retains the mathematical rules, a complete overall algorithm, new limitation evidence and the original main results. Length is reduced; it is not represented as an eight-page manuscript. |
| Page-charge rules | Current official IoTJ guidance is checked separately in `VENUE_AND_BUILD_NOTES.md`. No submission, payment or venue commitment is made. |
| Missing matched baselines | Refreshed to all currently completed, validated partners: 81/96, comprising 33/48 MNIST and 48/48 CIFAR-10. Fifteen MNIST replications remain, rather than the 32 missing in the reviewed snapshot. Further replications stay late in the user-selected queue. |
| 16.48-minute correction | Accepted. That value was correct for the old snapshot. The refreshed non-IID 40% means are 15.55/21.22 minutes for MNIST and 48.02/58.32 for CIFAR-10, using the newly available matched coverage. No measurement is edited to preserve an old mean. |
| Honest-only and low prevalence missing | Four honest-only runs and 26 completed low-share runs are now included separately from the 96-run main study. The complete 24-case non-IID grid is shown, including misses at 5% and the one new honest removal. |
| Passive ablation, oracle, published attacks | **Pending.** Plans and code exist, but these batches have not executed. The low-prevalence batch is currently waiting for available RAM. The paper does not claim queued experiments as results. |
| Working detection baseline | **Still incomplete.** Stored STD-DAGMM flags are reported only as diagnostics of the declared five-epoch recipe, which missed the tested FR3 responses. The passive-run MAD diagnostic remains queued. No fair general detection ranking is asserted. |
| Immutable archive | Still an external publication step. Local checksum bundles and repository evidence do not constitute a public DOI deposit. |

The revised main algorithm preserves the engine's aggregation ordering:
start-round eligibility is formed first, fresh cycle decisions exclude new
quarantines/removals, and only then are eligible ordinary responses aggregated.
Released clients are not retroactively added to that round's aggregation set.
The quiet clock is updated when paired review ends. Sparse challenge responses
remain excluded. The expanded supplement retains the published raw-clock
procedure for traceability and documents its agreement with the corrected
guard on all 622 recorded primary-study audits.

The new norm-matching endpoint is a **paired statistical certificate at round
20**, not final recall. The original 96-run permanent-removal results and the
new lower-prevalence results remain separately scoped throughout the abstract,
introduction, results and conclusion. Detector settings and the running
registered source files are unchanged.
The component breakdowns retain the joint nomination rule; they are not
standalone norm-only/profile-only classifier baselines or a profile-off ablation.
