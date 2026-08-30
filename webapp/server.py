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

from flask import Flask, Response, jsonify, request, send_from_directory

from verso import __version__
from verso.annotate import annotate_bytes
from verso.errors import VersoError
from verso.receipt import build_r3_receipt, load_or_create_keypair
from verso.scan import scan
from verso.serialize import finding_dict

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "corpus" / "build"
HERE = Path(__file__).resolve().parent
MAX_BYTES = 25 * 1024 * 1024

app = Flask(__name__, static_folder=None)


# --------------------------------------------------------------------------- #
def _annotated_pdf_b64(result) -> str | None:
    """A NEW copy of the document with findings marked in place (base64), for
    download. The original is never touched."""
    try:
        return base64.b64encode(annotate_bytes(result)).decode("ascii")
    except Exception:
        return None


def _original_pdf_b64(result) -> str | None:
    """The original PDF (base64) for Verso's own in-app viewer, which draws the
    finding highlights itself so it can jump to and flash the exact spot."""
    try:
        return base64.b64encode(Path(result.path).read_bytes()).decode("ascii")
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
        "pdf": _original_pdf_b64(result),          # for Verso's own viewer + overlays
        "annotated": _annotated_pdf_b64(result),   # marked copy, for download
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


# The Verso mark ("The Fold"): a page with a turned-up cyan verso corner.
_FAVICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40">'
    '<rect width="40" height="40" rx="9" fill="#2DD4E8"/>'
    '<g fill="none" stroke="#04222A" stroke-width="2.6" stroke-linejoin="round" '
    'stroke-linecap="round">'
    '<path d="M11 8h13l6 6v16.5A1.5 1.5 0 0 1 28.5 32H12.5A1.5 1.5 0 0 1 11 30.5'
    'V9.5A1.5 1.5 0 0 1 11 8Z"/><path d="M14 22h11M14 26h8"/></g>'
    '<path d="M24 8v6h6z" fill="#04222A"/></svg>'
)


@app.get("/favicon.svg")
def favicon():
    return Response(_FAVICON, mimetype="image/svg+xml")


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


@app.get("/api/foxit/status")
def api_foxit_status():
    """Whether the in-app Foxit actions are enabled (real credentials present)."""
    try:
        from integrations.foxit_app import foxit_configured
        return jsonify({"configured": foxit_configured()})
    except Exception:
        return jsonify({"configured": False})


@app.post("/api/foxit")
def api_foxit():
    """Run a Foxit PDF operation on a RELEASED document.

    The gate is enforced here again server-side: the bytes are re-scanned and a
    quarantined document is refused before any Foxit tool runs -- the client
    cannot bypass it by calling this endpoint directly.
    """
    src = request.json or {}
    action = (src.get("action") or "").strip()
    pdf_b64 = src.get("pdf") or ""
    if not pdf_b64:
        return jsonify({"error": "no pdf provided"}), 400
    try:
        raw = base64.b64decode(pdf_b64)
    except Exception:
        return jsonify({"error": "bad pdf encoding"}), 400
    if len(raw) > MAX_BYTES:
        return jsonify({"error": "file too large (25 MB max)"}), 413
    if not raw.startswith(b"%PDF-"):
        return jsonify({"error": "not a PDF"}), 400
    # Never let an exception escape as an HTML 500 -- this endpoint's contract is
    # JSON, and the browser does r.json() on the result.
    # Optional bring-your-own-key creds from the UI Settings; fall back to env.
    # Sent only for this call, used for this call, never stored server-side.
    cid = (src.get("foxit_client_id") or "").strip() or None
    csec = (src.get("foxit_client_secret") or "").strip() or None
    try:
        from integrations.foxit_app import run_foxit_action
        return jsonify(run_foxit_action(raw, action, cid, csec))
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as e:  # noqa: BLE001 -- deliberately broad; return JSON
        return jsonify({"ok": False, "error": f"{type(e).__name__}: {e}"[:400]}), 200


@app.post("/api/nutrient")
def api_nutrient():
    """Extract a RELEASED document with Nutrient DWS. Gate is re-enforced here;
    a quarantined document is handed to review instead of extracted."""
    src = request.json or {}
    pdf_b64 = src.get("pdf") or ""
    if not pdf_b64:
        return jsonify({"error": "no pdf provided"}), 400
    try:
        raw = base64.b64decode(pdf_b64)
    except Exception:
        return jsonify({"error": "bad pdf encoding"}), 400
    if len(raw) > MAX_BYTES:
        return jsonify({"error": "file too large (25 MB max)"}), 413
    if not raw.startswith(b"%PDF-"):
        return jsonify({"error": "not a PDF"}), 400
    key = (src.get("dws_api_key") or "").strip() or None
    try:
        from integrations.nutrient_app import run_nutrient
        return jsonify(run_nutrient(raw, key))
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as e:  # noqa: BLE001 -- deliberately broad; return JSON
        return jsonify({"ok": False, "error": f"{type(e).__name__}: {e}"[:400]}), 200


def _pdf_from_request():
    """Decode + validate a base64 PDF from a JSON body. Returns (bytes, error_response)."""
    src = request.json or {}
    pdf_b64 = src.get("pdf") or ""
    if not pdf_b64:
        return None, (jsonify({"error": "no pdf provided"}), 400)
    try:
        raw = base64.b64decode(pdf_b64)
    except Exception:
        return None, (jsonify({"error": "bad pdf encoding"}), 400)
    if len(raw) > MAX_BYTES:
        return None, (jsonify({"error": "file too large (25 MB max)"}), 413)
    if not raw.startswith(b"%PDF-"):
        return None, (jsonify({"error": "not a PDF"}), 400)
    return raw, None


@app.post("/api/sanitize")
def api_sanitize():
    """`verso sanitize`: strip metadata attacks and return a cleaned copy, or
    refuse if the document has in-content attacks that cleaning can't remove."""
    raw, err = _pdf_from_request()
    if err:
        return err
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(raw)
        tmp = Path(f.name)
    try:
        from verso.sanitize import sanitize
        res = sanitize(tmp)
        out = {"safe": bool(res.safe), "removed": res.removed, "remaining": res.remaining}
        if res.safe and res.cleaned_bytes:
            out["content"] = base64.b64encode(res.cleaned_bytes).decode("ascii")
            out["filename"] = "cleaned.pdf"
        return jsonify(out)
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as e:  # noqa: BLE001
        return jsonify({"error": f"{type(e).__name__}: {e}"[:400]}), 200
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


@app.post("/api/overlay")
def api_overlay():
    """`verso scan --overlay`: a rasterized page with the findings drawn on it."""
    raw, err = _pdf_from_request()
    if err:
        return err
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(raw)
        tmp = Path(f.name)
    png = tmp.with_suffix(".png")
    try:
        result = scan(tmp, with_render=True, with_advisory=False)
        from verso.overlay import render_overlay
        render_overlay(result, str(png))
        data = png.read_bytes()
        return jsonify({"content": base64.b64encode(data).decode("ascii"),
                        "filename": "overlay.png"})
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as e:  # noqa: BLE001
        return jsonify({"error": f"{type(e).__name__}: {e}"[:400]}), 200
    finally:
        for p in (tmp, png):
            try:
                p.unlink()
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
