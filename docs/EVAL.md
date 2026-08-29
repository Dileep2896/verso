# Evaluation

The eval is the scoreboard for the build loop. If a change cannot be justified by
a number in this file, it is not a change worth making this week.

## Metrics

**Per-class recall.** Of the injected attacks of class X, what fraction did we
find, matched by page and overlapping bounding box. Position matters: finding
that a document is dirty without finding where is a partial credit at best, and
the demo depends on the coordinates.

**False positive rate.** Of the clean control documents, what fraction produced
any high-severity structural finding. The target is zero and there is no
acceptable nonzero value for the hackathon build. A firewall that cries wolf on a
normal lease is worse than no firewall, because the first thing a user does is
turn it off.

**Determinism.** Scan every corpus file twice, compare output hashes. Binary pass
or fail, no partial credit.

**Localization error.** For matched findings, the IoU between the reported bbox
and the injected bbox recorded in the manifest. Report the median. This catches
coordinate transform drift that recall alone will not.

**Wall clock per page.** Not a judging criterion, but if a scan takes thirty
seconds the demo drags and OCR is the reason. Track it so you notice.

## Report format

`make eval` prints this and writes the same data to `eval/results.json`.

```
class  cases  found  recall   median IoU
A1        30     28   0.933        0.91
A2        30     30   1.000        0.99
A3        30     19   0.633        0.78
A4        30     29   0.967        0.88
A5        30     30   1.000        n/a
-----------------------------------------
clean     12      0   FP rate 0.000
determinism: PASS
```

## Rules for reading it

A single number for the whole system is misleading and you should not compute one.
Attack classes have different difficulties and different real-world frequencies,
and averaging them hides exactly the information you need to pick the next thing
to work on.

Recall on a class with fewer than ten cases is noise. Do not act on it.

A jump in recall paired with any movement in the false positive rate is not a win
until you have looked at which clean document broke and why.

If recall on a class is 1.000 on the first attempt, be suspicious rather than
pleased. It usually means the detector is keying off something the generator does
incidentally rather than something the attack does essentially. The check is to
hand-craft one instance of that attack in a different tool and confirm the
detector still catches it.

## Corpus hygiene

The generators and the detectors must not share code. If both import the same
constant for what counts as an invisible fill colour, the eval is measuring
whether you can read your own constant.

Every generated case records its seed in the manifest, so a specific failing case
can be regenerated exactly while investigating.

Host documents are real. Synthetic single-paragraph PDFs are far easier to scan
than actual contracts with tables, headers, footers, and multi-column layout, and
a corpus of them will produce numbers that collapse the moment a judge drops a
real file on it.

## Honesty in reporting

Report the numbers you have, including the bad ones, in the README and in the
video. A recall table with a weak class on it is more convincing than a
suspiciously flat one, because it demonstrates that the harness measures something
real.

If a class is not implemented, list it as not implemented rather than omitting the
row. The taxonomy has ten classes and the build has five. Saying so is the
difference between a scoped project and an overclaimed one.
