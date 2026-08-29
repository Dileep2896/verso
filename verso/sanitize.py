"""Emit a cleaned copy of a document, or refuse if it cannot be made safe.

Sanitization is intentionally conservative. It removes the metadata attack
vectors it can remove without touching page content -- document JavaScript,
embedded files, non-standard /Info keys, custom XMP, hidden annotations -- then
re-scans. If any high-severity structural finding remains (an in-content attack
such as invisible or occluded text), the document is refused rather than shipped
half-clean: a firewall that returns a document it still believes is hostile is
worse than one that refuses.

Original bytes are never modified; the cleaned copy is a new artifact.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pikepdf

from .scan import scan

STANDARD_INFO_KEYS = {
    "/Title", "/Author", "/Subject", "/Keywords", "/Creator",
    "/Producer", "/CreationDate", "/ModDate", "/Trapped",
}
FLAG_HIDDEN = 1 << 1
FLAG_NOVIEW = 1 << 5


@dataclass
class SanitizeResult:
    safe: bool
    cleaned_bytes: Optional[bytes]
    removed: list[str] = field(default_factory=list)
    remaining: list[str] = field(default_factory=list)


def _strip_metadata(pdf: pikepdf.Pdf) -> list[str]:
    removed: list[str] = []
    root = pdf.Root

    names = root.get("/Names")
    if names is not None:
        if "/JavaScript" in names:
            del names.JavaScript
            removed.append("document JavaScript (/Names/JavaScript)")
        if "/EmbeddedFiles" in names:
            del names.EmbeddedFiles
            removed.append("embedded files (/Names/EmbeddedFiles)")

    if "/OpenAction" in root:
        oa = root.OpenAction
        if hasattr(oa, "get") and str(oa.get("/S")) == "/JavaScript":
            del root.OpenAction
            removed.append("OpenAction JavaScript")
    if "/AA" in root:
        del root.AA
        removed.append("document additional actions (/AA)")

    info = pdf.trailer.get("/Info")
    if info is not None:
        for key in [k for k in info.keys() if k not in STANDARD_INFO_KEYS]:
            del info[key]
            removed.append(f"non-standard /Info key {key}")

    if "/Metadata" in root:
        try:
            xmp = root.Metadata.read_bytes().decode("utf-8", "replace")
            import re
            prefixes = {m.lower() for m in re.findall(r"xmlns:([A-Za-z0-9_]+)\s*=", xmp)}
            benign = {"dc", "xmp", "xmpmm", "pdf", "pdfaid", "pdfx", "rdf", "x",
                      "xmprights", "photoshop", "tiff", "exif"}
            if prefixes - benign:
                del root.Metadata
                removed.append("custom XMP metadata")
        except Exception:
            pass

    for page in pdf.pages:
        annots = page.obj.get("/Annots")
        if annots is None:
            continue
        keep = []
        for a in annots:
            flags = int(a.get("/F", 0))
            if (flags & FLAG_HIDDEN) or (flags & FLAG_NOVIEW):
                removed.append("hidden/no-view annotation")
                continue
            keep.append(a)
        if len(keep) != len(annots):
            page.obj.Annots = pikepdf.Array(keep)

    return removed


def sanitize(path: str | Path) -> SanitizeResult:
    data = Path(path).read_bytes()
    pdf = pikepdf.open(io.BytesIO(data))
    removed = _strip_metadata(pdf)
    buf = io.BytesIO()
    pdf.save(buf, deterministic_id=True)
    cleaned = buf.getvalue()

    # re-scan the cleaned copy; refuse if anything high remains
    import tempfile
    import os
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(cleaned)
        tmp = f.name
    try:
        result = scan(tmp, with_render=False)
    finally:
        os.unlink(tmp)

    remaining = sorted({f.rule for f in result.high_findings})
    if remaining:
        return SanitizeResult(False, None, removed, remaining)
    return SanitizeResult(True, cleaned, removed, [])
