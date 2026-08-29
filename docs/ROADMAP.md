# Roadmap

Deadline 2026-09-03 at 10:00 PDT. In person judging at the Santa Clara Convention
Center September 2 and 3. That means the real deadline is end of day September 1,
because the last two days are travel, setup, and things going wrong.

Six working days. The plan is front loaded on purpose.

---

## Friday Aug 28 (today, remainder)

Ground truth before product. Nothing else today.

- Register on Devpost, join the Foxit and Nutrient tracks
- Create the Nutrient DWS account using the campaign credentials in the brief
- Email Doctavian for API credentials so the dependency is removed early even if
  you never use it
- Collect five real host documents: a lease, an MSA, an NDA, an invoice, and one
  legitimately scanned document. Public templates are fine and better, since the
  corpus gets released
- Write `corpus/forge/a2_offcanvas.py`. One generator, the easiest class

**Done when** you can run the A2 generator and open the output in a PDF viewer,
see nothing unusual, and see the payload in `pdftotext` output.

## Saturday Aug 29

Corpus day. This is the day that decides whether the project is a demo or a
contribution, and it is the day it will be most tempting to skip ahead to code.

- Generators for A1, A3, A4, A5
- `corpus/manifest.yaml` recording class, host document, payload, injection
  coordinates, and seed for every case
- Ten cases per class across at least three host documents
- Ten clean controls, including the scanned one and one with a real annotation
- `make corpus` builds the whole thing reproducibly from the manifest
- `eval/run.py` skeleton that scans everything and prints a recall table, with a
  detector that finds nothing so the table reads all zeros

**Done when** `make eval` prints a table of zeros. A working harness with a
useless detector is the correct state to end Saturday in.

## Sunday Aug 30

Detector day. Now the loop is closed and you can grind.

- Ingest, three views, coordinate transform test
- Detectors for A2, then A1, then A4, then A5, then A3, in that order of
  increasing difficulty
- One class per loop iteration, one commit per green loop
- `make check` determinism gate passing

**Done when** recall is above 90 percent on A1, A2, A4, A5 and the false positive
rate on clean controls is zero. A3 can trail.

## Monday Aug 31

Product day.

- `verso scan` CLI with the exit codes from the contract
- Receipt emission for class R3, canonicalization, signing
- Receipt chaining and `ledger verify` if the morning goes well
- Findings overlay: render the flagged page with boxes drawn on it, output PNG.
  This single image is the most important asset in the demo video

**Done when** you can scan a file, get exit 2, get a receipt, and get a PNG with
a red box around invisible text on page three.

## Tuesday Sep 1

Integration and submission. Treat this as the last build day.

- Nutrient DWS extraction on released documents, Viewer for flagged review
- Foxit MCP server registered with Verso gating tool invocation
- Record the demo video, see `docs/SUBMISSION.md` for the beat sheet
- Write the Devpost page for both tracks
- Submit. Do not wait for Wednesday

**Done when** the submission is filed. Everything after this is upside.

## Wednesday Sep 2, in person

- A7 glyph mapping divergence if and only if everything above is done. This is
  the best demo moment and it is worth building on site if you have the room
- Advisory layer, if A7 is done
- Rehearse the ninety second version of the pitch out loud, standing up, at least
  five times

## Thursday Sep 3

- Buffer. Deadline is 10:00 PDT
- Talk to the Foxit and Nutrient people in person. Sponsor track judging is
  decided by humans who will remember whether you explained your thing well

---

## Cut criteria

If Sunday night arrives and recall is below 80 percent, cut A3 and A6 entirely and
ship four classes done properly. Four classes with a real number beats seven
classes with a hand-waved number, and the second thing is obvious to any judge who
asks one follow-up question.

If Monday night arrives without a working receipt, ship the scanner alone and
present the taxonomy as the design. The document firewall stands on its own.
