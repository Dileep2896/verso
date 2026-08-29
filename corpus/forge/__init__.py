"""Corpus generators. One module per attack class; no detector code is imported.

Every generator exposes ``inject(host_bytes, payload, seed, mechanism,
page_index) -> (pdf_bytes, ground_truth_dict)``.
"""

from . import (
    a1_invisible_ink, a2_offcanvas, a3_occlusion, a4_microtype, a5_metadata,
)

GENERATORS = {
    "A1": a1_invisible_ink.inject,
    "A2": a2_offcanvas.inject,
    "A3": a3_occlusion.inject,
    "A4": a4_microtype.inject,
    "A5": a5_metadata.inject,
}

__all__ = ["GENERATORS"]
