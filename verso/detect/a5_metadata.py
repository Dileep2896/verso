"""A5 -- metadata payload (with A10 hidden-annotation folded in).

Naive ingestion pipelines concatenate everything they can pull out of a file
before handing it to a model. Verso's stance is that an agent must never treat
metadata as content. But every clean PDF carries benign metadata, so reporting
*all* of it as high severity would quarantine every clean document.

Severity policy (see the verso-a5-severity-policy note / docs):

  HIGH  (quarantines) -- categorically agent-dangerous and rare in benign docs:
        document/field JavaScript, embedded files, non-GoTo OpenActions,
        non-standard /Info keys, custom XMP namespaces, and hidden / no-view /
        off-page annotations carrying text (the A10 case).

  LOW   (reported, never flips the exit code) -- ordinary metadata that a naive
        pipeline would still ingest as content: visible annotation text, outline
        titles, form-field values, optional-content-group names.

  IGNORED -- standard /Info values and benign XMP: pure provenance, not content.
"""

from __future__ import annotations

from ..models import BBox, Finding, TextSpan, Views
from .base import SEV_HIGH, SEV_MEDIUM, SEV_LOW, inside_ratio, make_finding

HIGH_KINDS = {
    "javascript": "A5.javascript",
    "embedded_file": "A5.embedded_file",
    "open_action": "A5.open_action",
}
# Custom metadata keys/namespaces are reported but do NOT quarantine: real
# documents carry them routinely (pdfTeX writes /PTEX.Fullbanner, Adobe writes
# /SPDF and custom XMP), so treating their mere presence as high severity
# false-positived on ordinary files. They ride in the receipt for a human to
# see; only executable/hidden constructs above flip the exit code.
MEDIUM_KINDS = {
    "info_custom": "A5.info_custom_key",
    "xmp_custom": "A5.xmp_custom_namespace",
}
LOW_KINDS = {
    "outline": "A5.outline_title",
    "form_field": "A5.form_default",
    "ocg": "A5.ocg_name",
}
RULE_HIDDEN_ANNOT = "A5.hidden_annotation"
RULE_VISIBLE_ANNOT = "A5.annotation_content"


def _annotation_offpage(span: TextSpan, views: Views) -> bool:
    if span.bbox is None:
        return False
    crop = next((p.cropbox for p in views.pages if p.index == span.page), None)
    if crop is None:
        return False
    return inside_ratio(span.bbox, crop) < 0.3


def detect(views: Views) -> list[Finding]:
    findings: list[Finding] = []
    for span in views.meta:
        kind = span.extra.get("meta_kind", "")

        if kind in HIGH_KINDS:
            findings.append(make_finding(
                HIGH_KINDS[kind], "A5", SEV_HIGH, span,
                detail={"meta_kind": kind, "field": span.extra.get("field")},
            ))
            continue

        if kind in MEDIUM_KINDS:
            findings.append(make_finding(
                MEDIUM_KINDS[kind], "A5", SEV_MEDIUM, span,
                detail={"meta_kind": kind, "field": span.extra.get("field")},
            ))
            continue

        if kind == "annotation":
            hidden = span.extra.get("hidden") or span.extra.get("noview")
            offpage = _annotation_offpage(span, views)
            if hidden or offpage:
                findings.append(make_finding(
                    RULE_HIDDEN_ANNOT, "A5", SEV_HIGH, span,
                    detail={"subtype": span.extra.get("field"),
                            "hidden": bool(span.extra.get("hidden")),
                            "noview": bool(span.extra.get("noview")),
                            "off_page": offpage,
                            "flags": span.extra.get("flags")},
                ))
            else:
                findings.append(make_finding(
                    RULE_VISIBLE_ANNOT, "A5", SEV_LOW, span,
                    detail={"subtype": span.extra.get("field")},
                ))
            continue

        if kind in LOW_KINDS:
            findings.append(make_finding(
                LOW_KINDS[kind], "A5", SEV_LOW, span,
                detail={"meta_kind": kind, "field": span.extra.get("field")},
            ))
            # standard 'info' and benign 'xmp' are intentionally not reported
    return findings
