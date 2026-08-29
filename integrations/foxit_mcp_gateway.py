"""Verso MCP gateway in front of the Foxit PDF API MCP server.

Foxit's open-source MCP server (foxitsoftware/foxit-pdf-api-mcp-server) exposes
30+ document tools -- convert, OCR, merge, split, extract, compress, flatten,
compare, forms -- to any AI agent. Their design deliberately leaves eSign out of
the catalogue: the right instinct, applied at the wrong end of the pipeline.

This gateway adds the boundary nobody drew. An agent connects to Verso instead of
to Foxit directly. Verso re-exposes every Foxit tool, but before any of them runs
it scans the input document; if the document is quarantined (exit code 2) the
tool never runs and Verso returns a signed refusal receipt. Clean documents pass
straight through to the real Foxit tool.

    # point your MCP host (Claude Desktop, Cursor, ...) at:
    python -m integrations.foxit_mcp_gateway

Config (environment):
    FOXIT_CLIENT_ID / FOXIT_CLIENT_SECRET   Foxit PDF Services credentials
    FOXIT_MCP_COMMAND                        launch cmd for the Foxit MCP server
                                             (default: the python module below)
    FOXIT_MCP_ARGS                           extra args, space-separated
With no Foxit credentials set, the gateway runs against a local fake backend so
the GATE itself can be demonstrated offline; swapping in real Foxit is config
only.
"""

from __future__ import annotations

import os
import shlex
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from verso.receipt import append, build_r3_receipt, latest, load_or_create_keypair
from verso.scan import scan

SERVER_NAME = "verso-foxit-gateway"
LEDGER_DIR = os.environ.get("VERSO_GATEWAY_LEDGER", "receipts/foxit-gateway")

# argument keys a Foxit tool uses to name its input document
_PATH_KEYS = ("path", "file", "file_path", "input", "input_path", "input_file",
              "document", "document_path", "source", "source_path", "pdf",
              "pdf_path", "in_path")


def document_path(arguments: dict) -> Optional[str]:
    """Find the input document path in a tool's arguments, if any."""
    if not isinstance(arguments, dict):
        return None
    for k, v in arguments.items():
        if isinstance(v, str) and (k.lower() in _PATH_KEYS or v.lower().endswith(".pdf")):
            if Path(v).is_file():
                return v
    return None


def _refusal_text(result, receipt_id: Optional[str]) -> str:
    lines = [
        f"REFUSED by the Verso document firewall — the Foxit tool was NOT run.",
        f"{result.filename} is quarantined (exit code 2): it contains content "
        f"present in the file but not visible to a human reader.",
    ]
    for f in result.high_findings[:6]:
        where = f"page {f.page + 1}" if f.bbox else "metadata"
        lines.append(f"  · {f.rule} ({where}): “{f.excerpt}”")
    if receipt_id:
        lines.append(f"Signed refusal receipt {receipt_id} recorded in {LEDGER_DIR}.")
    lines.append("An agent must not read or act on these bytes. Sanitize or reject the file.")
    return "\n".join(lines)


def _write_receipt(result) -> Optional[str]:
    try:
        private, public = load_or_create_keypair()
        receipt = build_r3_receipt(result, private, public,
                                   on_behalf_of="foxit-mcp-gateway",
                                   prev_id=latest(LEDGER_DIR))
        append(receipt, LEDGER_DIR)
        return receipt["id"]
    except Exception:
        return None


async def gate_and_forward(backend, name: str, arguments: dict):
    """The gate: scan the input document, refuse if quarantined, else forward.

    Returns a list of MCP content items. Pure enough to unit-test without a live
    MCP transport (see tests/test_foxit_gateway.py).
    """
    import mcp.types as types

    path = document_path(arguments or {})
    if path:
        result = scan(path)
        if result.decision == "quarantined":
            rid = _write_receipt(result)
            return [types.TextContent(type="text", text=_refusal_text(result, rid))]
    return await backend.call_tool(name, arguments or {})


# --------------------------------------------------------------------------- #
# backends: the real Foxit MCP server, or a local fake for offline demos
# --------------------------------------------------------------------------- #
class LocalFakeBackend:
    """Offline stand-in so the gate can be exercised without Foxit credentials."""

    @asynccontextmanager
    async def session(self):
        yield self

    async def list_tools(self):
        import mcp.types as types
        return [
            types.Tool(name="extract_text", description="[fake Foxit] extract text",
                       inputSchema={"type": "object",
                                    "properties": {"path": {"type": "string"}},
                                    "required": ["path"]}),
            types.Tool(name="get_document_properties",
                       description="[fake Foxit] inspect properties",
                       inputSchema={"type": "object",
                                    "properties": {"path": {"type": "string"}},
                                    "required": ["path"]}),
        ]

    async def call_tool(self, name: str, arguments: dict):
        import mcp.types as types
        path = document_path(arguments or {}) or arguments.get("path", "?")
        n = Path(path).stat().st_size if Path(path).is_file() else 0
        return [types.TextContent(
            type="text",
            text=f"[local-fake-foxit] {name} ran on {Path(path).name} ({n} bytes)")]


class RealFoxitBackend:
    """Bridges to the real Foxit PDF API MCP server over stdio."""

    def __init__(self, command: list[str], env: dict) -> None:
        self.command = command
        self.env = env

    @asynccontextmanager
    async def session(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        params = StdioServerParameters(command=self.command[0],
                                       args=self.command[1:],
                                       env={**os.environ, **self.env})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                self._session = session
                yield self

    async def list_tools(self):
        return (await self._session.list_tools()).tools

    async def call_tool(self, name: str, arguments: dict):
        return (await self._session.call_tool(name, arguments)).content


def build_backend():
    """Real Foxit backend if credentials + launch command are configured, else fake."""
    # Accept either our own short names or Foxit's own FOXIT_CLOUD_API_* names.
    client_id = os.environ.get("FOXIT_CLIENT_ID") or os.environ.get("FOXIT_CLOUD_API_CLIENT_ID")
    client_secret = (os.environ.get("FOXIT_CLIENT_SECRET")
                     or os.environ.get("FOXIT_CLOUD_API_CLIENT_SECRET"))
    command = os.environ.get("FOXIT_MCP_COMMAND")
    if client_id and client_secret and command:
        args = shlex.split(os.environ.get("FOXIT_MCP_ARGS", ""))
        argv = shlex.split(command) + args
        # A bare "python"/"python3" in the launch command must resolve to THIS
        # interpreter (the venv that has the Foxit package installed), not whatever
        # a subprocess PATH lookup would find. shlex.split isn't shell-alias aware.
        if argv and argv[0] in ("python", "python3"):
            argv[0] = sys.executable
        # Foxit's own server reads FOXIT_CLOUD_API_* env vars, not our short names,
        # so translate here. Host defaults to the NA fusion endpoint but is overridable.
        host = (os.environ.get("FOXIT_CLOUD_API_HOST")
                or "https://na1.fusion.foxit.com/pdf-services")
        return RealFoxitBackend(
            command=argv,
            env={
                "FOXIT_CLOUD_API_HOST": host,
                "FOXIT_CLOUD_API_CLIENT_ID": client_id,
                "FOXIT_CLOUD_API_CLIENT_SECRET": client_secret,
            },
        )
    return LocalFakeBackend()


# --------------------------------------------------------------------------- #
async def run() -> None:
    from mcp.server.lowlevel import Server
    from mcp.server.stdio import stdio_server
    import mcp.types as types

    backend = build_backend()
    async with backend.session() as be:
        tools = await be.list_tools()
        server = Server(SERVER_NAME)

        @server.list_tools()
        async def _list_tools() -> list[types.Tool]:
            # advertise every Foxit tool, noting the firewall in the description
            out = []
            for tdef in tools:
                desc = (tdef.description or "") + " [gated by Verso: refused if the input is quarantined]"
                out.append(types.Tool(name=tdef.name, description=desc,
                                      inputSchema=tdef.inputSchema))
            return out

        @server.call_tool()
        async def _call_tool(name: str, arguments: dict) -> list:
            return await gate_and_forward(be, name, arguments)

        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())


def main() -> None:
    import anyio
    anyio.run(run)


if __name__ == "__main__":
    main()
