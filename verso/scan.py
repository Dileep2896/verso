"""The scan pipeline: ingest -> views -> detect -> decide -> (advisory).

The decision (and therefore the exit code) is computed from the structural
findings *before* the advisory pass runs. This is the load-bearing guarantee:
if the decision is already final when a model is (optionally) consulted, the
model cannot change it, no matter what anyone later adds to the code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .detect import run_detectors
from .ingest import load
from .models import Finding, PageInfo, SEV_HIGH
from .serialize import finding_dict, output_hash
from .views import build_views

DECISION_CLEAN = "clean"
DECISION_QUARANTINED = "quarantined"

EXIT_CLEAN = 0
EXIT_ERROR = 1
EXIT_QUARANTINE = 2


@dataclass
class ScanResult:
    path: Path
    sha256: str
    filename: str
    size: int
    n_pages: int
    revisions: int
    findings: list[Finding]
    decision: str
    advisory: list[dict] = field(default_factory=list)
    pages: list[PageInfo] = field(default_factory=list)

    @property
    def high_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == SEV_HIGH]

    @property
    def exit_code(self) -> int:
        return EXIT_QUARANTINE if self.decision == DECISION_QUARANTINED else EXIT_CLEAN

    @property
    def output_hash(self) -> str:
        return output_hash(self.findings, self.decision)

    def subject(self) -> dict:
        return {
            "kind": "document",
            "sha256": self.sha256,
            "filename": self.filename,
            "bytes": self.size,
            "pages": self.n_pages,
            "revisions": self.revisions,
        }

    def to_dict(self) -> dict:
        return {
            "subject": self.subject(),
            "decision": self.decision,
            "findings": [finding_dict(f) for f in self.findings],
            "advisory": self.advisory,
        }


def scan(path: str | Path, with_render: bool = True,
         with_advisory: bool = False, advisory_config=None) -> ScanResult:
    doc = load(path)
    try:
        views = build_views(doc, with_render=with_render)
        findings = run_detectors(views)
        decision = (
            DECISION_QUARANTINED
            if any(f.severity == SEV_HIGH for f in findings)
            else DECISION_CLEAN
        )
        # ---- decision is now FINAL. Advisory runs after, cannot change it. ----
        advisory: list[dict] = []
        if with_advisory:
            try:
                from .advisory import run_advisory
                advisory = run_advisory(views, llm_config=advisory_config)
            except Exception:
                advisory = []

        return ScanResult(
            path=Path(path),
            sha256=doc.sha256,
            filename=doc.filename,
            size=doc.size,
            n_pages=doc.n_pages,
            revisions=doc.revisions,
            findings=findings,
            decision=decision,
            advisory=advisory,
            pages=list(doc.pages),
        )
    finally:
        doc.close()
