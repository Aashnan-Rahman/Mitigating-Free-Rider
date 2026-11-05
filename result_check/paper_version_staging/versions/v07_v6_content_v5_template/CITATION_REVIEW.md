# Citation and literature-review revision — 30 October 2026

## Citation hygiene follow-up — 5 November 2026

- **Lin et al. [6].** Recheck the [original paper](https://arxiv.org/html/1911.12560v1),
  especially Sections 3, 4 and 5. Replace the earlier participation claim with
  the tested distinction: random weights can evade the autoencoder, whereas
  received-model differences can evade DAGMM. Section III-B now cites the same
  paper for persistent free riding without collusion. Do not attribute our other
  protocol assumptions or retained-history design to that paper.
- **VeriML [22].** Replace the preprint entry with the published TPDS article,
  volume 32, issue 10, pages 2524–2540, October 2021, DOI
  [10.1109/TPDS.2021.3068195](https://doi.org/10.1109/TPDS.2021.3068195).
  The six journal authors are Lingchen Zhao, Qian Wang, Cong Wang, Qi Li,
  Chao Shen and Bo Feng, confirmed in the
  [authors' university publication record](https://scholar.xjtu.edu.cn/en/publications/veriml-enabling-integrity-assurances-and-fair-payments-for-machin/).
  IEEE Xplore's indexed publisher record confirms the venue, issue, pages and
  DOI. Direct access to its author panel was blocked by a JavaScript/bot check,
  so direct inspection of that panel is not claimed. The stable internal BibTeX
  key is retained, while the visible year and publication metadata are corrected.
- **Melis et al. [4].** Add pages 691–706 and DOI
  [10.1109/SP.2019.00029](https://doi.org/10.1109/SP.2019.00029), checked against
  [UCL Discovery](https://discovery.ucl.ac.uk/id/eprint/10061777/).
- **Jia et al. [24].** Add PMLR 89 pages 1167–1176, as listed in the
  [official proceedings](https://proceedings.mlr.press/v89/jia19a.html).
- **PASS [8].** The existing DOI is correct. Use the published DOI URL
  [10.1109/JIOT.2023.3288936](https://doi.org/10.1109/JIOT.2023.3288936)
  instead of the arXiv URL. The
  [authors' arXiv record](https://arxiv.org/abs/2207.07292) explicitly links that
  IEEE DOI and gives volume 11, issue 1, pages 1374–1384, 2024.
- **FRIDA [9].** Expose the existing DOI through the reference URL:
  [10.1016/j.jisa.2025.104357](https://doi.org/10.1016/j.jisa.2025.104357).
  The [publisher record](https://www.sciencedirect.com/science/article/pii/S221421262500393X)
  confirms volume 97, March 2026, article 104357. Retain the 2026 issue year.
- **RFA [16].** Expose the existing DOI through the reference URL:
  [10.1109/TSP.2022.3153135](https://doi.org/10.1109/TSP.2022.3153135).
  The [authors' arXiv record](https://arxiv.org/abs/1912.13445) confirms this
  DOI and the journal reference, volume 70, pages 1142–1154, 2022.
- **Yin et al. [15].** Retain pages 5650–5659. They agree with the
  [official PMLR record](https://proceedings.mlr.press/v80/yin18a.html).

IEEEtran renders these DOI URLs as clickable reference links. The reference
keys, citation numbering and all 31 entries remain stable. Layout-control
settings are unchanged. The rebuilt 19-page PDF has no undefined references or
citations, overfull boxes or oversized floats. Pages 2–4 and the bibliography
are checked for spacing regressions. Earlier notes below are revision history.

The review now follows approach, contribution, limitation, then connection to
the study. Source-backed descriptions are separated from interpretation and
implementation-specific measurements.

| Work | Source used | Scope of the criticism |
| --- | --- | --- |
| Lin et al., STD-DAGMM | [Original paper](https://arxiv.org/html/1911.12560v1) | Auxiliary neural-model fitting and memory; measured fitting cost is cross-referenced to this study's native-workflow experiment, without claiming a controlled speedup. |
| Fraboni et al. | [AISTATS paper](https://proceedings.mlr.press/v130/fraboni21a.html) | Stochastic disguises motivate going beyond unchanged-model checks. |
| Zhu et al. | [Original workshop paper](https://neurips2021workshopfl.github.io/NFFL-2021/papers/2021/Zhu2021.pdf) | Convergence and stealth motivate challenges; the current four attacks are not claimed to reproduce every advanced attack. |
| Wang et al., FRAD | [Published record](https://doi.org/10.1109/JIOT.2023.3298606), original abstract available on the publication record | Additional contribution/reputation signals and retained DAGMM fitting. Full text was not accessible; no unverified implementation-specific criticism was added. |
| Wang et al., PASS | [Accepted manuscript](https://arxiv.org/pdf/2207.07292) | Peer evaluation and update distribution add work and expose updates to additional parties. The paragraph acknowledges noise/pruning protections and does not claim a demonstrated breach. |
| Recasens et al., FRIDA | [Author manuscript](https://arxiv.org/html/2410.05020v2), [published record](https://doi.org/10.1016/j.jisa.2025.104357) | Membership variants add canary training and server evaluation; property variants infer local-data characteristics. These are distinct variants. |
| Bonawitz et al. | [Original CCS paper](https://acmccs.github.io/papers/p1175-bonawitzA.pdf) | Individual-update auditing conflicts with ordinary secure aggregation; this limitation also applies to BaitFL. |

Formatting and bibliography repairs:

- Load `cite` before `hyperref` to sort and compress numerical citation groups.
- Preserve the compound surname Agüera y Arcas in BibTeX.
- Expand AISTATS proceedings names and include the PMLR series/publisher.
- Identify Lin et al. as a preprint, not a journal publication.
- Identify the Rieke and FRIDA article numbers as article numbers.
- Add DOI links for entries lacking a clickable source; retain published issue
  years for PASS (2024) and FRIDA (2026), despite earlier online/DOI dates.

## Section II refinement — 4 November 2026

Rechecked the original manuscripts and rewrote the review to connect each
approach to a specific, restrained limitation. The wording varies across
paragraphs instead of repeating an approach/contribution/limitation template.

- **STD-DAGMM:** Sections 2.2 and 8 of Lin et al. establish auxiliary joint
  fitting and the MNIST/shallow-model evaluation scope. Differing local data
  distributions were tested, so the review does not claim heterogeneity was
  ignored. Runtime depends on the implementation and fitting schedule; our
  separately declared reproduction is not treated as the authors' runtime.
- **Anomalies and poor contributions:** An anomalous response or low utility
  is not, by itself, proof of non-training. This is our interpretation of what
  these scores measure, not a claim that a cited paper reported a particular
  false-positive result or failed to consider honest clients.
- **FRAD:** Retain the existing published-abstract description of contribution,
  reputation and DAGMM. Reliable estimation is a deployment consideration,
  not a demonstrated measurement failure. Full-text implementation details
  remain unverified and no additional such claims are introduced.
- **PASS:** Section III.A locates parameter audits on clients' own private data.
  The server receives scores, not those datasets. Section III.B discusses
  update exposure, Gaussian noise and pruning. Additional evaluation and
  distribution follow from that protocol. The utility/non-training distinction
  under heterogeneity is an interpretation, not a measured PASS failure.
- **FRIDA:** Sections 3.3.1, 3.4 and 3.6 specify client canary training, the
  server's labeled auxiliary set and server-side testing. Sections 3.5 and 5.2
  distinguish property inference from raw-data access and client canary work.
  Section 5.1 reports that canary-only adaptive training evades cosine-based
  detection while loss-based detection retains separation. The review now
  acknowledges that result instead of making a blanket canary-evasion claim.
  Privacy protections are acknowledged; inference is not described as
  invalidating federated learning.
- **Secure aggregation:** The individual-response visibility limitation also
  applies to BaitFL and is retained explicitly.

Checked primary sources:
[Lin et al.](https://arxiv.org/html/1911.12560v1),
[Fraboni et al.](https://proceedings.mlr.press/v130/fraboni21a.html),
[Zhu et al.](https://neurips2021workshopfl.github.io/NFFL-2021/papers/2021/Zhu2021.pdf),
[PASS](https://arxiv.org/pdf/2207.07292), and
[FRIDA](https://arxiv.org/html/2410.05020v2).

No experimental data, detector policy, or numerical results were changed.

Validation: PDFLaTeX/BibTeX rebuild passed (25 pages), with no unresolved
citations/references or overfull boxes and no BibTeX warnings. The literature
review pages were visually inspected; the timing-section reference resolves.

## Supplied-review response — 4 November 2026

Add 17 relevant sources and remove the medical motivation, for 31 cited works.
Each new source is used for a specific distinction rather than citation padding:

- DAGMM: https://openreview.net/forum?id=BJJLHbb0-
- Krum: https://proceedings.neurips.cc/paper/6617-machine-learning-with-adversaries-byzantine-tolerant-gradient-descent.pdf
- Median/trimmed mean: https://proceedings.mlr.press/v80/yin18a.html
- FLTrust: https://www.ndss-symposium.org/wp-content/uploads/ndss2021_6C-2_24434_paper.pdf
- RFA: https://arxiv.org/abs/1912.13445
- Proof of learning: https://arxiv.org/abs/2103.05633
- VeriML, inspected preprint version: https://arxiv.org/abs/1909.06961
- Data Shapley: https://proceedings.mlr.press/v97/ghorbani19c.html
- Efficient data valuation: https://proceedings.mlr.press/v89/jia19a.html
- GTG-Shapley: https://arxiv.org/abs/2109.02053
- FedProx: https://proceedings.mlsys.org/paper_files/paper/2020/hash/1f5fe83998a09396ebe6477d9475ba0c-Abstract.html
- SCAFFOLD: https://proceedings.mlr.press/v119/karimireddy20a.html
- FedNova: https://papers.neurips.cc/paper_files/paper/2020/hash/564127c03caab942e503ee6f810f54fd-Abstract.html
- Deep Leakage from Gradients: https://proceedings.neurips.cc/paper_files/paper/2019/hash/60a6c4002cc7b29142def8871531281a-Abstract.html
- Collaborative feature leakage: https://arxiv.org/abs/1805.04049
- LEAF: https://arxiv.org/abs/1812.01097
- FedScale: https://proceedings.mlr.press/v162/lai22a.html

Primary sources establish the technical descriptions. VeriML cites the 2019
preprint whose authors/content were inspected. Melis et al. follows the
manuscript's IEEE S&P 2019 venue metadata. RFA is described as building on secure
averaging, avoiding a blanket claim that all robust aggregators expose updates.
The requirements table concerns information exposure and computation location,
not measured privacy or runtime rankings. FRAD claims remain restricted to its
verified published description. PASS is not said to expose raw client records.
No universal canary-evasion claim is introduced for FRIDA.
