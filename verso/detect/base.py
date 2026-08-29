"""Shared helpers for the structural detectors.

Detectors may share helpers *with each other* (this module). What they may not
do, per docs/detect-loop and the CI lint check, is import an LLM client, an HTTP
client, the advisory package, or any constant from a corpus generator. Nothing
here does. Everything is arithmetic over the Views data structure.
"""

from __future__ import annotations

from ..models import (
    BBox, Finding, TextSpan, Views,
    SEV_HIGH, SEV_MEDIUM, SEV_LOW, truncate_excerpt,
)


def make_finding(rule: str, attack_class: str, severity: str, span: TextSpan,
                 detail: dict | None = None, bbox: BBox | None = None) -> Finding:
    excerpt, truncated = truncate_excerpt(span.text)
    return Finding(
        rule=rule,
        attack_class=attack_class,
        severity=severity,
        page=span.page,
        bbox=bbox if bbox is not None else span.bbox,
        excerpt=excerpt,
        excerpt_truncated=truncated,
        detail=detail or {},
    )


def covered_ratio(views: Views, page: int, bbox: BBox) -> float:
    """Fraction of ``bbox`` overlapped by render-view (OCR) text on that page.

    A high ratio means a human reader sees text there; a near-zero ratio on a
    page that otherwise has a text layer means the stream text is not visible.
    """
    if bbox is None or bbox.area <= 0:
        return 0.0
    covered = 0.0
    for r in views.render:
        if r.page != page or r.bbox is None:
            continue
        inter = bbox.intersection(r.bbox)
        if inter is not None:
            covered += inter.area
    return min(1.0, covered / bbox.area)


def page_has_render_text(views: Views, page: int) -> bool:
    return any(r.page == page for r in views.render)


def inside_ratio(inner: BBox, outer: BBox) -> float:
    """Fraction of ``inner``'s area that lies within ``outer``."""
    if inner is None or inner.area <= 0:
        return 0.0
    inter = inner.intersection(outer)
    return (inter.area / inner.area) if inter else 0.0


def meaningful_len(text: str) -> int:
    return len(text.strip())


# Page default background: an unfilled PDF page is white.
PAGE_BACKGROUND = (1.0, 1.0, 1.0)
_OPAQUE = 0.9


def background_under(bbox: BBox, span_paint_index: int, paints) -> tuple | None:
    """Effective background colour beneath a text span, from paint order.

    The topmost opaque fill drawn *before* the span whose box contains it wins;
    if none, the page's white default. Returns None when that covering paint is
    an image (colour unknown) so the caller can decline to guess.
    """
    best_pi = -1
    best_rgb: tuple | None = PAGE_BACKGROUND
    found_cover = False
    for p in paints:
        if p.paint_index >= span_paint_index or p.opacity < _OPAQUE:
            continue
        if not p.bbox.contains(bbox, pad=1.0):
            continue
        if p.paint_index > best_pi:
            best_pi = p.paint_index
            found_cover = True
            if p.kind == "image":
                best_rgb = None
            else:
                best_rgb = tuple(p.detail.get("fill_rgb", PAGE_BACKGROUND))
    return best_rgb if found_cover else PAGE_BACKGROUND


def contrast(a: tuple, b: tuple) -> float:
    """Max per-channel absolute difference between two RGB colours, in [0, 1]."""
    return max(abs(x - y) for x, y in zip(a, b))


def region_stddev(views, page: int, bbox: BBox, dpi: int = 200) -> Optional[float]:
    """Pixel std-dev of the rendered page under ``bbox`` (grayscale), or None.

    A solid redaction renders as a near-uniform block (low std-dev); a diagram
    whose labels stay visible renders with edges and text (high std-dev). This is
    deterministic (same bytes -> same raster -> same number) and needs no OCR.
    """
    rasterize = getattr(views, "rasterize", None)
    if rasterize is None:
        return None
    img = rasterize(page)
    if img is None:
        return None
    scale = dpi / 72.0
    x0 = int(bbox.x0 * scale); y0 = int(bbox.top * scale)
    x1 = int(bbox.x1 * scale); y1 = int(bbox.bottom * scale)
    x0 = max(0, min(x0, img.width)); x1 = max(0, min(x1, img.width))
    y0 = max(0, min(y0, img.height)); y1 = max(0, min(y1, img.height))
    if (x1 - x0) < 3 or (y1 - y0) < 3:
        return None
    from PIL import ImageStat
    crop = img.crop((x0, y0, x1, y1))
    try:
        return float(ImageStat.Stat(crop).stddev[0])
    except Exception:
        return None


__all__ = [
    "make_finding", "covered_ratio", "page_has_render_text", "inside_ratio",
    "meaningful_len", "background_under", "contrast", "region_stddev",
    "PAGE_BACKGROUND", "SEV_HIGH", "SEV_MEDIUM", "SEV_LOW",
]
