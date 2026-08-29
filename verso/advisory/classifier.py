"""Classifier behind an interface, with a local deterministic fake.

A2 through A7 are structural; A8 (semantic injection) is fully visible, correctly
rendered text addressed to a machine rather than a human, and cannot be solved
deterministically. The advisory layer flags it and hands it to a person -- it can
raise a finding's display priority, never quarantine on its own.

The model-backed classifier is used only if ANTHROPIC_API_KEY is set and the SDK
is installed; otherwise the local heuristic runs, so the whole system works
offline with no key. Either way, output lands in the receipt's ``advisory`` array
and the exit code was already final before this ran.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

# Phrases that address an automated reader rather than a human. Deliberately
# conservative; this is advisory, not a decision.
_MACHINE_PATTERNS = [
    r"\bfor automated (processing|systems|review)",
    r"\bautomated (processing systems|reviewer|system directive)",
    r"\ba[i1] (assistant|agent|model|system)\b",
    r"\blanguage model\b",
    r"\bignore (all |any )?(previous|prior) instructions\b",
    r"\bpre-?approved\b",
    r"\bproceed to signature\b",
    r"\bdo not (flag|escalate|review)\b",
    r"\bas an ai\b",
    r"\byou (must|should) (approve|comply|proceed)\b",
    r"\bsystem\s*:",
    r"\bmachine reader\b",
    r"\bprocessing pipeline\b",
    r"\bautomated system directive\b",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in _MACHINE_PATTERNS]


@dataclass
class AdvisoryHit:
    page: int
    excerpt: str
    reason: str
    source: str


class LocalHeuristicClassifier:
    source = "advisory-heuristic"

    def classify(self, sentences: list[tuple[int, str]]) -> list[AdvisoryHit]:
        hits: list[AdvisoryHit] = []
        for page, sent in sentences:
            for rx in _COMPILED:
                m = rx.search(sent)
                if m:
                    hits.append(AdvisoryHit(
                        page=page,
                        excerpt=sent.strip()[:160],
                        reason=f"machine-addressed language: '{m.group(0)}'",
                        source=self.source,
                    ))
                    break
        return hits


def get_classifier(config=None):
    """A bring-your-own-key model classifier if configured, else the local heuristic.

    ``config`` may be an ``LLMConfig``, a dict with keys provider/api_key/model/
    base_url (e.g. from the web app), or None to resolve from environment. Any
    failure to build a model client falls back to the offline heuristic so the
    advisory pass never hard-errors.
    """
    from .llm import LLMClassifier, LLMConfig, config_from_env
    cfg = None
    try:
        if isinstance(config, LLMConfig):
            cfg = config
        elif isinstance(config, dict) and config.get("provider") and config.get("api_key"):
            cfg = LLMConfig(
                provider=str(config["provider"]).lower(),
                api_key=str(config["api_key"]),
                model=config.get("model") or None,
                base_url=config.get("base_url") or None,
            )
        else:
            cfg = config_from_env()
        if cfg is not None:
            return LLMClassifier(cfg)
    except Exception:
        pass
    return LocalHeuristicClassifier()
