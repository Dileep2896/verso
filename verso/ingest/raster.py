"""Deterministic rasterization of a page to a PIL image via pypdfium2.

200 DPI is deliberate (docs/ARCHITECTURE.md): lower loses small legitimate
text and manufactures false invisible-ink hits; higher costs seconds per page
and buys nothing for a presence-or-absence check.
"""

from __future__ import annotations

from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

DEFAULT_DPI = 200


def render_page(path: str | Path, page_index: int, dpi: int = DEFAULT_DPI) -> Image.Image:
    """Render one page to an RGB PIL image at ``dpi``. Deterministic."""
    doc = pdfium.PdfDocument(str(path))
    try:
        page = doc[page_index]
        scale = dpi / 72.0
        pil = page.render(scale=scale, draw_annots=True).to_pil().convert("RGB")
        return pil
    finally:
        doc.close()


def points_to_pixels(value: float, dpi: int = DEFAULT_DPI) -> float:
    return value * dpi / 72.0


def pixels_to_points(value: float, dpi: int = DEFAULT_DPI) -> float:
    return value * 72.0 / dpi
