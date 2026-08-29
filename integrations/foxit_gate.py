"""Foxit MCP gate: the agent's document tools cannot run on unscanned bytes.

Foxit's own design leaves eSign out of the tool catalogue -- the right instinct
applied at the wrong end of the pipeline. Verso adds the boundary nobody drew:
before ANY Foxit document tool touches a file, the file must clear the firewall.
Anything Verso quarantines (exit code 2) is refused here, a receipt is written,
and the tool is never invoked.

The Foxit MCP client is behind an interface with a local fake, so this runs with
no network. Point VERSO_FOXIT_MCP at a real server to forward instead.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional, Protocol

from verso.receipt import (append, build_r3_receipt, latest,
                           load_or_create_keypair)
from verso.scan import scan


class FoxitClient(Protocol):
    def invoke(self, tool: str, path: str, **kwargs) -> Any: ...


class LocalFakeFoxit:
    """Stands in for the Foxit MCP document server for offline demos."""

    TOOLS = {"extract_text", "split_pages", "merge", "flatten", "get_metadata"}

    def invoke(self, tool: str, path: str, **kwargs) -> dict:
        if tool not in self.TOOLS:
            raise ValueError(f"unknown Foxit tool: {tool}")
        n = len(Path(path).read_bytes())
        return {"tool": tool, "path": str(path), "ok": True,
                "note": f"[local-fake-foxit] {tool} ran on {n} bytes"}


class RealFoxitMCP:
    def __init__(self, url: str) -> None:
        self.url = url

    def invoke(self, tool: str, path: str, **kwargs) -> Any:  # pragma: no cover
        raise NotImplementedError(
            "wire this to the Foxit MCP server at %s (register its tools and "
            "forward the call)" % self.url)


def get_foxit_client() -> FoxitClient:
    url = os.environ.get("VERSO_FOXIT_MCP")
    return RealFoxitMCP(url) if url else LocalFakeFoxit()


class QuarantineError(Exception):
    def __init__(self, result, receipt: Optional[dict]) -> None:
        super().__init__(f"{result.filename} quarantined; Foxit tool refused")
        self.result = result
        self.receipt = receipt


def guarded_invoke(tool: str, path: str, *, client: Optional[FoxitClient] = None,
                   ledger_dir: Optional[str] = "receipts/foxit",
                   on_behalf_of: Optional[str] = None) -> Any:
    """Run a Foxit tool only if Verso releases the document (exit 0)."""
    result = scan(path)
    if result.decision == "quarantined":
        receipt = None
        if ledger_dir is not None:
            private, public = load_or_create_keypair()
            receipt = build_r3_receipt(result, private, public,
                                       on_behalf_of=on_behalf_of,
                                       prev_id=latest(ledger_dir))
            append(receipt, ledger_dir)
        raise QuarantineError(result, receipt)

    client = client or get_foxit_client()
    return client.invoke(tool, path)
