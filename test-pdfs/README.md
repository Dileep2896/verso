# Test PDFs

Ready-to-use files for trying the scanner (`verso scan <file>` or drop them into
the web app at `make web`).

## `clean/` — real public documents

Downloaded from public sources. They exercise the false-positive controls on
genuine files, not synthetic ones.

| File | Source | Verso result |
|---|---|---|
| `tracemonkey-paper.pdf` | Mozilla pdf.js sample (academic paper, 14pp) | **clean** (exit 0) |
| `somatosensory-article.pdf` | css4.pub typeset article | **clean** (exit 0) |
| `drylab-newsletter.pdf` | css4.pub newsletter | **clean** (exit 0) |
| `irs-w9-form.pdf` | irs.gov fillable form | **quarantined** — contains document JavaScript |

The IRS W-9 quarantines on `A5.javascript`: a real interactive form ships
executable JavaScript, and a document firewall's stance is that an agent should
not blindly ingest or execute it. That is a deliberate, explainable finding, not
a bug — the receipt names exactly why.

## `attacks/` — labeled adversarial files

Each carries one hidden payload. All quarantine (exit 2).

| File | Class | What's hidden |
|---|---|---|
| `invisible-ink.pdf` | A1 | text drawn with render mode 3 (paints nothing) |
| `white-text-on-white.pdf` | A1 | text the same colour as the page background |
| `off-canvas-text.pdf` | A2 | text positioned outside the crop box |
| `redaction-hiding-text.pdf` | A3 | live text under an opaque redaction bar |
| `microscopic-text.pdf` | A4 | text set below the readable size threshold |
| `document-javascript.pdf` | A5 | document-level JavaScript |
| `embedded-file.pdf` | A5 | an embedded instructions file |
| `hidden-annotation.pdf` | A5 | a FreeText annotation with the Hidden flag set |

Try one:

```bash
verso scan test-pdfs/attacks/invisible-ink.pdf --overlay out.png ; echo $?   # 2
verso scan test-pdfs/clean/tracemonkey-paper.pdf ; echo $?                    # 0
```
