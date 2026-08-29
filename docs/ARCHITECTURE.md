# Architecture

## Pipeline

```
input.pdf
   |
   +-- ingest      load, validate, hash, rasterize pages at 200 DPI
   |
   +-- views       build three independent views
   |     S  stream    text + bbox from the content stream
   |     R  render    text + bbox from OCR of the rasterized page
   |     M  meta      everything outside page content
   |
   +-- detect      structural rules, one module per attack class
   |                 deterministic, no model calls, sorted output
   |
   +-- advisory    optional semantic pass over visible text only
   |                 model calls allowed, cannot change the decision
   |
   +-- decide      any high-severity structural finding -> quarantine
   |
   +-- receipt     canonicalize, chain, sign, write
   |
   v
exit 0 (clean) | exit 2 (quarantined) | exit 1 (error)
```

## The three views

Each view is a list of `TextSpan(text, page, bbox, source)` plus view-specific
extras. Building them the same shape is what makes the diff logic small.

**Stream view.** `pdftotext -bbox-layout` gives text with coordinates and is fast
and reliable. pypdf gives access to the raw content stream operators, which is
where the render mode, text matrix, and painting order live. You need both:
pdftotext for the span list, pypdf for the operator-level signals that A1, A3 and
A4 key off. Do not try to reimplement a content stream interpreter.

**Render view.** pypdfium2 rasterizes at 200 DPI. Tesseract with a bounding box
output mode produces spans in image coordinates, which then need transforming back
into PDF user space. Get that transform right early and write a test for it,
because every coordinate-dependent rule downstream inherits the bug if you do not.

200 DPI is a deliberate choice. Lower loses small legitimate text and creates
false A1 hits. Higher costs seconds per page and buys nothing for a
presence-or-absence check.

**Meta view.** A full object graph walk with pypdf, plus `pdfdetach -list` for
embedded files. Collect: `/Info`, XMP packets, outline titles, annotation
`/Contents` and `/TU`, form field `/V` and `/DV`, document and field level
JavaScript, optional content group names, embedded file names and streams. Every
item is a span with a synthetic bbox where one exists and null where it does not.

## The diff

Four comparisons, in this order.

1. **Stream not in render.** For each span in S, look for overlapping text in R
   within an IoU threshold. No match means the text is present to a parser and
   not to a reader. This is the general case behind A1, A3 and A4.
2. **Render not in stream.** The inverse. Suppressed on pages with no text layer
   at all, which are simply scans.
3. **Both present, text differs.** Overlapping boxes with a normalized edit
   distance above the cutoff. This is A7.
4. **Anything in meta.** Always reported, no comparison needed.

Structural signals shortcut the diff. If a span was drawn with `3 Tr`, you already
know it is invisible and you do not need OCR to agree with you. Prefer the
structural signal and use the render diff as corroboration, recording both in the
finding. This matters because OCR is the only nondeterministic-feeling part of the
system and you want the fewest possible decisions resting on it alone.

## Determinism

`make check` scans every corpus file twice and asserts identical output hashes.
The usual culprits when it fails:

- Iterating a dict or set without sorting
- Timestamps or absolute paths inside findings
- Unsorted `glob` results
- Tesseract configuration drift, so pin the config and the language data
- Float formatting, so round coordinates to one decimal at serialization time

Findings sort by page, then bbox top, then bbox left, then rule id. Ties are
impossible under that key, which is the point.

## Where the sponsors fit

**Nutrient DWS** is the extraction and human review layer. Once a document is
released, DWS Data Extraction pulls the fields with confidence scores, and the DWS
Viewer is where a human reviews the ones Verso flagged, with the findings
overlaid at their coordinates. This is the honest fit for their brief, since their
argument is deterministic auditable output with a human in the loop where a guess
is not acceptable, and quarantine is the case where a guess is not acceptable.
Free for the whole event, credentials in the hackathon brief.

**Foxit** is the downstream agent being protected. Register their open source MCP
server, and put Verso in front of it so the agent's document tools cannot be
invoked on bytes that have not passed the firewall. eSign stays outside the tool
catalog, which is their design and also our argument: the boundary they drew at
signing is correct but insufficient, and there is a second boundary at ingestion
that nobody drew.

**Doctavian**, if scope allows, is the generation side. A cleaned document with a
Verso receipt attached is the input to their generation API. Optional, and the
first sponsor to cut.

Keep every sponsor integration behind an interface with a local fake. Two days
before a deadline is the wrong time to discover that a hosted API is rate limited,
and a demo that cannot run offline is a demo that will fail in the room.

## Advisory layer

`verso/advisory/` may call a model to flag machine-addressed language in text that
is confirmed visible. It exists because attack class A8 is not solvable
structurally and pretending otherwise would be dishonest.

Hard constraints, enforced by a lint check in CI:

- Nothing under `verso/detect/` may import anything under `verso/advisory/`
- Nothing under `verso/detect/` may import an HTTP client or a model SDK
- Advisory output lands in the `advisory` array of the receipt, never `findings`
- The exit code is computed before the advisory pass runs

The last one is the strongest form of the guarantee. If the decision is already
final when the model is called, the model cannot influence it regardless of what
anyone later adds to the code.
