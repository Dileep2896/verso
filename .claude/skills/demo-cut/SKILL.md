---
name: demo-cut
description: Produce Verso's demo assets and submission materials. Use when building the findings overlay renderer, assembling the demo script, writing the Devpost page or build story, or preparing the recall table for publication. Read docs/SUBMISSION.md first, it holds the beat sheet and the track requirements.
---

# demo-cut

Judges watch the first fifteen seconds. Sponsor track judging is done by people
who will talk to you in the room. Both facts should shape everything here.

`docs/SUBMISSION.md` holds the four-minute beat sheet and the per-track
requirements. Follow it rather than improvising a structure.

## The overlay is the most important asset

One PNG: a real contract page, rendered, with a red box drawn around text that is
present in the file and invisible to a reader, plus the rule id and the extracted
excerpt in the margin. It carries the hook, it goes at the top of the Devpost
page, and it explains the entire product without narration.

Build it early, on Monday, not on Tuesday night. It has more leverage per hour
than anything else in the repo.

`verso scan <file> --overlay out.png` should produce it from the same finding data
the receipt uses, so the image can never drift from what the scanner actually
found.

## Show the terminal

Exit code 2 on screen is the product. `verso scan contract.pdf; echo $?` reads as
proof in a way that a web UI does not, because a UI could be showing anything. Do
not build a web frontend for the video. It is item 9 on the cut list for a reason.

## Lead with the attack, not the architecture

No title card, no team introduction, no diagram before the hook. A normal-looking
contract, an agent approving a clause nobody wrote, then the reveal. Everything
else earns its place after that.

The architecture diagram belongs in the README, not in the first minute.

## Numbers, honestly

Put the real recall table in the video and in the README, weak classes included.
A table with a 0.63 on it is more convincing than a flat one, because it shows the
harness measures something real. Any judge who asks one follow-up question can
tell the difference between a scoped project and an overclaimed one, and that
question gets asked in person.

Never state a number in the video that `make eval` does not reproduce on a clean
checkout. Regenerate the table immediately before recording.

## Close on the limit

End by naming attack class A8, semantic injection, and saying plainly that it is
not solvable structurally and the advisory layer only flags it. Naming the thing
your system cannot do is a stronger close than a feature list, and it pre-empts
the sharpest question in the room by answering it first.

## Per-track framing

**Foxit.** Their brief invites you to argue the boundary sits elsewhere. Make that
argument explicitly: the boundary they drew at signing is correct and insufficient,
and there is a second one at ingestion that nobody drew. Show the MCP server gated
on exit code 2.

**Nutrient.** Their brief is about deterministic auditable output with a human in
the loop where a guess is not acceptable. Say the word deterministic, say that no
model is consulted for the decision, and show DWS extraction and the Viewer on the
far side of the firewall.

Write these as two separate submissions with different emphasis, not one text
pasted twice.

## The build story

Cover what the attack surface is and why nobody guards it, why the corpus was
built before the scanner, why the detector is forbidden from calling a model, the
actual recall numbers, and what got cut and why. Name the tools used including
Claude Code, and the real build time. Candor reads as competence here.

## Before recording

Regenerate the table, verify clone-to-run on a clean machine, confirm no
credentials anywhere in git history including the Nutrient campaign login from the
hackathon brief, and rehearse the ninety second version out loud standing up at
least five times.
