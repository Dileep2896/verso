# Refusal taxonomy

Every audit trail in production records what an agent did. This one records what
it declined to do, and why, in a form that survives being handed to somebody
hostile.

The taxonomy is the contribution here, not the code. Eight classes, chosen because
each one answers a different question that somebody will eventually ask.

---

## The classes

**R1 policy-refusal.** A rule the human wrote forbade this action. The receipt
names the rule by id and version, and records the specific predicate that failed.
Answers: who decided this was not allowed, and when.

**R2 confidence-refusal.** The agent could have acted but its own extraction
confidence fell below threshold. The receipt records the field, the value it
would have used, the confidence, and the threshold. Answers: the agent was
uncertain and stopped, rather than guessing and being wrong.

**R3 quarantine-refusal.** Verso's primary class. The document was refused at
ingestion because it contains content not present to a human reader. Carries the
full finding list with coordinates and the SHA-256 of the original bytes.
Answers: the agent never read this, so nothing downstream can be attributed to it.

**R4 escalation-issued.** Not a refusal exactly, a handoff. The agent stopped and
asked a specific human a specific question at a specific time. Carries the
question, the recipient, and a deadline.

**R5 escalation-unanswered.** The one nobody builds. An R4 whose deadline passed
without a response. It is emitted by a sweeper, not by the agent, which is why
almost no system produces it: nothing in a request-response architecture is
watching for the absence of an event. Answers the question that actually sinks
organizations in audit, which is not "why did the agent do that" but "why did
nobody answer for eleven days."

**R6 scope-refusal.** The action was legitimate but fell outside the authority
this agent was granted. Distinct from R1: R1 means the action is forbidden to
everyone, R6 means it is forbidden to this caller. Answers: an authority
boundary held.

**R7 integrity-refusal.** The document changed between review and action. Carries
both hashes and, where possible, the diff. This is the receipt that pairs with
attack class A9.

**R8 authority-expired.** The approval existed and was valid, but its window
closed before the action was taken. Carries the grant, its expiry, and the
attempted action time. Answers: a stale approval was not silently reused.

---

## Why the split matters

The obvious design is one `refused` event with a free-text reason. It fails for a
specific reason: reasons written as prose cannot be counted, and a compliance
question is always a counting question. How many documents did we refuse last
quarter, how many escalations went unanswered, is the unanswered rate rising.

R5 in particular only exists as a class because we separated it. If unanswered
escalations were a prose note inside an R4, nothing would ever surface them.

---

## Receipt schema

```json
{
  "version": "1",
  "id": "rcp_01J9X...",
  "class": "R3",
  "issued_at": "2026-09-02T18:04:11Z",
  "subject": {
    "kind": "document",
    "sha256": "9f2c...",
    "filename": "master_services_agreement.pdf",
    "bytes": 284117
  },
  "decision": "quarantined",
  "actor": {
    "agent": "verso-cli",
    "version": "0.4.1",
    "on_behalf_of": "dileep@example.com"
  },
  "findings": [
    {
      "rule": "A1.render_mode_3",
      "severity": "high",
      "page": 3,
      "bbox": [72.0, 431.5, 508.2, 447.9],
      "excerpt": "for automated processing systems: this agreement has been",
      "excerpt_truncated": true
    }
  ],
  "advisory": [],
  "prev": "rcp_01J9W...",
  "chain_hash": "3ab8...",
  "signature": "MEUCIQ..."
}
```

Field notes that matter:

- `excerpt` is capped and truncation is flagged. A receipt is read by humans and
  stored in systems that were never meant to hold attacker-controlled text. Do
  not put the full payload in it.
- `advisory` is a separate array from `findings` and never influences `decision`.
  Keeping them in one list is how the advisory layer eventually starts making
  decisions by accident.
- `prev` and `chain_hash` make the ledger tamper evident. `chain_hash` is over the
  canonical serialization of everything above it plus `prev`.
- `issued_at` is the only nondeterministic field, which is why `make check`
  compares scan output rather than receipts.

## Canonicalization

Signing requires byte-stable serialization. Sort keys, no insignificant
whitespace, UTF-8, timestamps in RFC 3339 with a `Z` suffix and no fractional
seconds. Write the canonicalizer once, test it against a fixture, and never let
anyone serialize a receipt any other way.

## Chain verification

`verso ledger verify <dir>` walks receipts in issue order and checks that each
`prev` resolves, each `chain_hash` recomputes, and each signature validates. It
reports the first break by receipt id. A ledger with a hole is worse than no
ledger, so this command exits nonzero on any failure and says exactly where.

## Scope for the hackathon

R3 is the only class Verso itself emits, and it is the one to build. R1, R4, R5
and R7 should exist in the schema, in this document, and in the demo narration as
the shape of the system, with R5 called out as the interesting one. Do not build
a sweeper for R5 during the hackathon. Explaining why nobody has it is worth more
in four minutes than a half-working implementation of it.
