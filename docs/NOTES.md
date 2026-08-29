# Notes

Running log of things tried that did not work, so they are not tried twice.
Written by the build loop when two consecutive iterations fail to move a number.

## Format

    ### A3 occlusion, 2026-08-30
    Tried: bbox containment on any fill op in the same stream.
    Result: recall 0.63, three false positives on watermarked clean docs.
    Why it failed: watermarks are fills drawn over text too.
    Next idea: require the fill to be fully opaque and post-dated in paint order.

## Build log

### A1 colour-match, 2026-08-28
Tried: flag near-white text as invisible when OCR finds no text at its box
(render corroboration).
Result: recall on A1 stuck at 0.90 and clean FP rate 0.500 — every clean doc
with a dark table header (white text on dark fill) false-positived.
Why it failed: tesseract does not reliably OCR white-on-dark, so the "no OCR
text here" test fired on legitimately visible white-on-dark text. The corroboration
was the wrong signal.
Fix that worked: drop OCR entirely for A1. Compute the effective background colour
under each span from paint order (topmost opaque fill drawn before the span,
else the white page default) and flag when text-to-background contrast is below
threshold. White-on-white -> flagged; white-on-dark -> high contrast -> clean.
Result: A1 recall 1.000, clean FP 0.000, and the whole A1 rule is now deterministic.

### A3 occlusion, 2026-08-28
Tried: after confirming an opaque post-drawn fill contains the text, additionally
require OCR to confirm the text is absent (render corroboration).
Result: A3 recall 0.90 — one nda case missed, covered_ratio came back 1.0 over a
region that was actually painted over.
Why it failed: OCR reported text inside a region an opaque fill covers. A covered
region is exactly where OCR is least trustworthy, and it was being allowed to veto
an unambiguous structural signal.
Fix that worked: let opacity + paint-order + containment drive the decision
(translucent watermarks are already excluded by the opacity gate). Record the OCR
signal in the finding as corroboration, never as a suppressor. A3 recall -> 1.000.

### Metadata text extraction, 2026-08-28
Bug: `_text_of` used `hasattr(obj, "read_bytes")` to decide whether a pikepdf
object was a stream. Every pikepdf.Object exposes read_bytes(); it only works on
streams. So every /Info value and every /JS string read back empty, and A5
javascript + info_custom cases silently missed (recall 0.60).
Fix: test `isinstance(obj, pikepdf.Stream)` first. A5 recall -> 1.000.

### Corpus byte-determinism, 2026-08-28
Symptom: `make corpus` produced different bytes every run even with fixed /Info
dates. Isolated to the trailer /ID: `deterministic_id=True` was hashing the
random /ID ReportLab had already embedded, so the "deterministic" id was
non-deterministic. Fix: delete /ID before the deterministic save so the id is
derived purely from content. Corpus is now byte-identical across builds.

### Real-world false positives, 2026-08-28
Scanning four real public PDFs (not the synthetic corpus) exposed exactly the
collapse EVAL.md warned about:
- A3 occlusion fired 55x on a LaTeX paper. Cause: a diagram's 537x1025pt figure
  fill "contains" its own visible labels; structural-only A3 can't tell a
  redaction from a diagram. Fix: after the structural match, require the rendered
  region under the text to be a near-uniform block (grayscale std-dev < 18, from
  the deterministic pypdfium2 raster — not OCR). A real redaction is uniform; a
  diagram's labels stay visible (high variance). Plus a cheap gate rejecting
  fills >60x the text area. 55 -> 0, corpus A3 recall still 1.000.
- A4 microtype fired 17x on the same paper at 3.73pt figure labels. Threshold
  was 4.0pt; real figures use ~3.7pt. Lowered to 3.0pt — corpus attacks all
  render <1.4pt, so recall held; the FPs went to 0.
- A5 flagged /PTEX.Fullbanner (pdfTeX) and /SPDF (Adobe) as high. Non-standard
  /Info keys and custom XMP namespaces are common in real files; treating their
  mere presence as quarantine-worthy was over-fit to a corpus with only standard
  metadata. Downgraded custom-metadata to MEDIUM (reported, not quarantining).
  Document JavaScript / embedded files / hidden annotations stay HIGH — those are
  genuinely agent-dangerous (the IRS W-9 quarantines on its form JS, correctly).
Lesson: the synthetic corpus keeps FP at 0 but cannot surface over-fit rules;
real documents must be in the test loop. See test-pdfs/.
