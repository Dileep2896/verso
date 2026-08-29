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

## `wild/` — assorted real documents (unverified)

A grab-bag of real public PDFs from many different producers, for stress-testing
false positives on genuine files. Not pre-checked — run them yourself. Span 1 to
660 pages and six+ producers (pdfTeX, Adobe LiveCycle Designer, Acrobat
Distiller, Prince, Antenna House).

| File | Producer | Pages |
|---|---|---|
| `arxiv-attention.pdf` | pdfTeX (LaTeX) | 15 |
| `arxiv-bert.pdf` | pdfTeX (LaTeX) | 16 |
| `arxiv-deep-double-descent.pdf` | pdfTeX (LaTeX, math-heavy) | 24 |
| `icelandic-dictionary.pdf` | Prince (HTML→PDF, dense columns) | 660 |
| `usenix-paper.pdf` | Prince | 3 |
| `antennahouse-sample.pdf` | Antenna House (XSL-FO) | 2 |
| `irs-1040-form.pdf` | Adobe LiveCycle Designer (form) | 2 |
| `irs-w4-form.pdf` | Adobe LiveCycle Designer (form) | 5 |
| `uscis-i9-form.pdf` | Acrobat Distiller (form) | 4 |
| `orimi-pdf-test.pdf` | Acrobat Distiller | 1 |

Forms built with LiveCycle Designer often carry document JavaScript, so expect
some of them to quarantine on `A5.javascript` — that is the firewall doing its
job on real executable content, not a false positive. The papers and the
dictionary are good tests for the occlusion / microtype false positives that
real figures and dense typesetting used to trigger.

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
