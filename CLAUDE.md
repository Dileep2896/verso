# CLAUDE.md

Operating contract for Claude Code on this repository. Read this file fully before
your first edit in any session. If something here conflicts with a request in
chat, say so out loud rather than silently picking one.

## What Verso is

Verso is a document firewall. It inspects a PDF before any AI agent is allowed to
read it, finds content that is present in the file but not present to a human
reader, and refuses to release the document if it finds any. Every refusal is
emitted as a signed, replayable receipt.

The thesis in one line: the trust boundary for document agents is at ingestion,
not at signature. By the time a hostile document reaches the signing step, the
attack already succeeded.

Built for the DevNetwork API + Cloud + AI Hackathon 2026. Submission deadline
2026-09-03 10:00 PDT. See `docs/ROADMAP.md` for the day plan and
`docs/SUBMISSION.md` for what has to exist at the end.

## The loop

This project is built as a closed verification loop. There is an objective
ground truth, so you should almost never be guessing whether a change helped.

```
make corpus   # build labeled adversarial PDFs from corpus/manifest.yaml
make eval     # run the detector over the corpus, write eval/results.json
make check    # determinism: scan twice, assert identical output hash
```

One iteration is: run `make eval`, read the per-class recall table, pick the
single worst attack class, fix only that class, run `make eval` again, confirm
that class improved and no other class regressed. Then commit.

Rules for the loop, in priority order:

1. Never edit `corpus/manifest.yaml` or anything under `corpus/` to make an
   eval pass. The corpus is the ground truth. If a corpus case is genuinely
   wrong, say so explicitly in chat and wait for a human decision before
   touching it.
2. Never add a detector rule that keys off a filename, a seed, a fixture path,
   or any artifact of how the corpus was generated. Rules key off document
   structure only.
3. A change that raises recall on one class while raising the false positive
   rate on `corpus/clean/` is a regression, not a win. Report both numbers
   every time.
4. Commit after every green loop, one class per commit, message format
   `detect(A3): occlusion via post-drawn fill rect`.
5. If two consecutive iterations fail to move the number, stop and write up
   what you tried in `docs/NOTES.md` instead of trying a third variation.

## Architectural invariants

These are load bearing. Breaking one silently is the worst outcome in this repo.

- **The scanner never renders the document to a model.** Verso decides whether
  an agent may read a document. If Verso itself passes untrusted document text
  into an LLM prompt in order to decide, the whole argument collapses. The
  structural layer is pure Python plus deterministic PDF tooling. Nothing in
  `verso/detect/` may import an LLM client. There is a lint check for this.
- **Structural detection is deterministic.** Same bytes in, same findings out,
  same order, every time. `make check` enforces it. Any nondeterminism (dict
  iteration order, timestamps inside findings, unsorted globs) is a bug.
- **The semantic layer is advisory only.** `verso/advisory/` may call a model to
  flag machine-addressed language in visible text. It can raise a finding's
  priority for human display. It can never be the sole reason a document is
  quarantined, and its output never changes the exit code.
- **Original bytes are immutable.** Verso never writes to the input file. The
  sanitized output is a new artifact, and the receipt records the SHA-256 of
  the original.
- **Findings carry coordinates.** A finding without page number and a bounding
  box is not a finding, it is an opinion. The demo depends on pointing at the
  exact spot on the page.

## CLI contract

Build to this interface and keep it stable. The eval harness and the demo both
depend on it.

```
verso scan <path>            # exit 0 clean, exit 2 quarantined, exit 1 error
verso scan <path> --json     # findings as JSON on stdout
verso scan <path> --receipt out.json   # emit a signed refusal receipt
verso sanitize <path> -o <path>        # emit cleaned copy, refuse if unsafe
verso ledger verify <dir>    # verify receipt chain integrity
```

Exit code 2 is the whole product. Anything that wraps Verso, including the
Foxit MCP flow, gates on that exit code.

## Repo map

```
verso/
  ingest/      pdf loading, page rasterization, view construction
  views/       the three views: stream, render, meta
  detect/      structural rules, one module per attack class, NO llm imports
  advisory/    optional semantic pass, llm allowed here only
  receipt/     receipt construction, signing, chaining
  cli.py       the interface above
corpus/
  manifest.yaml   declarative list of attack cases
  forge/          generators, one per attack class
  clean/          unmodified real-world documents, false positive control
  build/          generated, gitignored
eval/
  run.py          scans corpus, writes results.json
  results.json    generated
docs/
```

## Priority when time runs out

Cut from the bottom. This order is deliberate and was decided before the build
started, so do not relitigate it at 2am on the last day.

1. A1 invisible text, A2 off canvas, A3 occlusion detection
2. Corpus with at least four attack classes and ten clean controls
3. `verso scan` CLI with correct exit codes
4. Refusal receipts, single receipt, no chain
5. A7 glyph mapping divergence
6. Receipt chaining and `ledger verify`
7. Sanitize command
8. Advisory semantic layer
9. Web UI

Items 8 and 9 are the first things to go. The demo can be a terminal.

## Things that will waste your time

- Do not build a web UI before the detector works. The demo video shows a
  terminal and a highlighted PDF page, and that is enough.
- Do not try to handle encrypted or malformed PDFs. Out of scope, fail cleanly
  with exit 1 and a clear message.
- Do not chase perfect OCR. The render view only needs to be good enough to
  detect presence or absence of text in a region, not to transcribe it.
- Do not generalize the rule engine. Four hardcoded rule modules that work beat
  a plugin architecture that does not.
