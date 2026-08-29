"""The ordered list of structural detectors.

One module per attack class, in ascending build difficulty (docs/detect-loop).
Final findings are re-sorted deterministically by the engine, so this order is
only about readability. NO detector here may import an LLM or HTTP client.
"""

from __future__ import annotations

from . import a1_invisible_ink, a2_offcanvas, a3_occlusion, a4_microtype, a5_metadata

try:
    from . import a7_glyph_divergence  # optional, best-effort demo class
    _A7 = [("A7", a7_glyph_divergence.detect)]
except Exception:  # pragma: no cover
    _A7 = []

DETECTORS = [
    ("A2", a2_offcanvas.detect),
    ("A1", a1_invisible_ink.detect),
    ("A4", a4_microtype.detect),
    ("A5", a5_metadata.detect),
    ("A3", a3_occlusion.detect),
    *_A7,
]

IMPLEMENTED_CLASSES = [c for c, _ in DETECTORS]
