"""A4 -- microtype generator.

Two mechanisms:

    tiny_font      a sub-point font size (0.6 - 1.4 pt)
    matrix_scale   a normal font size shrunk to near zero by the text matrix

Both are technically 'visible' and so defeat any pure alpha/render-mode check,
but no human reads them. The unreadable-size threshold lives in the detector,
not here.
"""

from __future__ import annotations

import io

import pikepdf
import pymupdf

from .inject_util import add_font, append_content, pdf_escape, save_bytes

MECHANISMS = ("tiny_font", "matrix_scale")


def _baseline(seed: int) -> float:
    return 540.0 - (seed % 9) * 34.0


def _bbox(x: float, by: float, eff_size: float, payload: str,
          page_top: float) -> list[float]:
    # forge-local geometry, using the effective (post-scale) size.
    width = pymupdf.get_text_length(payload, fontname="helv", fontsize=eff_size)
    asc, desc = 0.75 * eff_size, 0.25 * eff_size
    return [round(x, 1), round(page_top - (by + asc), 1),
            round(x + width, 1), round(page_top - (by - desc), 1)]


def inject(host_bytes: bytes, payload: str, seed: int, mechanism: str,
           page_index: int = 0) -> tuple[bytes, dict]:
    pdf = pikepdf.open(io.BytesIO(host_bytes))
    page = pdf.pages[page_index]
    page_top = float(page.mediabox[3])
    x = 96.0
    by = _baseline(seed)
    fname = add_font(pdf, page)
    esc = pdf_escape(payload)

    if mechanism == "tiny_font":
        size = 0.6 + (seed % 5) * 0.18            # 0.6 .. 1.32 pt
        eff = size
        body = (f"BT /{fname.lstrip('/')} {size:.3f} Tf 0 Tr 0 0 0 rg "
                f"{x:.2f} {by:.2f} Td ").encode() + b"(" + esc + b") Tj ET"
    elif mechanism == "matrix_scale":
        base = 12.0
        s = 0.04 + (seed % 4) * 0.01              # scale 0.04 .. 0.07
        eff = base * s                            # ~0.48 .. 0.84 pt
        body = (f"BT /{fname.lstrip('/')} {base} Tf 0 Tr 0 0 0 rg "
                f"{s:.4f} 0 0 {s:.4f} {x:.2f} {by:.2f} Tm ").encode() \
            + b"(" + esc + b") Tj ET"
    else:
        raise ValueError(f"A4 unknown mechanism: {mechanism}")

    append_content(page, body)
    out = save_bytes(pdf)
    bbox = _bbox(x, by, eff, payload, page_top)
    return out, {
        "attack_class": "A4", "page": page_index, "bbox": bbox,
        "mechanism": mechanism,
        "note": f"microtype via {mechanism}, effective size ~{eff:.2f}pt",
    }
