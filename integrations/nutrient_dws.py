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

import json
import os
import ssl
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Protocol

from verso.scan import scan

DEFAULT_BASE = "https://api.nutrient.io"


def _ssl_ctx() -> ssl.SSLContext:
    """A verifying SSL context, using certifi's CA bundle where available
    (the python.org macOS build often lacks system CAs)."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


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


def _multipart(fields: dict, files: dict) -> tuple[bytes, str]:
    """Build a multipart/form-data body with stdlib (no requests dependency)."""
    boundary = "----verso" + uuid.uuid4().hex
    out = bytearray()
    for k, v in fields.items():
        out += (f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n').encode()
    for k, (fn, data, ct) in files.items():
        out += (f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{k}"; filename="{fn}"\r\n'
                f"Content-Type: {ct}\r\n\r\n").encode()
        out += data + b"\r\n"
    out += (f"--{boundary}--\r\n").encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def _normalize(out: dict, name: str) -> dict:
    """Fold the DWS json-content response into fields + a text sample."""
    fields, text = [], []
    pages = out.get("pages") or []
    for pg in pages:
        for kv in (pg.get("keyValuePairs") or []):
            key = (kv.get("key") or {}).get("text") if isinstance(kv.get("key"), dict) else kv.get("key")
            valobj = kv.get("value") if isinstance(kv.get("value"), dict) else {}
            val = valobj.get("text") if valobj else kv.get("value")
            conf = valobj.get("confidence") if valobj else kv.get("confidence")
            if key or val:
                fields.append({"name": str(key)[:60], "value": str(val)[:120],
                               "confidence": conf})
        pt = pg.get("plainText") or pg.get("text")
        if pt:
            text.append(pt)
    return {"engine": "nutrient-dws (build/json-content)", "document": name,
            "fields": fields, "pages": len(pages),
            "text_sample": (" ".join(text))[:400]}


class RealDWS:
    """Real DWS Processor API client: POST /build with a json-content output."""

    def __init__(self, api_key: str, base_url: Optional[str] = None) -> None:
        self.api_key = api_key
        self.base = (base_url or DEFAULT_BASE).rstrip("/")

    def extract(self, path: str) -> dict:
        data = Path(path).read_bytes()
        instructions = json.dumps({
            "parts": [{"file": "document"}],
            "output": {"type": "json-content", "plainText": True,
                       "tables": True, "keyValuePairs": True},
        })
        body, ctype = _multipart(
            {"instructions": instructions},
            {"document": (Path(path).name, data, "application/pdf")},
        )
        req = urllib.request.Request(
            f"{self.base}/build", data=body, method="POST",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": ctype},
        )
        try:
            with urllib.request.urlopen(req, timeout=90, context=_ssl_ctx()) as resp:
                out = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:200] if e.fp else ""
            return {"engine": "nutrient-dws", "document": Path(path).stem,
                    "fields": [], "error": f"HTTP {e.code}: {detail}"}
        except Exception as e:  # network/timeout/parse
            return {"engine": "nutrient-dws", "document": Path(path).stem,
                    "fields": [], "error": str(e)}
        return _normalize(out, Path(path).stem)


def get_dws_client() -> DWSClient:
    # official env names first, then Verso aliases
    key = (os.environ.get("NUTRIENT_DWS_API_KEY")
           or os.environ.get("VERSO_DWS_API_KEY"))
    base = os.environ.get("DWS_API_BASE_URL") or os.environ.get("VERSO_DWS_URL")
    return RealDWS(key, base) if key else LocalFakeDWS()


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
