"""Run Nutrient DWS extraction from the web app -- only on released documents.

Mirrors integrations/foxit_app.py and the same gate (verso.scan). A released
document is extracted with DWS Data Extraction; a quarantined one is NOT extracted
-- its findings are handed to human review (the DWS Viewer), which is exactly
Nutrient's brief: don't guess on a document where a guess isn't acceptable.

Credentials come from the request (the web UI's Settings) or the environment; with
neither, a deterministic local fake is used so the flow demos offline (labelled).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from integrations.nutrient_dws import LocalFakeDWS, RealDWS
from verso.scan import scan


def _env_key() -> str | None:
    return (os.environ.get("NUTRIENT_DWS_API_KEY")
            or os.environ.get("VERSO_DWS_API_KEY"))


def run_nutrient(pdf_bytes: bytes, api_key: str | None = None) -> dict:
    """Gate the document, then extract it with DWS if released.

    Returns one of:
      {"review": True, "count": N, "items": [...]}  -- quarantined; handed to review
      {"ok": True, "data": {...}, }                 -- extracted (live or sample)
      {"ok": False, "error": ...}                   -- scan/DWS failure
    """
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_bytes)
        tmp = Path(f.name)
    try:
        result = scan(tmp, with_render=False, with_advisory=False)
        if result.exit_code == 2:
            items = [{"rule": fi.rule, "excerpt": (fi.excerpt or "")[:120]}
                     for fi in result.findings if fi.severity == "high"]
            return {"review": True, "count": len(items), "items": items[:12],
                    "decision": result.decision}
        if result.exit_code != 0:
            return {"ok": False, "error": "Document could not be scanned."}

        key = (api_key or "").strip() or _env_key()
        client = RealDWS(key) if key else LocalFakeDWS()
        try:
            data = client.extract(str(tmp))
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as e:  # network / parse / timeout
            return {"ok": False, "error": f"{type(e).__name__}: {e}"[:400]}
        if isinstance(data, dict) and data.get("error"):
            return {"ok": False, "error": data["error"]}
        data["live"] = bool(key)
        return {"ok": True, "data": data}
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
