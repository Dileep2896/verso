"""Load, validate, and hash a PDF. Never writes to the input file.

Opens the document once with pikepdf (object graph + raw content streams)
and once with PyMuPDF (page geometry + convenient decoded text). Both handles
are read-only. The original bytes are hashed on the way in and never mutated.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pikepdf
import pymupdf  # PyMuPDF; the `fitz` alias is deprecated upstream.

from ..errors import EncryptedDocumentError, MalformedDocumentError
from ..models import BBox, PageInfo


@dataclass
class Document:
    path: Path
    raw_bytes: bytes
    sha256: str
    n_pages: int
    pages: list[PageInfo]
    revisions: int              # count of %%EOF markers; >1 == incremental update
    pike: pikepdf.Pdf
    mu: "pymupdf.Document"

    @property
    def filename(self) -> str:
        return self.path.name

    @property
    def size(self) -> int:
        return len(self.raw_bytes)

    def close(self) -> None:
        try:
            self.pike.close()
        finally:
            self.mu.close()

    def __enter__(self) -> "Document":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def _mediabox_to_topleft(rect, page_height: float) -> BBox:
    """PDF boxes are bottom-left, y up. Convert a [x0,y0,x1,y1] to top-left."""
    x0, y0, x1, y1 = (float(v) for v in rect)
    # top-left origin: top = page_height - y_top(=y1); bottom = page_height - y0
    return BBox(x0, page_height - y1, x1, page_height - y0)


def load(path: str | Path) -> Document:
    p = Path(path)
    if not p.is_file():
        raise MalformedDocumentError(f"no such file: {p}")

    raw = p.read_bytes()
    if not raw.startswith(b"%PDF-"):
        raise MalformedDocumentError(f"not a PDF (bad header): {p}")

    digest = hashlib.sha256(raw).hexdigest()
    revisions = raw.count(b"%%EOF")

    try:
        pike = pikepdf.open(p)
    except pikepdf.PasswordError as e:
        raise EncryptedDocumentError(f"encrypted PDF, out of scope: {p}") from e
    except Exception as e:  # pikepdf raises a variety of parse errors
        raise MalformedDocumentError(f"could not parse PDF: {p}: {e}") from e

    try:
        mu = pymupdf.open(p)
    except Exception as e:
        pike.close()
        raise MalformedDocumentError(f"could not parse PDF: {p}: {e}") from e

    if mu.is_encrypted:
        pike.close()
        mu.close()
        raise EncryptedDocumentError(f"encrypted PDF, out of scope: {p}")

    pages: list[PageInfo] = []
    for i, page in enumerate(mu):
        # PyMuPDF rect is already top-left points.
        media = page.mediabox      # in PDF (bottom-left) space
        crop = page.cropbox
        ph = float(page.mediabox.height)
        pw = float(page.mediabox.width)
        # Use PyMuPDF's rect (top-left) for the render/crop rectangle actually used.
        r = page.rect              # cropped page rect, top-left points
        media_tl = _mediabox_to_topleft(
            [float(media.x0), float(media.y0), float(media.x1), float(media.y1)], ph
        )
        crop_tl = _mediabox_to_topleft(
            [float(crop.x0), float(crop.y0), float(crop.x1), float(crop.y1)], ph
        )
        has_text = bool(page.get_text("text").strip())
        pages.append(
            PageInfo(
                index=i,
                width=float(r.width),
                height=float(r.height),
                mediabox=media_tl,
                cropbox=crop_tl,
                has_text_layer=has_text,
            )
        )

    return Document(
        path=p,
        raw_bytes=raw,
        sha256=digest,
        n_pages=len(pages),
        pages=pages,
        revisions=revisions,
        pike=pike,
        mu=mu,
    )
