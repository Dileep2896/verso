"""Deterministic serialization of findings and scan output.

Pages are 1-indexed in all external output (findings are 0-indexed internally).
Kept separate from the receipt canonicalizer, which adds signing-specific rules.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import Finding


def _clean(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 3)
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in sorted(value.items())}
    return value


def finding_dict(f: Finding) -> dict:
    return {
        "rule": f.rule,
        "attack_class": f.attack_class,
        "severity": f.severity,
        "page": f.page + 1,
        "bbox": f.bbox.as_list() if f.bbox is not None else None,
        "excerpt": f.excerpt,
        "excerpt_truncated": f.excerpt_truncated,
        "detail": _clean(f.detail),
    }


def findings_output(findings: list[Finding], decision: str) -> dict:
    return {
        "decision": decision,
        "findings": [finding_dict(f) for f in findings],
    }


def output_hash(findings: list[Finding], decision: str) -> str:
    """Hash used by ``make check``. Excludes timestamps and the advisory pass."""
    payload = findings_output(findings, decision)
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
