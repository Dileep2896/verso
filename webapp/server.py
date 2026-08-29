"""A small Flask backend that runs the real scanner behind a web UI.

The detector is Python plus native PDF tooling, so it cannot run in a browser --
this server is the thin bridge. It saves an uploaded PDF to a temp file, runs
``verso.scan`` exactly as the CLI does, renders the overlay, builds a signed R3
receipt on a quarantine, and returns everything as JSON. The original bytes are
never modified and nothing from the document is ever shown to a model.

    python -m webapp            # then open http://127.0.0.1:8000
"""

from __future__ import annotations

import base64
import os
import tempfile
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from verso import __version__
from verso.errors import VersoError
from verso.overlay import render_overlay
from verso.receipt import build_r3_receipt, load_or_create_keypair
from verso.scan import scan
from verso.serialize import finding_dict

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "corpus" / "build"
HERE = Path(__file__).resolve().parent
MAX_BYTES = 25 * 1024 * 1024

app = Flask(__name__, static_folder=None)


# --------------------------------------------------------------------------- #
def _overlay_data_uri(result) -> str | None:
    """Render the findings overlay to a PNG and return it as a data URI."""
    if not result.findings:
        return None
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp = f.name
        render_overlay(result, tmp)
        data = Path(tmp).read_bytes()
        os.unlink(tmp)
        return "data:image/png;base64," + base64.b64encode(data).decode("ascii")
    except Exception:
        return None


def _receipt(result) -> dict | None:
    if result.decision != "quarantined":
        return None
    try:
        private, public = load_or_create_keypair(ROOT / "keys")
        return build_r3_receipt(result, private, public, on_behalf_of="web-demo")
    except Exception:
        return None


def _result_json(result, advisory: bool) -> dict:
    return {
        "decision": result.decision,
        "exit_code": result.exit_code,
        "subject": result.subject(),
        "findings": [finding_dict(f) for f in result.findings],
        "advisory": result.advisory if advisory else [],
        "overlay": _overlay_data_uri(result),
        "receipt": _receipt(result),
    }


def _scan_path(path: Path, advisory: bool, llm_config: dict | None = None) -> dict:
    result = scan(path, with_render=True, with_advisory=advisory,
                  advisory_config=llm_config)
    return _result_json(result, advisory)


def _llm_config_from_request() -> dict | None:
    """Read an optional bring-your-own-key LLM config from the request.

    The key is used only for this request's outbound call and is never stored or
    logged. Missing key -> the offline heuristic is used instead.
    """
    src = request.form if request.form else (request.json or {})
    provider = (src.get("provider") or "").strip()
    api_key = (src.get("api_key") or "").strip()
    if not provider or not api_key:
        return None
    return {
        "provider": provider,
        "api_key": api_key,
        "model": (src.get("model") or "").strip() or None,
        "base_url": (src.get("base_url") or "").strip() or None,
    }


# --------------------------------------------------------------------------- #
@app.get("/")
def index():
    return send_from_directory(HERE, "index.html")


@app.get("/api/samples")
def samples():
    """List the built corpus so the UI can offer one-click demo files."""
    import json
    labels = BUILD / "labels.json"
    if not labels.is_file():
        return jsonify({"attacks": [], "clean": [], "built": False})
    data = json.loads(labels.read_text())
    attacks = [
        {"id": a["id"], "file": a["file"], "attack_class": a["attack_class"],
         "mechanism": a["mechanism"]}
        for a in data.get("attacks", [])
    ]
    clean = [{"id": c["id"], "file": c["file"], "kind": c["kind"]}
             for c in data.get("clean", [])]
    return jsonify({"attacks": attacks, "clean": clean, "built": True})


@app.post("/api/scan")
def api_scan():
    advisory = request.form.get("advisory") == "true" or \
        (request.is_json and request.json.get("advisory") is True)
    llm_config = _llm_config_from_request() if advisory else None

    # sample by id (server-side file, no upload)
    sample = request.form.get("sample") or (request.json.get("sample")
                                            if request.is_json else None)
    if sample:
        rel = _sample_rel(sample)
        if rel is None:
            return jsonify({"error": "unknown sample id"}), 404
        try:
            return jsonify(_scan_path(BUILD / rel, advisory, llm_config))
        except VersoError as e:
            return jsonify({"decision": "error", "exit_code": 1, "error": str(e)}), 200

    # uploaded file
    up = request.files.get("file")
    if up is None or up.filename == "":
        return jsonify({"error": "no file provided"}), 400
    raw = up.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        return jsonify({"error": "file too large (25 MB max)"}), 413
    if not raw.startswith(b"%PDF-"):
        return jsonify({"decision": "error", "exit_code": 1,
                        "error": "not a PDF (bad header)"}), 200

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(raw)
        tmp = Path(f.name)
    try:
        out = _scan_path(tmp, advisory, llm_config)
        out["subject"]["filename"] = up.filename        # show the real name
        return jsonify(out)
    except VersoError as e:
        return jsonify({"decision": "error", "exit_code": 1, "error": str(e)}), 200
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def _sample_rel(sample_id: str) -> str | None:
    import json
    labels = BUILD / "labels.json"
    if not labels.is_file():
        return None
    data = json.loads(labels.read_text())
    for group in ("attacks", "clean"):
        for c in data.get(group, []):
            if c["id"] == sample_id:
                return c["file"]
    return None


def main() -> None:
    host = os.environ.get("VERSO_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("VERSO_WEB_PORT", "8000"))
    print(f"Verso {__version__} — document firewall")
    print(f"  open  http://{host}:{port}")
    app.run(host=host, port=port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
