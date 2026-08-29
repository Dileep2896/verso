"""Clean stdio launcher for Foxit's PDF API MCP server.

Foxit's `foxit-pdf-api-mcp-server` 0.2.3 ships three entry-point defects that make
its own launch paths unusable with current dependencies:

  1. The console script and pyproject entry point name module `foxit_pdf_api_mcp`,
     but the installed package is `foxit_pdf_api_mcp_server` -> ModuleNotFoundError.
  2. `main()` calls `asyncio.run(mcp.run())`, but `fastmcp>=3` makes `run()` a
     synchronous blocking call, so the process raises `TypeError` on shutdown.

We only need the assembled FastMCP instance, which `main.py` builds at import time
(reading FOXIT_CLOUD_API_* from the environment). Import it and run it directly
over stdio -- correct for fastmcp 3.x, and free of both bugs above.

Point the Verso gateway at this launcher:

    export FOXIT_MCP_COMMAND="python -m integrations.foxit_server_launch"
"""

from __future__ import annotations


def main() -> None:
    # Imported lazily so `--help`/import of this module doesn't require the Foxit
    # package or its FOXIT_CLOUD_API_* env vars until we actually launch.
    from foxit_pdf_api_mcp_server.main import mcp

    mcp.run()  # blocking stdio server (fastmcp 3.x); serves until the client disconnects


if __name__ == "__main__":
    main()
