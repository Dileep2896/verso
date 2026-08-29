"""Clean-control construction that needs pikepdf post-processing.

The plain clean variants come straight from hosts.generate_clean. Two need real
metadata added so they exercise the detector's benign path: an annotated document
(a visible annotation + a form field) and a bookmarked document (real outlines).
These must produce at most LOW findings, never a quarantine.
"""

from __future__ import annotations

import io

import pikepdf

from .hosts import generate_clean
from .inject_util import add_annotation, add_form_field, add_outlines, save_bytes


def build_clean(kind: str) -> bytes:
    base = generate_clean(kind)
    if kind == "annotated":
        pdf = pikepdf.open(io.BytesIO(base))
        page = pdf.pages[0]
        # a genuine, visible reviewer note (no hidden/noview flag)
        add_annotation(pdf, page, [360.0, 690.0, 560.0, 740.0],
                       "Reviewed by Legal on 2026-01-14. Approved as to form.",
                       hidden=False, noview=False, subtype="/Text")
        add_form_field(pdf, page, [120.0, 120.0, 320.0, 140.0],
                       "signature_name", "Jordan A. Whitfield")
        return save_bytes(pdf)
    if kind == "bookmarked":
        pdf = pikepdf.open(io.BytesIO(base))
        add_outlines(pdf, ["1. Services", "2. Fees", "3. Term and Termination",
                           "4. Confidentiality", "5. Governing Law"])
        return save_bytes(pdf)
    return base
