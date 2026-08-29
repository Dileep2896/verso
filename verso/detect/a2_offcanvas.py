"""A2 -- off canvas.

Text positioned outside the CropBox is never rasterized, so a renderer never
shows it, but a parser that walks the content stream returns it. Pure
coordinate arithmetic; no rendering required. This is the cheapest and most
certain class, which is why it is first.
"""

from __future__ import annotations

from ..models import Finding, Views
from .base import SEV_HIGH, inside_ratio, make_finding, meaningful_len

RULE = "A2.off_cropbox"
# A span is off-canvas if 70%+ of it lies outside the crop box. Duplicated here
# (not shared with the generator) on purpose.
MAX_INSIDE_RATIO = 0.30
MIN_LEN = 2


def detect(views: Views) -> list[Finding]:
    findings: list[Finding] = []
    crop_by_page = {p.index: p.cropbox for p in views.pages}
    for span in views.stream:
        if span.bbox is None or meaningful_len(span.text) < MIN_LEN:
            continue
        crop = crop_by_page.get(span.page)
        if crop is None:
            continue
        ratio = inside_ratio(span.bbox, crop)
        if ratio <= MAX_INSIDE_RATIO:
            findings.append(make_finding(
                RULE, "A2", SEV_HIGH, span,
                detail={
                    "inside_cropbox_ratio": round(ratio, 3),
                    "cropbox": crop.as_list(),
                    "span_bbox": span.bbox.as_list(),
                },
            ))
    return findings
