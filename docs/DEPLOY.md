# Deploying Verso

Verso's web app runs a real PDF pipeline (pikepdf, pymupdf, pypdfium2, and
tesseract for the OCR render view), so it deploys as a **container**, not a
static or serverless site. Keys for the sponsor tools are entered in the app's
Settings and kept in the browser, so **the server holds no secrets**.

## Render (recommended)

The repo ships a `Dockerfile` and a `render.yaml` blueprint.

### Option A — Blueprint (one click, uses render.yaml)
1. Push this repo to GitHub (already done).
2. Go to <https://dashboard.render.com> and click **New +** then **Blueprint**.
3. Connect the `Dileep2896/verso` repo. Render reads `render.yaml`, shows a
   service named **verso** on the **free** plan. Click **Apply**.
4. First build takes a few minutes (installs tesseract, builds the sample
   corpus). When it goes live you get a URL like `https://verso.onrender.com`.

### Option B — Manual (no blueprint)
1. **New +** then **Web Service**, connect the repo.
2. Set **Language/Runtime** to **Docker** (Render auto-detects the `Dockerfile`).
3. Plan: **Free**. Health check path: `/`. Create the service.

Render injects `$PORT`; the container's `CMD` binds to it via gunicorn. Nothing
else to configure.

### Notes
- **Free tier sleeps.** After ~15 min idle the service spins down; the next
  request cold-starts in ~30-60s. Fine for a demo; hit the URL once to warm it
  before you present.
- **OCR is off on the deploy.** The render (OCR) view only corroborates and is
  the heaviest step; on a 512 MB free instance it exhausts memory and the scan
  never returns. The image sets `VERSO_WEB_OCR=0`, which gives byte-identical
  verdicts without the tesseract load. On a larger instance (more RAM/CPU) set
  `VERSO_WEB_OCR=1` to turn corroboration back on.
- **Sponsor tools.** With no keys set, the Foxit and Nutrient panels show as
  gated/locked and fall back to the local fake, so the app fully works offline.
  To make them live on the deploy, open **Settings** in the app and paste your
  own keys (they stay in your browser, sent per request, never stored on the
  server).
- **Receipt keys.** The Ed25519 signing key regenerates on each deploy (the
  container filesystem is ephemeral). Receipts stay self-verifying because each
  one embeds its public key.

## Run the container locally

```bash
docker build -t verso .
docker run --rm -p 8000:8000 verso
# open http://127.0.0.1:8000
```

## Fly.io (alternative)

The same `Dockerfile` works on Fly. `fly launch --no-deploy` to generate a
`fly.toml` (set the internal port to 8000), then `fly deploy`.
