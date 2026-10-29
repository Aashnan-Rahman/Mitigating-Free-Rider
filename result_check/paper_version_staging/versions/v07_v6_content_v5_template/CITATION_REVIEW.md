# Citation and literature-review revision — 30 October 2026

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

No experimental data, detector policy, or numerical results were changed.

Validation: PDFLaTeX/BibTeX rebuild passed (25 pages), with no unresolved
citations/references or overfull boxes and no BibTeX warnings. The literature
review pages were visually inspected; the timing-section reference resolves.
