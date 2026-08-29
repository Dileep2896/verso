---
name: detect-loop
description: Run the closed build-verify-fix loop on Verso's structural detectors. Use when writing or improving anything under verso/detect/ or verso/views/, when make eval shows a weak attack class, when a clean control produces a false positive, or when make check fails on determinism. Do not use for corpus changes, that is corpus-forge.
---

# detect-loop

This project has an objective scoreboard, so you should almost never be guessing
whether a change helped. One iteration, start to finish:

```bash
make eval                 # read the per-class recall table
# pick the single worst class
# fix only that class
make eval                 # confirm it improved and nothing else moved
make check                # determinism gate
git commit                # detect(A3): occlusion via post-drawn fill rect
```

One class per iteration, one commit per green loop. Do not fix three classes at
once, because when the table moves you will not know which change did it and you
will not be able to revert cleanly.

## Reading the table

Recall and false positive rate are reported together and read together. A class
going from 0.63 to 0.90 while the clean FP rate goes from 0.000 to 0.083 is a
regression, not progress. State both numbers out loud every iteration.

Recall on a class with fewer than ten cases is noise. Do not act on it, add cases
first.

Recall of 1.000 on the first attempt is a warning, not a success. It usually means
the detector is keying off something the generator does incidentally rather than
something the attack does essentially. Verify by hand-crafting one instance of
that attack in a different tool and confirming the detector still fires.

## Rules that hold regardless of deadline pressure

**Never edit the corpus to make an eval pass.** If a case looks genuinely wrong,
say so in chat with the case id and stop. See corpus-forge.

**Never key a rule off a filename, a path, a seed, or anything about how the
corpus was generated.** Rules key off document structure. If a rule would not fire
on the same attack delivered by a stranger's email attachment, it is not a rule.

**No model calls under `verso/detect/`.** Verso decides whether an agent may read
a document. A detector that feeds untrusted document text to a model to make that
decision has reproduced the vulnerability it exists to prevent. There is a lint
check. Do not work around it.

**Prefer the structural signal over the render diff.** If text was drawn with
`3 Tr`, you know it is invisible without asking OCR to agree. Record both signals
in the finding but let the deterministic one drive the decision. OCR is the only
part of this system that feels nondeterministic and the fewer decisions resting on
it alone, the better the demo holds up.

## When determinism fails

`make check` failing is always one of these, in rough order of likelihood:
unsorted dict or set iteration, a timestamp or absolute path inside a finding,
unsorted glob results, unpinned tesseract config, float formatting drift.

Findings sort by page, then bbox top, then bbox left, then rule id. Round
coordinates to one decimal at serialization. Fix the cause, never paper over it by
loosening the check.

## Build order

Ascending difficulty, so the loop stays green as long as possible:

A2 off canvas, then A1 invisible ink, then A4 microtype, then A5 metadata, then
A3 occlusion. A7 glyph divergence only after all five are solid, since it is the
best demo moment and the worst use of time if the core is unfinished.

## Every finding carries coordinates

Page number and bounding box are mandatory. A finding without them is an opinion,
not evidence, and the demo depends on drawing a box on the page. If a rule cannot
localize, it is not done.

## When to stop

If two consecutive iterations fail to move the number, stop. Write what you tried
in `docs/NOTES.md` and either move to the next class or raise it in chat. A third
variation on a failing approach is how a day disappears, and there is a cut list
in `CLAUDE.md` for exactly this situation.
