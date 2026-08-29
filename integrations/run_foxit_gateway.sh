#!/usr/bin/env bash
# Launch the Verso -> Foxit MCP gateway against the REAL Foxit PDF API server.
#
# Credentials are read from the environment, or from keys/foxit.env (gitignored).
# Copy integrations/foxit.env.example to keys/foxit.env and fill in your values,
# or just `export FOXIT_CLIENT_ID=... FOXIT_CLIENT_SECRET=...` before running.
#
#   ./integrations/run_foxit_gateway.sh
#
# The gateway serves MCP over stdio: no output on a healthy start means it is
# waiting for a client (e.g. Claude Desktop). Ctrl-C to stop.
set -euo pipefail
cd "$(dirname "$0")/.."          # project root

# Prefer the project venv; fall back to python3 on PATH.
PY="./.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

# Load credentials from keys/foxit.env if present (that path is gitignored).
if [ -f keys/foxit.env ]; then
  set -a; . keys/foxit.env; set +a
fi

: "${FOXIT_CLIENT_ID:?Set FOXIT_CLIENT_ID (export it, or put it in keys/foxit.env)}"
: "${FOXIT_CLIENT_SECRET:?Set FOXIT_CLIENT_SECRET (export it, or put it in keys/foxit.env)}"

# Launch Foxit's server through our shim (works around its broken entry points).
# Set unconditionally so a stale/incorrect exported value can't shadow it.
export FOXIT_MCP_COMMAND="python -m integrations.foxit_server_launch"

echo "Starting Verso->Foxit gateway (real backend) — Ctrl-C to stop." >&2
exec "$PY" -m integrations.foxit_mcp_gateway
