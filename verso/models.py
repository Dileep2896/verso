"""Core data model shared across ingest, views, detect, and receipt.

Coordinate convention (locked, see docs/ARCHITECTURE.md):
every ``BBox`` is in PDF points with a top-left origin and y increasing
*downward* -- the same convention PyMuPDF, ``pdftotext -bbox`` and a
rasterized page all use. That makes "sort by top, then left" a natural
reading order and makes points -> pixels a single scale factor.

Nothing in this module imports a PDF library, an HTTP client, or a model
SDK. It is pure data so that ``verso/detect`` can depend on it without
tripping the no-LLM lint check.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Optional


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BBox:
    """Axis-aligned box in PDF points, top-left origin, y down (top < bottom)."""

    x0: float
    top: float
    x1: float
    bottom: float

    def __post_init__(self) -> None:
        # Normalize so x0<=x1 and top<=bottom regardless of caller order.
        # Capture originals first -- swapping in place would clobber them.
        x0, x1, top, bottom = self.x0, self.x1, self.top, self.bottom
        if x1 < x0:
            object.__setattr__(self, "x0", x1)
            object.__setattr__(self, "x1", x0)
        if bottom < top:
            object.__setattr__(self, "top", bottom)
            object.__setattr__(self, "bottom", top)

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    def intersection(self, other: "BBox") -> Optional["BBox"]:
        x0 = max(self.x0, other.x0)
        y0 = max(self.top, other.top)
        x1 = min(self.x1, other.x1)
        y1 = min(self.bottom, other.bottom)
        if x1 <= x0 or y1 <= y0:
            return None
        return BBox(x0, y0, x1, y1)

    def iou(self, other: "BBox") -> float:
        inter = self.intersection(other)
        if inter is None:
            return 0.0
        union = self.area + other.area - inter.area
        return inter.area / union if union > 0 else 0.0

    def contains(self, other: "BBox", pad: float = 0.5) -> bool:
        """True if ``self`` (grown by ``pad`` pts) fully contains ``other``."""
        return (
            self.x0 - pad <= other.x0
            and self.top - pad <= other.top
            and self.x1 + pad >= other.x1
            and self.bottom + pad >= other.bottom
        )

    def overlaps(self, other: "BBox") -> bool:
        return self.intersection(other) is not None

    def rounded(self, ndigits: int = 1) -> "BBox":
        r = round
        return BBox(
            r(self.x0, ndigits), r(self.top, ndigits),
            r(self.x1, ndigits), r(self.bottom, ndigits),
        )

    def as_list(self, ndigits: int = 1) -> list[float]:
        b = self.rounded(ndigits)
        return [b.x0, b.top, b.x1, b.bottom]


# --------------------------------------------------------------------------- #
# Views: a TextSpan is the shared shape of stream / render / meta output
# --------------------------------------------------------------------------- #
SOURCE_STREAM = "stream"
SOURCE_RENDER = "render"
SOURCE_META = "meta"


@dataclass
class TextSpan:
    """A run of text as seen by one view, with coordinates where they exist."""

    text: str
    page: int                    # 0-indexed page
    bbox: Optional[BBox]         # None only for metadata with no location
    source: str                  # SOURCE_STREAM | SOURCE_RENDER | SOURCE_META
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def norm_text(self) -> str:
        return _normalize(self.text)


@dataclass
class PaintOp:
    """A non-text paint operation (fill or image), used by occlusion detection."""

    kind: str                    # "fill" | "image"
    page: int
    bbox: BBox
    paint_index: int             # monotonic order within the page's stream
    opacity: float = 1.0         # fill alpha (ExtGState ca), 1.0 == opaque
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class PageInfo:
    index: int
    width: float                 # points
    height: float                # points
    mediabox: BBox               # in top-left points
    cropbox: BBox                # in top-left points
    has_text_layer: bool = True


@dataclass
class Views:
    """The three views plus the structural extras detectors key off."""

    stream: list[TextSpan] = field(default_factory=list)
    render: list[TextSpan] = field(default_factory=list)
    meta: list[TextSpan] = field(default_factory=list)
    paints: list[PaintOp] = field(default_factory=list)
    pages: list[PageInfo] = field(default_factory=list)
    render_available: bool = True   # False when OCR could not run
    # Lazy per-page rasterizer: page_index -> grayscale PIL image (or None).
    # Deterministic (pypdfium2), independent of OCR. Occlusion uses it to tell a
    # solid redaction (uniform pixels) from a diagram whose labels stay visible.
    rasterize: Optional[Any] = None

    def stream_on(self, page: int) -> list[TextSpan]:
        return [s for s in self.stream if s.page == page]

    def render_on(self, page: int) -> list[TextSpan]:
        return [s for s in self.render if s.page == page]


# --------------------------------------------------------------------------- #
# Findings
# --------------------------------------------------------------------------- #
SEV_HIGH = "high"
SEV_MEDIUM = "medium"
SEV_LOW = "low"

_SEV_RANK = {SEV_LOW: 0, SEV_MEDIUM: 1, SEV_HIGH: 2}


@dataclass
class Finding:
    """A structural detection with a location. No bbox -> not a finding."""

    rule: str                    # e.g. "A1.render_mode_3"
    attack_class: str            # e.g. "A1"
    severity: str                # SEV_HIGH | SEV_MEDIUM | SEV_LOW
    page: int                    # 0-indexed page
    bbox: Optional[BBox]
    excerpt: str
    excerpt_truncated: bool = False
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def sev_rank(self) -> int:
        return _SEV_RANK.get(self.severity, 0)

    def sort_key(self) -> tuple:
        """Deterministic total order: page, top, left, rule. Ties impossible."""
        if self.bbox is not None:
            b = self.bbox.rounded(1)
            top, left = b.top, b.x0
        else:
            # Metadata findings with no location sort after located ones,
            # stable by rule id.
            top = left = float("inf")
        return (self.page, top, left, self.rule)


# --------------------------------------------------------------------------- #
# Text normalization -- shared, deterministic, no external deps
# --------------------------------------------------------------------------- #
def _normalize(text: str) -> str:
    """Lowercase, collapse whitespace. Used for view-to-view text matching."""
    return " ".join(text.lower().split())


def levenshtein_ratio(a: str, b: str) -> float:
    """Normalized edit distance similarity in [0, 1]; 1.0 == identical.

    Small, dependency-free, deterministic. Used by A7 glyph-divergence and by
    the render/stream matcher. Not performance-critical (short strings).
    """
    a, b = _normalize(a), _normalize(b)
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    la, lb = len(a), len(b)
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        ca = a[i - 1]
        for j in range(1, lb + 1):
            cost = 0 if ca == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    dist = prev[lb]
    return 1.0 - dist / max(la, lb)


def truncate_excerpt(text: str, limit: int = 120) -> tuple[str, bool]:
    """Cap and sanitize attacker-controlled text for a receipt/finding.

    Strips control characters (a receipt is stored in systems never meant to
    hold hostile text) and flags truncation. Never returns the full payload.
    """
    cleaned = "".join(ch for ch in text if ch == " " or ch.isprintable())
    cleaned = " ".join(cleaned.split())
    if len(cleaned) <= limit:
        return cleaned, False
    return cleaned[:limit].rstrip() + "…", True


__all__ = [
    "BBox", "TextSpan", "PaintOp", "PageInfo", "Views", "Finding",
    "SOURCE_STREAM", "SOURCE_RENDER", "SOURCE_META",
    "SEV_HIGH", "SEV_MEDIUM", "SEV_LOW",
    "levenshtein_ratio", "truncate_excerpt", "replace",
]
