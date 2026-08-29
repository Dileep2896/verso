"""A1 -- invisible ink.

Text present in the content stream but drawn so a human sees nothing:

* render mode 3 or 7 ("add to the text stream but paint nothing") -- structural,
  needs no OCR and is the cleanest signal;
* fill alpha ~0 via an ExtGState -- structural;
* fill colour matching the page background (near-white) *and* no OCR text at
  those coordinates -- the one variant that needs render corroboration, which is
  also what keeps legitimate white-on-dark cover pages from being flagged (a
  human sees that text, so OCR sees it too).
"""

from __future__ import annotations

from ..models import Finding, Views
from .base import (
    SEV_HIGH, background_under, contrast, inside_ratio, make_finding,
    meaningful_len,
)

RULE_RENDER_MODE = "A1.render_mode_3"
RULE_ALPHA = "A1.alpha_zero"
RULE_COLOR = "A1.color_match"

INVISIBLE_RENDER_MODES = {3, 7}
ALPHA_EPS = 0.02
# Text is invisible-by-colour when its fill and the effective background beneath
# it differ by less than this on every channel -- white-on-white, black-on-black.
# White-on-*dark* has high contrast, so a legitimate dark banner is never
# flagged. This is structural: the background is read from paint order, not OCR.
CONTRAST_EPS = 0.12
MIN_LEN = 2
# only trust the colour-match rule where the span is actually on the page
MIN_INSIDE = 0.5


def detect(views: Views) -> list[Finding]:
    findings: list[Finding] = []
    crop_by_page = {p.index: p.cropbox for p in views.pages}
    paints_by_page: dict[int, list] = {}
    for p in views.paints:
        paints_by_page.setdefault(p.page, []).append(p)

    for span in views.stream:
        if span.bbox is None or meaningful_len(span.text) < MIN_LEN:
            continue
        rm = span.extra.get("render_mode", 0)
        alpha = span.extra.get("fill_alpha", 1.0)
        rgb = span.extra.get("fill_rgb", (0.0, 0.0, 0.0))

        if rm in INVISIBLE_RENDER_MODES:
            findings.append(make_finding(
                RULE_RENDER_MODE, "A1", SEV_HIGH, span,
                detail={"render_mode": rm,
                        "signal": "structural", "corroborated_by_ocr": False},
            ))
            continue  # one A1 finding per span is enough

        if alpha <= ALPHA_EPS:
            findings.append(make_finding(
                RULE_ALPHA, "A1", SEV_HIGH, span,
                detail={"fill_alpha": alpha, "signal": "structural"},
            ))
            continue

        # colour-match variant: fill colour ~= effective background colour.
        crop = crop_by_page.get(span.page)
        if crop is None or inside_ratio(span.bbox, crop) < MIN_INSIDE:
            continue
        bg = background_under(span.bbox, span.extra.get("paint_index", 1 << 30),
                              paints_by_page.get(span.page, []))
        if bg is None:            # sitting on an image; background colour unknown
            continue
        c = contrast(rgb, bg)
        if c < CONTRAST_EPS:
            findings.append(make_finding(
                RULE_COLOR, "A1", SEV_HIGH, span,
                detail={"fill_rgb": [round(v, 3) for v in rgb],
                        "background_rgb": [round(v, 3) for v in bg],
                        "contrast": round(c, 3),
                        "signal": "structural"},
            ))
    return findings
