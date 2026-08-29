---
name: receipt-ledger
description: Build and verify Verso's signed refusal receipts. Use when working under verso/receipt/, implementing canonicalization or signing, adding a receipt class, implementing verso ledger verify, or debugging a chain break. Read docs/REFUSAL-TAXONOMY.md first, it is the schema of record.
---

# receipt-ledger

A receipt is evidence, and evidence has different requirements from a log line.
It has to be byte-stable, tamper evident, readable by a person who was not there,
and safe to store even though it contains attacker-controlled text.

`docs/REFUSAL-TAXONOMY.md` holds the eight classes and the schema. It is the
document of record. If code and that file disagree, the file wins.

## Canonicalization is the foundation

Signing requires byte-stable serialization, and every other property depends on
it. Write the canonicalizer once, test it against a fixture, and make it the only
way a receipt is ever serialized.

Rules: keys sorted, no insignificant whitespace, UTF-8, floats rounded to one
decimal, timestamps in RFC 3339 with a `Z` suffix and no fractional seconds.

The one nondeterministic field is `issued_at`, which is why `make check` compares
scan output rather than receipts. Do not try to make receipts deterministic by
freezing the clock, that makes the ledger useless.

## Excerpts are attacker-controlled

The `excerpt` field contains text lifted from a hostile document, and it will end
up in dashboards, log aggregators, and eventually somebody's terminal. Cap it,
flag truncation with `excerpt_truncated`, strip control characters, and never
include the full payload. A receipt about a prompt injection that itself carries
the injection into three more systems is an own goal.

## Keep findings and advisory separate

`findings` drives the decision. `advisory` never does. Two arrays, not one list
with a severity field, because one list is how the advisory layer starts
influencing decisions six commits later without anyone noticing.

Stronger still: compute the exit code before the advisory pass runs. If the
decision is already final when the model is called, the model cannot affect it no
matter what anyone adds later.

## Chaining

`prev` points at the previous receipt id. `chain_hash` is over the canonical
serialization of the current receipt plus `prev`. A ledger with a hole is worse
than no ledger, so `verso ledger verify` exits nonzero on any failure and reports
the first break by receipt id, not just that something is wrong.

Test chain verification against a deliberately tampered ledger, not only a good
one. A verifier that has never rejected anything has not been tested.

## Scope for the hackathon

Verso emits R3, quarantine-refusal, and that is the only class to implement.

R1, R4, R5, R7 exist in the schema and in the taxonomy document as the shape of
the system. Do not build the R5 sweeper. Explaining in the demo why nobody has
escalation-unanswered, and why it is the class that actually sinks organizations
in an audit, is worth more in four minutes than a half-working implementation.

Do not add a receipt class that Verso does not emit and cannot explain. The
taxonomy is the contribution and a padded taxonomy is a weaker one.
