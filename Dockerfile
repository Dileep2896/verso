# Verso — document firewall. Container image for a public deploy (Render, Fly, etc.).
#
# The render view shells out to tesseract, so this is a container job, not a
# static/serverless deploy. Keys are entered in the app's Settings and kept in
# the browser, so the server holds no secrets.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# System dependency: tesseract for the OCR "render" view. Everything else
# (pikepdf/qpdf, pymupdf, pypdfium2) ships self-contained manylinux wheels.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so the layer caches across code changes.
COPY requirements.txt ./
RUN pip install -r requirements.txt gunicorn

# App source.
COPY . .

# Build the labeled sample corpus so the in-app sample buttons work on the live
# site. Deterministic and offline; inputs (manifest + test-pdfs hosts) are in
# the repo. If this ever fails the build fails loudly, which is what we want.
RUN python -m corpus.build

# Render (and most hosts) inject $PORT; default to 8000 for a local `docker run`.
# One worker keeps memory modest on a free tier; threads cover the light
# concurrency, and the long timeout is a safety net for a stalled request.
ENV VERSO_WEB_HOST=0.0.0.0
# OCR (the render view) only corroborates and is the heaviest step; on a small
# host it exhausts memory and the scan never returns. Verdicts are byte-identical
# with it off, so default it off for the container. On a larger instance set
# VERSO_WEB_OCR=1 to turn corroboration back on.
ENV VERSO_WEB_OCR=0
EXPOSE 8000
CMD ["sh", "-c", "gunicorn webapp.server:app --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 4 --timeout 120"]
