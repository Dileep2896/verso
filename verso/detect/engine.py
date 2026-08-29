"""Run every detector over the views and return findings in canonical order.

Findings sort by (page, bbox top, bbox left, rule id). Ties are impossible
under that key, which is what makes the output byte-stable across runs.
"""

from __future__ import annotations

from ..models import Finding, Views
from .registry import DETECTORS


def run_detectors(views: Views) -> list[Finding]:
    findings: list[Finding] = []
    for _class_id, fn in DETECTORS:
        findings.extend(fn(views))
    findings.sort(key=lambda f: f.sort_key())
    return findings
