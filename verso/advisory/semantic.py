"""Advisory pass over VISIBLE text only.

It gathers the text a human actually reads -- stream spans drawn normally, at a
readable size, inside the page -- and never the invisible payloads the structural
layer already found. Those visible sentences are handed to the classifier. The
result is a list of advisory dicts for the receipt's ``advisory`` array.
"""

from __future__ import annotations

import re

from ..models import Views
from .classifier import get_classifier

_MIN_SIZE = 4.0
_INVISIBLE_MODES = {3, 7}
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _visible_text_by_page(views: Views) -> list[tuple[int, str]]:
    crop = {p.index: p.cropbox for p in views.pages}
    buckets: dict[int, list[str]] = {}
    for s in views.stream:
        if s.bbox is None or not s.text.strip():
            continue
        if s.extra.get("render_mode", 0) in _INVISIBLE_MODES:
            continue
        if s.extra.get("effective_size", 99) < _MIN_SIZE:
            continue
        c = crop.get(s.page)
        if c is not None:
            inter = s.bbox.intersection(c)
            if inter is None or inter.area < 0.5 * s.bbox.area:
                continue
        buckets.setdefault(s.page, []).append(s.text)
    sentences: list[tuple[int, str]] = []
    for page in sorted(buckets):
        joined = " ".join(buckets[page])
        for sent in _SENT_SPLIT.split(joined):
            sent = sent.strip()
            if len(sent) >= 12:
                sentences.append((page, sent))
    return sentences


def run_advisory(views: Views, llm_config=None) -> list[dict]:
    sentences = _visible_text_by_page(views)
    classifier = get_classifier(llm_config)
    hits = classifier.classify(sentences)
    return [
        {
            "class": "A8",
            "kind": "semantic-injection",
            "page": h.page + 1,
            "excerpt": h.excerpt,
            "reason": h.reason,
            "source": h.source,
            "advisory_only": True,
        }
        for h in hits
    ]
