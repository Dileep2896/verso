"""Render view: text as a human sees it, via OCR of the rasterized page.

This is the only part of the system that feels nondeterministic, so it is used
as *corroboration* for structural signals rather than as a sole decision maker
(see docs/detect-loop). Tesseract is deterministic given the same image, config
and language data; we pin the config and cache by image hash so a re-scan of the
same bytes is byte-identical and fast.

If tesseract is not installed the render view is simply empty and
``render_available`` is False; the deterministic structural core still runs.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Optional

from ..ingest.raster import render_page, DEFAULT_DPI, pixels_to_points
from ..models import BBox, TextSpan, SOURCE_RENDER

# Pinned so the same bytes always yield the same OCR. --oem 1 = LSTM engine,
# --psm 3 = automatic page segmentation.
TESS_CONFIG = "--oem 1 --psm 3"
MIN_CONF = 40

_CACHE_DIR = Path(os.environ.get("VERSO_OCR_CACHE", ".ocr_cache"))
_available: Optional[bool] = None


def ocr_available() -> bool:
    global _available
    if _available is None:
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            _available = True
        except Exception:
            _available = False
    return _available


def _cache_path(img_hash: str) -> Path:
    return _CACHE_DIR / f"{img_hash}.json"


def ocr_page(path: str | Path, page_index: int, page_h: float,
             dpi: int = DEFAULT_DPI) -> list[TextSpan]:
    """Return render-view spans for one page (word level), in top-left points."""
    if not ocr_available():
        return []
    import pytesseract
    from pytesseract import Output

    img = render_page(path, page_index, dpi=dpi)
    img_hash = hashlib.sha256(img.tobytes()).hexdigest()[:32]

    cp = _cache_path(img_hash)
    if cp.is_file():
        try:
            rows = json.loads(cp.read_text())
        except Exception:
            rows = None
    else:
        rows = None

    if rows is None:
        data = pytesseract.image_to_data(img, config=TESS_CONFIG, lang="eng",
                                         output_type=Output.DICT)
        rows = []
        n = len(data["text"])
        for i in range(n):
            txt = (data["text"][i] or "").strip()
            try:
                conf = float(data["conf"][i])
            except (ValueError, TypeError):
                conf = -1.0
            if not txt or conf < MIN_CONF:
                continue
            rows.append([txt, int(data["left"][i]), int(data["top"][i]),
                         int(data["width"][i]), int(data["height"][i])])
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cp.write_text(json.dumps(rows))
        except Exception:
            pass

    spans: list[TextSpan] = []
    for txt, l, t, w, h in rows:
        x0 = pixels_to_points(l, dpi)
        top = pixels_to_points(t, dpi)
        x1 = pixels_to_points(l + w, dpi)
        bottom = pixels_to_points(t + h, dpi)
        spans.append(TextSpan(text=txt, page=page_index,
                              bbox=BBox(x0, top, x1, bottom), source=SOURCE_RENDER))
    return spans
