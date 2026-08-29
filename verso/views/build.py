"""Assemble the three views (stream, render, meta) for a loaded Document."""

from __future__ import annotations

from ..ingest.loader import Document
from ..ingest.raster import render_page
from ..models import Views
from .interpret import interpret_page
from .meta import build_meta
from .render import ocr_available, ocr_page


def build_views(doc: Document, with_render: bool = True) -> Views:
    views = Views(pages=doc.pages)

    # -- stream view + paint ops (deterministic, no OCR) -------------------- #
    for i, pike_page in enumerate(doc.pike.pages):
        mb = pike_page.mediabox
        page_top = float(mb[3])
        page_x0 = float(mb[0])
        spans, paints = interpret_page(pike_page, i, page_top, page_x0)
        views.stream.extend(spans)
        views.paints.extend(paints)

    # -- meta view ---------------------------------------------------------- #
    views.meta = build_meta(doc)

    # -- lazy grayscale rasterizer (deterministic; for occlusion's uniformity
    #    test). Rendered on demand per page and cached, so pages with no
    #    occlusion candidate are never rasterized. Independent of OCR/tesseract.
    _cache: dict[int, object] = {}
    path = doc.path

    def _rasterize(page: int):
        if page not in _cache:
            try:
                _cache[page] = render_page(path, page).convert("L")
            except Exception:
                _cache[page] = None
        return _cache[page]

    views.rasterize = _rasterize

    # -- render view (OCR, optional / cached) ------------------------------- #
    if with_render and ocr_available():
        views.render_available = True
        for i in range(doc.n_pages):
            page_h = doc.pages[i].height
            views.render.extend(ocr_page(doc.path, i, page_h))
    else:
        views.render_available = False

    return views
