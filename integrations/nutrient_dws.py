"""Nutrient DWS on the far side of the firewall.

Nutrient's brief is deterministic, auditable output with a human in the loop
where a guess is not acceptable -- and quarantine is exactly the case where a
guess is not acceptable. So DWS Data Extraction runs only on documents Verso has
released, and Verso's findings are handed to the DWS Viewer for a human to
adjudicate, overlaid at their coordinates.

Behind an interface with a local fake so the demo runs offline. Point
VERSO_DWS_API_KEY / VERSO_DWS_URL at DWS to use the real service.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Protocol

from verso.scan import scan


class DWSClient(Protocol):
    def extract(self, path: str) -> dict: ...


class LocalFakeDWS:
    """Deterministic stand-in for DWS Data Extraction."""

    def extract(self, path: str) -> dict:
        name = Path(path).stem
        # deterministic pseudo-fields with confidences
        return {
            "engine": "[local-fake-dws]",
            "document": name,
            "fields": [
                {"name": "party_a", "value": "Landlord", "confidence": 0.98},
                {"name": "party_b", "value": "Tenant", "confidence": 0.97},
                {"name": "effective_term_months", "value": "12", "confidence": 0.95},
                {"name": "monthly_amount", "value": "2400.00", "confidence": 0.93},
            ],
        }


class RealDWS:  # pragma: no cover
    def __init__(self, url: str, api_key: str) -> None:
        self.url, self.api_key = url, api_key

    def extract(self, path: str) -> dict:
        raise NotImplementedError(
            "call DWS Data Extraction at %s with the campaign credentials" % self.url)


def get_dws_client() -> DWSClient:
    key = os.environ.get("VERSO_DWS_API_KEY")
    url = os.environ.get("VERSO_DWS_URL", "https://api.dws.nutrient.io")
    return RealDWS(url, key) if key else LocalFakeDWS()


@dataclass
class ExtractionOutcome:
    released: bool
    extraction: Optional[dict]
    review_items: list          # findings to adjudicate in the DWS Viewer


def extract_released(path: str, *, client: Optional[DWSClient] = None) -> ExtractionOutcome:
    """Extract only if Verso released the document; else hand findings to review."""
    result = scan(path)
    if result.decision == "quarantined":
        review = [
            {"rule": f.rule, "page": f.page + 1,
             "bbox": f.bbox.as_list() if f.bbox else None,
             "excerpt": f.excerpt}
            for f in result.high_findings
        ]
        return ExtractionOutcome(released=False, extraction=None, review_items=review)

    client = client or get_dws_client()
    return ExtractionOutcome(released=True, extraction=client.extract(path),
                             review_items=[])
