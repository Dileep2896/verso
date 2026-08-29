---
name: corpus-forge
description: Build or extend the labeled adversarial PDF corpus for Verso. Use when writing or fixing a generator under corpus/forge/, adding an attack class to corpus/manifest.yaml, adding host or clean-control documents, or when an eval result suggests a corpus case is mislabeled. Do not use for detector work, that is detect-loop.
---

# corpus-forge

The corpus is the ground truth for every number this project reports. It is also
the artifact most likely to be released and reused after the hackathon. Treat a
mistake here as more expensive than a mistake in the scanner, because a wrong
corpus makes every downstream number a lie.

Read `docs/ATTACK-TAXONOMY.md` before writing any generator. It is the
specification. If a generator and the taxonomy disagree about what a class means,
the taxonomy wins and the generator gets fixed.

## The contract every generator satisfies

```python
def inject(host: Path, payload: str, seed: int) -> Injection:
    """Return the modified PDF bytes plus a ground-truth record."""
```

The `Injection` record carries: attack class id, host document, payload text,
page, bounding box in PDF user space, seed, and a one-line note on the mechanism
used. That record goes straight into the manifest. A generator that cannot report
exactly where it put the payload is not finished, because localization is a
scored metric.

## Non-negotiables

**Generators and detectors share no code.** Not a constants module, not a helper
for colour comparison, nothing. If both sides import the same definition of what
invisible means, the eval measures whether the code can read its own constant.
Duplicate the constant deliberately and leave a comment saying why.

**Seeded and reproducible.** `make corpus` on a clean checkout produces
byte-identical files. Any randomness takes the seed from the manifest.

**Real host documents.** A single-paragraph synthetic PDF is trivially scannable
and produces numbers that collapse on a real contract. Hosts are actual documents
with tables, headers, footers, and multi-column layout. Use at least three
different hosts per attack class so no detector can key off one document's quirks.

**The payload is visible in the file and invisible on the page.** After writing a
generator, verify both halves by hand before trusting it:

```bash
pdftotext -bbox-layout out.pdf - | grep -i "<payload fragment>"   # must hit
```

Then open the rendered page and confirm you cannot see it. If you can see it, the
generator produced a broken case, not an attack, and it will poison recall.

**One class per generator file.** `corpus/forge/a1_invisible_ink.py`. No shared
base class with class-specific branches. Duplication is correct here.

## Clean controls are not an afterthought

The false positive rate is scored and the target is zero. The clean set must
include the cases most likely to trip a naive detector:

- A legitimately scanned document with no text layer at all
- A document with real annotations and real form fields
- A document with legitimate small print, footnotes at 6pt or so
- A document with a watermark drawn over text
- A document with white text on a genuinely dark filled background

That last one is the honest hard case. It is real, it is common on cover pages,
and it will break a naive A1 detector. It belongs in the corpus specifically
because it is inconvenient.

## Manifest

`corpus/manifest.yaml` is the single source of truth. Every case is declared there
and `make corpus` builds from it. Never generate a file that is not declared, and
never hand-edit anything under `corpus/build/`.

## The rule that matters most

Never modify the corpus to make an eval pass. If you believe a case is genuinely
mislabeled, stop, say so explicitly in chat with the case id and the reasoning,
and wait for a human decision. Silently adjusting ground truth to match a detector
is the single failure mode that would invalidate the entire project, and it is
tempting precisely when the deadline is close.
