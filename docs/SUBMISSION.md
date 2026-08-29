# Submission

## Tracks

Primary: **Foxit, Your Agent Shouldn't Sign That.** $700 first, $300 second.
Secondary: **Nutrient DWS.** $750 first plus credits, $250 second plus credits.
Also eligible for the **overall prize**, $12,500, judged across all entries.

Foxit is primary because the brief explicitly invites you to argue the boundary
sits somewhere other than where they drew it, and that is exactly the argument.

## Required artifacts

Both tracks want roughly the same package.

- Project name and one line pitch
- Public repository with setup instructions that actually work on a clean machine
- Demo video, two to four minutes, showing it working end to end
- One line on where the sponsor's product does the real work and why

Nutrient additionally requires that DWS is used meaningfully for at least one core
document operation, not a single throwaway call. Extraction on released documents
plus the Viewer for flagged human review satisfies that honestly.

## One line pitch

Verso is a document firewall that inspects a PDF before an AI agent is allowed to
read it, refuses anything containing content a human reader cannot see, and emits
a signed receipt proving the refusal.

## Where the sponsor does the real work

**Foxit.** Their MCP server is the agent being defended. Verso gates it, so the
agent's forty document tools cannot be invoked on bytes that have not cleared the
firewall. Their decision to leave eSign out of the catalog is the right instinct
applied at the wrong end of the pipeline, and this is the argument they asked for.

**Nutrient.** DWS Data Extraction runs on documents Verso releases, and the DWS
Viewer is where a human adjudicates flagged findings with the coordinates overlaid.
Quarantine is precisely the case their brief describes, where a guess is not
acceptable and a human has to be pulled in.

## Demo video beat sheet

Four minutes, and the first fifteen seconds decide whether anyone watches the rest.
No title card, no team introduction, no architecture diagram before the hook.

**0:00 to 0:20. The hook, no narration needed.** A contract on screen. It looks
completely normal. Scroll it. An agent reads it and approves a clause. Cut to the
clause highlighted in the source document, which nobody wrote and nobody can see.

**0:20 to 0:50. Name the problem.** Every document agent has the same shape: read,
extract, decide, act. The industry spent its safety budget on the last step. The
attack does not need the agent to sign anything. It only needs the agent to
believe the document said something it did not.

**0:50 to 1:40. Show the mechanism.** Three views of the same page. Stream, render,
meta. The diff. Show the terminal, `verso scan`, exit code 2, and the overlay PNG
with a red box on page three. Say the word deterministic and say that no model was
asked for an opinion.

**1:40 to 2:20. The corpus.** This is the credibility beat and most teams will not
have one. The generator, the manifest, the recall table with real numbers per
attack class, and the false positive rate on clean documents. Say the number out
loud even if it is not perfect.

**2:20 to 3:00. The receipt.** Show the JSON. Explain that every audit system logs
what an agent did and almost none log what it declined to do. Name R5, escalation
unanswered, and say nobody has it including us, and why that is the class that
actually sinks organizations.

**3:00 to 3:30. Sponsors, briefly.** Foxit MCP gated on exit code. Nutrient
extraction and Viewer on the far side of the firewall.

**3:30 to 4:00. The limit and the ask.** Name attack class A8, semantic injection,
and say plainly that it is not solvable structurally and the advisory layer only
flags it. Then the corpus is public, and here is the link.

Ending on the thing you cannot do is a stronger close than a feature list. It is
also the answer to the question the sharpest judge in the room was already
forming.

## Build story, for the Devpost page

Cover: what the attack surface is and why nobody guards it, why the corpus came
before the scanner, why the detector is not allowed to call a model, what the
recall numbers actually are, and what got cut and why.

Mention the tooling honestly, including Claude Code, and how long it took. Xano's
brief asks for this explicitly and the other judges read it as candor.

## Pre-submit checklist

- [ ] Repo is public and clone-to-run works on a clean machine
- [ ] `make corpus && make eval` reproduces the numbers claimed in the video
- [ ] README has the recall table with the same numbers
- [ ] No API keys anywhere in git history, including the Nutrient campaign
      credentials from the hackathon brief
- [ ] Video is under four minutes and audible
- [ ] Both track submissions filed separately
- [ ] LICENSE present, corpus licensed for reuse
- [ ] One sentence in the README naming what the system cannot detect
