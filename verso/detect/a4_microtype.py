"""A4 -- microtype.

Text set below the visual threshold: a sub-point font size, or scaled to near
zero by the text matrix. Technically "visible", so it defeats a pure alpha or
render-mode check, but no human reads it. The threshold is a defensible number
recorded in every finding so it is auditable.
"""

from __future__ import annotations

from ..models import Finding, Views
from .base import SEV_HIGH, inside_ratio, make_finding, meaningful_len

RULE = "A4.microtype"
# Effective on-page height, in points, below which text is genuinely unreadable.
# Set to 3.0 so legitimate small print survives -- 6pt footnotes obviously, but
# also the ~3.7pt axis labels real papers put inside dense figures, which a 4.0
# cutoff false-positived. Corpus attacks all render under 1.4pt, well below this.
# Duplicated, not shared with the forge.
SIZE_THRESHOLD = 3.0
MIN_LEN = 4
ON_PAGE_MIN = 0.5


def detect(views: Views) -> list[Finding]:
    findings: list[Finding] = []
    crop_by_page = {p.index: p.cropbox for p in views.pages}
    for span in views.stream:
        if span.bbox is None or meaningful_len(span.text) < MIN_LEN:
            continue
        eff = span.extra.get("effective_size", span.extra.get("nominal_size", 99))
        if eff >= SIZE_THRESHOLD:
            continue
        # Off-canvas micro text belongs to A2; require this to be on the page.
        crop = crop_by_page.get(span.page)
        if crop is not None and inside_ratio(span.bbox, crop) < ON_PAGE_MIN:
            continue
        findings.append(make_finding(
            RULE, "A4", SEV_HIGH, span,
            detail={"effective_size": eff, "threshold": SIZE_THRESHOLD,
                    "nominal_size": span.extra.get("nominal_size")},
        ))
    return findings
