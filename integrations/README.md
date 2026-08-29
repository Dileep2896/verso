# Sponsor integrations

Each integration hides behind an interface with a local fake, so the whole thing
runs offline; swapping in the real sponsor product is configuration only.

## Foxit — the agent being protected

Our thesis *is* Foxit's argument ("Your Agent Shouldn't Sign That"): the boundary
they drew at signing is right but insufficient — there is an earlier one at
ingestion. So we put Verso **in front of the Foxit MCP server**.

### `foxit_mcp_gateway.py` — Verso as an MCP gateway (the real integration)

An agent connects to **Verso** instead of to Foxit directly. Verso re-exposes
every Foxit tool, but before any of them runs it scans the input document; a
quarantined document (exit code 2) means the Foxit tool never runs and Verso
returns a signed refusal receipt. Clean documents pass straight through to the
real Foxit tool.

```bash
pip install -e '.[foxit]'          # adds the MCP SDK
python -m integrations.foxit_mcp_gateway
```

With no `FOXIT_MCP_COMMAND` set it runs against a local fake backend, so the gate
itself is demonstrable offline. To gate the **real** Foxit tools, install Foxit's
open-source server and set the launch command:

```bash
# install Foxit's open-source server
git clone https://github.com/foxitsoftware/foxit-pdf-api-mcp-server
pip install -e foxit-pdf-api-mcp-server/python/foxit-pdf-api-mcp-server

export FOXIT_CLIENT_ID=...          # Foxit PDF Services credentials (from the portal)
export FOXIT_CLIENT_SECRET=...
export FOXIT_MCP_COMMAND="python -m integrations.foxit_server_launch"   # stdio launcher
# export FOXIT_CLOUD_API_HOST=...   # optional, defaults to https://na1.fusion.foxit.com/pdf-services
# export FOXIT_MCP_ARGS="..."       # optional extra args
python -m integrations.foxit_mcp_gateway
```

Two things the gateway handles for you:

- **Env-var translation.** Foxit's server reads `FOXIT_CLOUD_API_HOST` /
  `FOXIT_CLOUD_API_CLIENT_ID` / `FOXIT_CLOUD_API_CLIENT_SECRET`; the gateway maps
  your `FOXIT_CLIENT_ID` / `FOXIT_CLIENT_SECRET` into those names (and defaults the
  host) when it launches the subprocess, so you set credentials in one place.
- **Broken upstream entry points.** Foxit's 0.2.3 console script imports a module
  name that doesn't exist, and its `main()` runs the `fastmcp>=3` server the old
  (async) way and crashes on shutdown. `integrations/foxit_server_launch.py` is a
  two-line shim that imports the assembled server and runs it correctly over stdio,
  which is why `FOXIT_MCP_COMMAND` points at the shim rather than Foxit's script.

A bare `python` in `FOXIT_MCP_COMMAND` is resolved to the interpreter running the
gateway (your venv), so the Foxit package is always found.

Then point your MCP host at the gateway. For Claude Desktop
(`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "verso-foxit": {
      "command": "python",
      "args": ["-m", "integrations.foxit_mcp_gateway"],
      "env": {
        "FOXIT_CLIENT_ID": "...",
        "FOXIT_CLIENT_SECRET": "...",
        "FOXIT_MCP_COMMAND": "python -m integrations.foxit_server_launch"
      }
    }
  }
}
```

The agent now sees Foxit's 30+ document tools, each gated on exit code 2. Refusals
are written to `receipts/foxit-gateway/` and verifiable with `verso ledger verify`.

### `foxit_gate.py` — the same idea as a plain function

`guarded_invoke(tool, path)` runs `verso scan` and only forwards to the Foxit
client on exit 0. Useful when you are calling Foxit tools from your own code
rather than through MCP.

## Nutrient DWS — extraction on the far side of the firewall

`nutrient_dws.py` runs DWS Data Extraction only on documents Verso *releases*
(exit 0); a quarantined document is handed to the DWS Viewer for human review
instead. This calls the **real DWS Processor API** (`POST
https://api.nutrient.io/build` with a `json-content` output that returns
extracted text, tables, and key-value pairs):

```bash
export NUTRIENT_DWS_API_KEY=...      # DWS Processor API key from the dashboard
# export DWS_API_BASE_URL=...        # optional, defaults to https://api.nutrient.io
python -c "from integrations.nutrient_dws import extract_released; \
           print(extract_released('yourfile.pdf'))"
```

With no key set it falls back to a local fake that returns deterministic fields,
so the flow is demonstrable offline. The wiring is verified end-to-end: a request
with a placeholder key reaches the API and returns a proper `401 Unauthorized`,
so a valid key is the only missing piece.

## Run the offline story

```bash
python -m integrations.demo_gate     # refuse a hostile doc, extract a clean one
```
