"""A3 -- occlusion.

Legitimate-looking text is drawn, then an opaque fill or image is painted over
it later in the same stream. Painting order decides what a human sees;
extraction order does not.

The naive rule -- "any fill whose box contains text" -- false-positives on
watermarked documents, because a watermark is also a fill over text
(docs/NOTES.md). Two extra conditions fix that:

* the covering paint must be *fully opaque* (a watermark is translucent, so a
  reader still sees the text through it);
* where OCR is available, the text must be *absent* from the render view (if a
  reader can still read it, it was not actually occluded).

Both are drawn from the "post-dated, fully opaque" idea recorded in NOTES.
"""

from __future__ import annotations

from ..models import Finding, PaintOp, Views
from .base import (
    SEV_HIGH, inside_ratio, make_finding, meaningful_len, region_stddev,
)

RULE = "A3.occlusion"
OPAQUE_MIN = 0.98
ON_PAGE_MIN = 0.5
MIN_LEN = 3
WHITE_MIN = 0.90
INVISIBLE_RENDER_MODES = {3, 7}
# A rendered region under this grayscale std-dev is a solid block -- the text is
# actually hidden. Above it, the region still shows text/edges (a diagram, a
# chart label, a form line), so the "covering" fill did not hide anything. A
# clean redaction of black-on-white text renders near 0; a visible text line is
# ~50-90. 18 sits well clear of both.
UNIFORM_STDDEV = 18.0
# maximum covering-fill area (as a multiple of the text box) to still be a
# plausible redaction rather than a whole figure/page graphic swallowing labels
MAX_COVER_RATIO = 60.0


def _covering_paint(span_bbox, span_pi: int, paints: list[PaintOp],
                    span_area: float) -> PaintOp | None:
    for p in paints:
        if p.paint_index <= span_pi:
            continue
        if p.opacity < OPAQUE_MIN:
            continue
        if not p.bbox.contains(span_bbox, pad=1.0):
            continue
        # A redaction bar hugs its text; a fill dozens of times larger is a
        # figure/page graphic, not a redaction. The uniformity test is the real
        # gate, but this cheaply skips the obvious diagram fills first.
        if span_area > 0 and p.bbox.area > MAX_COVER_RATIO * span_area:
            continue
        return p
    return None


def detect(views: Views) -> list[Finding]:
    findings: list[Finding] = []
    crop_by_page = {p.index: p.cropbox for p in views.pages}
    paints_by_page: dict[int, list[PaintOp]] = {}
    for p in views.paints:
        paints_by_page.setdefault(p.page, []).append(p)

    for span in views.stream:
        if span.bbox is None or meaningful_len(span.text) < MIN_LEN:
            continue
        # Normally-drawn text only: invisible / near-white text is A1's job.
        if span.extra.get("render_mode", 0) in INVISIBLE_RENDER_MODES:
            continue
        rgb = span.extra.get("fill_rgb", (0.0, 0.0, 0.0))
        if all(c >= WHITE_MIN for c in rgb):
            continue
        crop = crop_by_page.get(span.page)
        if crop is not None and inside_ratio(span.bbox, crop) < ON_PAGE_MIN:
            continue

        paints = paints_by_page.get(span.page, [])
        cover_paint = _covering_paint(span.bbox, span.extra.get("paint_index", -1),
                                      paints, span.bbox.area)
        if cover_paint is None:
            continue

        # Confirm the text is ACTUALLY hidden: the rendered region under it must
        # be a near-uniform block. A diagram/chart whose labels stay visible has
        # a high-variance region and is not an occlusion. This is deterministic
        # (pypdfium2 raster), not OCR, and is what tells a redaction from a figure.
        std = region_stddev(views, span.page, span.bbox)
        if std is not None and std > UNIFORM_STDDEV:
            continue   # region still shows content -> nothing was hidden

        findings.append(make_finding(
            RULE, "A3", SEV_HIGH, span,
            detail={
                "cover_kind": cover_paint.kind,
                "cover_bbox": cover_paint.bbox.as_list(),
                "cover_opacity": cover_paint.opacity,
                "text_paint_index": span.extra.get("paint_index"),
                "cover_paint_index": cover_paint.paint_index,
                "region_stddev": round(std, 2) if std is not None else None,
            },
        ))
    return findings
