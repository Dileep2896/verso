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
# Two ways to be microtype, tuned so real figure labels don't false-positive:
#   * VERY_TINY -- anything below this is unreadable no matter what it says.
#     Corpus attacks all render under 1.4pt; real figure labels sit around
#     2.5-3.7pt, so 1.5 cleanly separates them.
#   * SIZE_THRESHOLD + MIN_RUN -- slightly larger small text only counts if it is
#     a substantial run (a hidden sentence), not a 4-8 char diagram label like
#     "Menu" or "Volume". Corpus payloads are 60-90 chars.
# Duplicated here, not shared with the forge.
VERY_TINY = 1.5
SIZE_THRESHOLD = 3.0
MIN_RUN = 20
MIN_LEN = 4
ON_PAGE_MIN = 0.5


def detect(views: Views) -> list[Finding]:
    findings: list[Finding] = []
    crop_by_page = {p.index: p.cropbox for p in views.pages}
    for span in views.stream:
        tlen = meaningful_len(span.text)
        if span.bbox is None or tlen < MIN_LEN:
            continue
        eff = span.extra.get("effective_size", span.extra.get("nominal_size", 99))
        tiny = eff < VERY_TINY
        small_run = eff < SIZE_THRESHOLD and tlen >= MIN_RUN
        if not (tiny or small_run):
            continue
        # Off-canvas micro text belongs to A2; require this to be on the page.
        crop = crop_by_page.get(span.page)
        if crop is not None and inside_ratio(span.bbox, crop) < ON_PAGE_MIN:
            continue
        findings.append(make_finding(
            RULE, "A4", SEV_HIGH, span,
            detail={"effective_size": eff,
                    "matched": "very_tiny" if tiny else "small_long_run",
                    "nominal_size": span.extra.get("nominal_size")},
        ))
    return findings
