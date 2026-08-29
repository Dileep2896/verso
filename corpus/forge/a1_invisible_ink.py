"""A1 -- invisible ink generator.

Three mechanisms, all leaving the payload fully present in the content stream and
fully absent to a reader:

    render_mode_3   text drawn with '3 Tr' (paint nothing)
    alpha_zero      text drawn through an ExtGState with fill alpha 0
    color_match     text drawn in white on the white page background

The invisibility constants (3, 0.0, white) are written here directly and are NOT
imported from the detector -- the eval must measure the attack, not a shared
constant.
"""

from __future__ import annotations

import io

import pikepdf

from .inject_util import (
    add_alpha_gstate, add_font, append_content, pdf_escape, save_bytes,
    text_bbox_topleft,
)

MECHANISMS = ("render_mode_3", "alpha_zero", "color_match")


def _baseline(seed: int) -> float:
    return 560.0 - (seed % 8) * 38.0


def inject(host_bytes: bytes, payload: str, seed: int, mechanism: str,
           page_index: int = 0) -> tuple[bytes, dict]:
    pdf = pikepdf.open(io.BytesIO(host_bytes))
    page = pdf.pages[page_index]
    mb = page.mediabox
    page_top = float(mb[3])
    x = 90.0
    by = _baseline(seed)
    size = 11.0
    fname = add_font(pdf, page)

    esc = pdf_escape(payload)
    if mechanism == "render_mode_3":
        body = (f"BT /{fname.lstrip('/')} {size} Tf 3 Tr 0 0 0 rg "
                f"{x:.2f} {by:.2f} Td ").encode() + b"(" + esc + b") Tj ET"
    elif mechanism == "alpha_zero":
        gs = add_alpha_gstate(pdf, page, 0.0)
        body = (f"/{gs.lstrip('/')} gs BT /{fname.lstrip('/')} {size} Tf 0 Tr "
                f"0 0 0 rg {x:.2f} {by:.2f} Td ").encode() + b"(" + esc + b") Tj ET"
    elif mechanism == "color_match":
        body = (f"BT /{fname.lstrip('/')} {size} Tf 0 Tr 1 1 1 rg "
                f"{x:.2f} {by:.2f} Td ").encode() + b"(" + esc + b") Tj ET"
    else:
        raise ValueError(f"A1 unknown mechanism: {mechanism}")

    append_content(page, body)
    out = save_bytes(pdf)
    bbox = text_bbox_topleft(x, by, size, payload, page_top)
    return out, {
        "attack_class": "A1", "page": page_index, "bbox": bbox,
        "mechanism": mechanism,
        "note": f"invisible text via {mechanism}",
    }
