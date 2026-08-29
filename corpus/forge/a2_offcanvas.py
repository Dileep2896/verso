"""A2 -- off canvas generator.

Text positioned outside the CropBox: negative x, beyond the right edge, above the
top, or below the bottom. A renderer clips it; a parser returns it. Coordinates
are computed against the host's own MediaBox so the ground-truth box is exact.
"""

from __future__ import annotations

import io

import pikepdf

from .inject_util import add_font, append_content, pdf_escape, save_bytes, text_bbox_topleft

MECHANISMS = ("negative_x", "beyond_right", "above_top", "below_bottom")


def inject(host_bytes: bytes, payload: str, seed: int, mechanism: str,
           page_index: int = 0) -> tuple[bytes, dict]:
    pdf = pikepdf.open(io.BytesIO(host_bytes))
    page = pdf.pages[page_index]
    mb = page.mediabox
    x0, y0, x1, y1 = (float(v) for v in mb)
    page_top = y1
    page_w = x1 - x0
    page_h = y1 - y0
    size = 11.0
    jitter = (seed % 6) * 12.0

    if mechanism == "negative_x":
        x, by = x0 - 320.0 - jitter, y0 + page_h * 0.5
    elif mechanism == "beyond_right":
        x, by = x1 + 40.0 + jitter, y0 + page_h * 0.5
    elif mechanism == "above_top":
        x, by = x0 + 90.0, y1 + 60.0 + jitter
    elif mechanism == "below_bottom":
        x, by = x0 + 90.0, y0 - 60.0 - jitter
    else:
        raise ValueError(f"A2 unknown mechanism: {mechanism}")

    fname = add_font(pdf, page)
    esc = pdf_escape(payload)
    body = (f"BT /{fname.lstrip('/')} {size} Tf 0 Tr 0 0 0 rg "
            f"{x:.2f} {by:.2f} Td ").encode() + b"(" + esc + b") Tj ET"
    append_content(page, body)
    out = save_bytes(pdf)
    bbox = text_bbox_topleft(x, by, size, payload, page_top)
    return out, {
        "attack_class": "A2", "page": page_index, "bbox": bbox,
        "mechanism": mechanism,
        "note": f"off-canvas text via {mechanism}",
    }
