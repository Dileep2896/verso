"""Write a NEW annotated copy of the document with findings marked in place.

Unlike the raster overlay, this edits the PDF itself: a crisp vector rectangle at
each finding's coordinates plus a popup note carrying the rule id and the
extracted excerpt, so a reviewer can open the file in any PDF viewer, zoom, and
click a mark to read what was found. Metadata findings (no location) become
sticky notes on the first page.

The original bytes are never touched -- this always writes a separate artifact,
per the immutability invariant.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

# stroke colours in 0..1 RGB, by severity
SEV_RGB = {
    "high": (0.816, 0.165, 0.180),
    "medium": (0.760, 0.470, 0.050),
    "low": (0.470, 0.500, 0.550),
}
SEV_FILL = {
    "high": (0.980, 0.925, 0.918),
    "medium": (0.985, 0.955, 0.870),
    "low": (0.960, 0.968, 0.978),
}


def annotate_pdf(scan_result, out_path: str | Path) -> Path:
    """Add finding annotations to a copy of the document; return the new path."""
    doc = pymupdf.open(scan_result.path)
    try:
        meta_only = []
        for i, f in enumerate(scan_result.findings, 1):
            color = SEV_RGB.get(f.severity, SEV_RGB["low"])
            fill = SEV_FILL.get(f.severity, SEV_FILL["low"])
            title = f"Verso · {f.rule} [{f.severity}]"
            content = f.excerpt + ("…" if f.excerpt_truncated else "")
            if f.bbox is not None and 0 <= f.page < doc.page_count:
                page = doc[f.page]
                b = f.bbox
                rect = pymupdf.Rect(b.x0, b.top, b.x1, b.bottom)
                # clamp wildly off-page boxes so the annotation stays reachable
                pr = page.rect
                rect = rect & pymupdf.Rect(pr.x0 - 200, pr.y0 - 200,
                                           pr.x1 + 200, pr.y1 + 200)
                if rect.is_empty or rect.width <= 0 or rect.height <= 0:
                    rect = pymupdf.Rect(b.x0, b.top, b.x0 + 60, b.top + 12)
                annot = page.add_rect_annot(rect)
                annot.set_colors(stroke=color, fill=fill)
                annot.set_border(width=1.4)
                annot.set_opacity(0.85)
                annot.set_info(title=title, content=content)
                annot.update()
            else:
                meta_only.append((i, f, title, content))

        if meta_only:
            page = doc[0]
            y = 24.0
            for _i, _f, title, content in meta_only[:24]:
                note = page.add_text_annot(pymupdf.Point(18, y), content, icon="Note")
                note.set_info(title=title, content=content)
                note.set_colors(stroke=SEV_RGB.get(_f.severity, SEV_RGB["low"]))
                note.update()
                y += 22.0

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # new artifact; original file untouched
        doc.save(str(out_path), garbage=3, deflate=True)
        return out_path
    finally:
        doc.close()


def annotate_bytes(scan_result) -> bytes:
    """Return the annotated PDF as bytes (for the web app), original untouched."""
    import io
    doc = pymupdf.open(scan_result.path)
    try:
        for f in scan_result.findings:
            if f.bbox is None or not (0 <= f.page < doc.page_count):
                continue
            color = SEV_RGB.get(f.severity, SEV_RGB["low"])
            fill = SEV_FILL.get(f.severity, SEV_FILL["low"])
            page = doc[f.page]
            b = f.bbox
            pr = page.rect
            rect = pymupdf.Rect(b.x0, b.top, b.x1, b.bottom) & pymupdf.Rect(
                pr.x0 - 200, pr.y0 - 200, pr.x1 + 200, pr.y1 + 200)
            if rect.is_empty or rect.width <= 0 or rect.height <= 0:
                rect = pymupdf.Rect(b.x0, b.top, b.x0 + 60, b.top + 12)
            annot = page.add_rect_annot(rect)
            annot.set_colors(stroke=color, fill=fill)
            annot.set_border(width=1.4)
            annot.set_opacity(0.85)
            annot.set_info(title=f"Verso · {f.rule} [{f.severity}]",
                           content=f.excerpt + ("…" if f.excerpt_truncated else ""))
            annot.update()
        # metadata sticky notes
        meta = [f for f in scan_result.findings if f.bbox is None]
        if meta:
            page = doc[0]
            y = 24.0
            for f in meta[:24]:
                note = page.add_text_annot(pymupdf.Point(18, y),
                                           f.excerpt, icon="Note")
                note.set_info(title=f"Verso · {f.rule} [{f.severity}]",
                              content=f.excerpt)
                note.update()
                y += 22.0
        buf = io.BytesIO()
        doc.save(buf, garbage=3, deflate=True)
        return buf.getvalue()
    finally:
        doc.close()
