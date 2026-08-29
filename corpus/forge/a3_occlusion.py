"""A3 -- occlusion generator.

Draw legitimate-looking text, then paint a fully opaque rectangle over it later
in the same stream. Painting order decides what a human sees. Three fill colours
(white, black-redaction, brand-colour) so the detector cannot key off colour --
it must key off paint order + opacity + containment, which is the actual attack.

The covering fill is fully opaque on purpose. A translucent fill would be a
watermark (a legitimate case that lives in the clean set), and the detector is
built to tell them apart.
"""

from __future__ import annotations

import io

import pikepdf
import pymupdf

from .inject_util import add_font, append_content, pdf_escape, save_bytes, text_bbox_topleft

MECHANISMS = ("fill_white", "fill_redaction", "fill_brand")

_COLORS = {
    "fill_white": (1.0, 1.0, 1.0),
    "fill_redaction": (0.0, 0.0, 0.0),
    "fill_brand": (0.16, 0.22, 0.33),
}


def _baseline(seed: int) -> float:
    return 520.0 - (seed % 7) * 40.0


def inject(host_bytes: bytes, payload: str, seed: int, mechanism: str,
           page_index: int = 0) -> tuple[bytes, dict]:
    pdf = pikepdf.open(io.BytesIO(host_bytes))
    page = pdf.pages[page_index]
    page_top = float(page.mediabox[3])
    x = 96.0
    by = _baseline(seed)
    size = 11.0
    fname = add_font(pdf, page)
    esc = pdf_escape(payload)

    width = pymupdf.get_text_length(payload, fontname="helv", fontsize=size)
    asc, desc = 0.75 * size, 0.25 * size
    r, g, b = _COLORS[mechanism]
    # rectangle covering the text, in PDF (bottom-left) coords, drawn AFTER text
    rx, ry = x - 2.0, by - desc - 2.0
    rw, rh = width + 4.0, (asc + desc) + 4.0

    text_part = (f"BT /{fname.lstrip('/')} {size} Tf 0 Tr 0 0 0 rg "
                 f"{x:.2f} {by:.2f} Td ").encode() + b"(" + esc + b") Tj ET\n"
    fill_part = (f"{r:.3f} {g:.3f} {b:.3f} rg "
                 f"{rx:.2f} {ry:.2f} {rw:.2f} {rh:.2f} re f").encode()
    append_content(page, text_part + fill_part)
    out = save_bytes(pdf)
    bbox = text_bbox_topleft(x, by, size, payload, page_top)
    return out, {
        "attack_class": "A3", "page": page_index, "bbox": bbox,
        "mechanism": mechanism,
        "note": f"opaque {mechanism} rect painted over text after it was drawn",
    }
