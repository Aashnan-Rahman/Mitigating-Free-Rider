# Local template and venue check

Checked 11 November 2026. The manuscript uses the local TeX Live installation's
IEEEtran journal class, version 1.8b (2015/08/26). Its installed path and SHA-256
are recorded in `VALIDATION.json`. This is a local build verification, rather
than reliance on the reviewer's Ubuntu package. No class file is copied into
the project to shadow the installed template.

The main source and isolated all-in-one export use journal, double-column
layout. Font size and page margins are set by IEEEtran. Existing small float
and heading-spacing choices are retained for readability; final published
pagination can differ from this working draft. The supplement is a separate
document, not an unannounced continuation of the main PDF.

## IEEE Internet of Things Journal

The journal's [official author guidelines](https://ieee-iotj.org/guidelines-for-authors/)
require an IEEE double-column template and a 150–250-word, single-paragraph
abstract. They state mandatory overlength charges of **US$175 per published
page beyond the first eight**, with submission signifying acceptance of the
mandatory-charge requirement. Eight pages is the charging threshold, not a
page limit inferred here.

At 15 main pages, the simple overlength calculation would be
`(15 - 8) × $175 = $1,225` if the final published pagination were unchanged.
This is not a fee quote or submission commitment and excludes any separately
applicable optional open-access charges. Editorial acceptance and treatment
of supplementary material must be confirmed for the actual submission; this
document does not promise that moving material online avoids every charge.

The reviewer's cited [2026 fee sheet](https://www.lib.nthu.edu.tw/research/doc/IEEE_Hybrid_OA.pdf)
also lists the $175 rate and eight-page threshold. The journal's own guidance
is used as the primary source. No medical application, deployment result,
venue acceptance or public archive DOI is introduced by this revision.
