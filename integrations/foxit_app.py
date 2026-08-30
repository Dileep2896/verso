"""Run a Foxit PDF operation on a document -- but only after Verso releases it.

This is the in-app equivalent of the MCP gateway: the exact same gate
(``verso.scan``), with no external MCP host (no Claude Desktop) required. The web
app calls :func:`run_foxit_action`; a quarantined document is refused here and the
Foxit tools are never invoked. On a released document we drive Foxit's own PDF API
MCP server in-process (our app is the MCP host) and return the result.

Only three actions are surfaced in the app, each a real Foxit tool:

    to_word     pdf_to_word        -> a .docx file (download)
    compress    pdf_compress       -> a smaller .pdf file (download)
    properties  get_pdf_properties -> document metadata (shown inline)

Credentials come from the environment (FOXIT_CLIENT_ID / FOXIT_CLIENT_SECRET);
with none set the app degrades gracefully to a "not configured" message.
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import anyio

from integrations.foxit_mcp_gateway import LocalFakeBackend, build_backend
from verso.scan import scan

COMPRESSION_LEVEL = "MEDIUM"
_DEFAULT_COMMAND = "python -m integrations.foxit_server_launch"

ACTIONS = {
    "to_word": ("pdf_to_word", ".docx"),
    "compress": ("pdf_compress", ".pdf"),
    "properties": ("get_pdf_properties", None),
}


def _ensure_command() -> None:
    """The app only asks the user for id/secret; we know the launch command."""
    if os.environ.get("FOXIT_CLIENT_ID") and os.environ.get("FOXIT_CLIENT_SECRET"):
        os.environ.setdefault("FOXIT_MCP_COMMAND", _DEFAULT_COMMAND)


def foxit_configured() -> bool:
    """True when real Foxit credentials are present (not the local fake)."""
    _ensure_command()
    return not isinstance(build_backend(), LocalFakeBackend)


def _readable_error(e: BaseException) -> str:
    """Flatten anyio/MCP ExceptionGroups to the underlying message(s)."""
    subs = getattr(e, "exceptions", None)
    if subs:
        return "; ".join(_readable_error(x) for x in subs)
    msg = str(e).strip()
    return f"{type(e).__name__}: {msg}" if msg else type(e).__name__


def _parse(content: Any) -> dict:
    """MCP tool results arrive as a list of TextContent; each Foxit tool returns
    a JSON string. Concatenate and decode it."""
    text = "".join(getattr(c, "text", "") for c in (content or []))
    try:
        return json.loads(text)
    except Exception:
        return {"success": False, "error": (text or "no response from Foxit")[:400]}


async def _run(backend, pdf_b64: str, action: str) -> dict:
    tool, suffix = ACTIONS[action]
    async with backend.session() as be:
        # 1. upload the released document
        up = _parse(await be.call_tool(
            "upload_document", {"fileContent": pdf_b64, "fileName": "input.pdf"}))
        if not up.get("success"):
            raise RuntimeError(up.get("error") or "upload failed")
        doc_id = up["documentId"]

        # 2. run the requested operation
        args: dict[str, Any] = {"documentId": doc_id}
        if action == "compress":
            args["compressionLevel"] = COMPRESSION_LEVEL
        res = _parse(await be.call_tool(tool, args))
        if not res.get("success"):
            raise RuntimeError(res.get("error") or f"{tool} failed")

        # 2a. get_pdf_properties returns data inline, not a file
        if action == "properties":
            return {"kind": "data", "data": res.get("resultData") or res}

        # 3. download the produced file (the server writes it to a temp path)
        result_doc = res.get("resultDocumentId")
        if not result_doc:
            raise RuntimeError("Foxit returned no result document")
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            out_path = Path(f.name)
        try:
            dl = _parse(await be.call_tool(
                "download_document",
                {"documentId": result_doc, "outputPath": str(out_path)}))
            if not dl.get("success"):
                raise RuntimeError(dl.get("error") or "download failed")
            data = out_path.read_bytes()
        finally:
            out_path.unlink(missing_ok=True)
        return {
            "kind": "file",
            "filename": f"verso-foxit{suffix}",
            "content": base64.b64encode(data).decode("ascii"),
            "size": len(data),
        }


def run_foxit_action(pdf_bytes: bytes, action: str) -> dict:
    """Gate the document, then run a Foxit action on it if it is released.

    Returns one of:
      {"refused": True, ...}         -- Verso quarantined it; Foxit not called
      {"not_configured": True, ...}  -- no Foxit credentials set
      {"ok": True, "kind": "file"|"data", ...}
      {"ok": False, "error": ...}    -- Foxit call failed (e.g. bad credentials)
    """
    if action not in ACTIONS:
        return {"ok": False, "error": f"unknown action: {action}"}

    # GATE -- re-scan server-side. A quarantined document never reaches Foxit,
    # no matter what the client claims. The decision is deterministic and OCR-free.
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_bytes)
        tmp = Path(f.name)
    try:
        result = scan(tmp, with_render=False, with_advisory=False)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass

    if result.exit_code == 2:
        return {
            "refused": True,
            "decision": result.decision,
            "reason": "Verso quarantined this document. Foxit was not called.",
        }
    if result.exit_code != 0:
        return {"ok": False, "error": "Document could not be scanned."}

    if not foxit_configured():
        return {
            "not_configured": True,
            "message": ("Foxit credentials are not set. Export FOXIT_CLIENT_ID and "
                        "FOXIT_CLIENT_SECRET, then restart the app to enable these "
                        "actions."),
        }

    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
    try:
        out = anyio.run(_run, build_backend(), pdf_b64, action)
        out["ok"] = True
        return out
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as e:  # incl. anyio BaseExceptionGroup / timeouts
        return {"ok": False, "error": _readable_error(e)[:400]}
