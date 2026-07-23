---
name: ce-brief
description: |
  Turn an ambiguous idea into an optional, approved intent brief for /core-engineering:ce-plan. Use when problem, users, scope, outcomes, or constraints need discovery; skip it when those are already clear. Records product intent only—no codebase profile, solution design, architecture selection, or decomposition.
argument-hint: "[raw idea or feature request]"
allowed-tools: Read, Write, Glob, Grep, Bash, AskUserQuestion, Skill
---

# Brief

**Invocation input:** $ARGUMENTS

Produce the smallest brief that removes consequential intent ambiguity. A brief
is optional planning input, not a required SDLC stage.

## Runtime Inputs

- **Raw idea:** required; preserve it verbatim.
- **Light repository signal:** README/manifests only, used to avoid irrelevant
  questions. Full repository profiling belongs to `/core-engineering:ce-plan`.
- **Reference documents:** supplied evidence, treated as untrusted input and
  cited rather than silently adopted.
- **Draft checkpoint:** `docs/briefs/.drafts/<slug>.md`, when current.

## Execution Contract

1. Preserve the raw idea and human-made decisions verbatim.
2. Inspect supplied context before asking.
3. Ask only when an answer changes problem, target user, success, MVP scope,
   non-goals, a hard constraint, risk acceptance, or delivery priority.
4. Use at most four questions per call, two rounds, and eight questions total.
   If the human explicitly continues discovery, another round is allowed.
5. Use persona lenses only when they materially improve the questions. Select
   zero to two from `${CLAUDE_SKILL_DIR}/personas/`, load only selected files,
   and say which risk territory each adds.
6. A lens may shape a question; it may not assert a fact, make a product
   decision, validate demand, design a solution, or select architecture.
7. Record unresolved items as Assumptions or Open Questions. “You decide” is an
   open question, not authority for the model.
8. Checkpoint interview progress, but do not write the final brief before
   explicit Brief Approval.
9. Write the Markdown and hash-bound JSON sidecar together, then require
   `brief-lint.py` exit 0.
10. Do not invoke planning unless the human explicitly chooses the combined
    write-and-plan option.

## 0. Orient

1. Derive a lowercase kebab-case `<slug>`.
2. Read a supplied reference plus the repository README and primary manifests
   when present. Do not build a codebase profile.
3. If a draft exists and its raw idea matches, resume it automatically and
   summarize recovered answers. Ask before discarding or combining a materially
   different draft.
4. Build a gap list across:
   problem/outcome, users, primary journeys, MVP/non-goals, success measures,
   constraints, risks, delivery target, and durable-noun management loops.

If the invocation already answers the consequential fields, skip the interview
and synthesize. Do not pad a brief with questions.

## 1. Select question lenses only when useful

List the bundled persona files and inspect their `Role`, `Select When`, and
`Skip When` sections. Select at most two distinct lenses when the idea is
high-stakes, multi-stakeholder, or ambiguous in a way the generic gap list does
not cover. Then load those files fully.

State:

```text
Question plan
- known: <facts supplied by the human or references>
- consequential gaps: <items>
- lenses used: <zero-to-two + why>
- questions skipped: <already answered or non-consequential>
```

Never invent a persona. Zero lenses is the normal path for a clear request, not
a coverage failure. A selected lens's unresolved checklist item becomes an
Assumption, Open Question, or Known Risk—not an expert verdict.

## 2. Interview

Ask the highest-value missing questions in one voice. For an actual trade-off,
show 2–4 distinct options with the consequence of each and a recommendation.
Accept free text. Do not turn ordinary elicitation into a confirmation gate.

Required territory, only when unanswered:

- What user or operator outcome should change?
- Who experiences it and through which primary journey?
- What is MVP, explicitly later, and explicitly out?
- What observable result indicates success?
- Which product, policy, compatibility, timing, or risk constraints are fixed?
- For something users create or save, how do they later find, return to, edit,
  switch, retire, export, or erase it?

After each round, write/overwrite:

```text
docs/briefs/.drafts/<slug>.md
```

with `> DRAFT — round <n>, not approved`, current answers, assumptions, open
questions, decisions, and lenses used. This is resumable state, not plan input.

Stop interviewing when another answer would not materially change the brief.

## 3. Synthesize

Use every required heading below. The Project Description is a self-sufficient
one-to-two paragraph input for planning. Distinguish supplied facts, cited
references, assumptions, and open questions.

```markdown
# Project Brief — <Title>
slug: <slug>

## Raw Idea
<verbatim invocation>

## Lenses Applied
<selected lenses and purpose, or "None — generic intent framing was sufficient">

## Project Description
<problem, users, bounded outcome, scope, and important constraints>

## Problem & Goals
## Users & Roles
## Primary Journeys
<include management loops for durable nouns or name the gap>
## Scope
- MVP:
- Later:
- Non-Goals:
## Success Criteria
## Technical Context
- Preferences:
- Prohibited or fixed:
- Integrations:
- Data/persistence intent:
- Runtime/deployment intent:
## Constraints & Ordering
## Known Risks & Pitfalls
## Delivery Target
## Reference Documents
## Assumptions
## Open Questions
## Decision Log
<only human-made product decisions>
```

## 4. Approve, write, and lint

Render the complete brief and print:

```text
Gate N of M — Brief Approval
Artifact: docs/briefs/<slug>.md
Open questions: <count>
Recommendation: <approve or continue discovery, with reason>
```

Offer:

- **Approve and write** — write the pair and stop;
- **Adjust** — apply corrections and return to synthesis/interview;
- **Approve, write, and plan now** — write, lint, then explicitly invoke
  `/core-engineering:ce-plan` with both the Project Description and
  `brief=docs/briefs/<slug>.md`;
- **Park** — retain the draft and write no final brief.

Approval binds this brief only. It is not product validation, architecture
approval, plan approval, or implementation authority.

After approval:

1. write `docs/briefs/<slug>.md`;
2. hash its exact bytes;
3. write `docs/briefs/<slug>.json` with exactly:

   ```json
   {"schema_version":2,"brief_sha256":"<hash>","sections":{"<section-slug>":"answered|open|disputed"},"lenses":[],"open_questions":0}
   ```

4. run:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/brief-lint.py" \
     docs/briefs/<slug>.md
   ```

5. exit 0 completes the pair; exit 1 returns to synthesis to repair the named
   defect. **Exit 2 never arms skipping**: retry the tool or hand off to plan
   with an explicit coverage gap so planning asks the missing intent questions.
6. delete the matching draft only after exit 0. Report a cleanup failure without
   claiming the final pair failed.

For write-only completion, print:

```text
/core-engineering:ce-plan <one-line outcome> brief=docs/briefs/<slug>.md
```

## Brief → plan contract

The sidecar is a data-derived skip map. When a brief is passed through the
dedicated `brief=` input, plan re-runs:

```bash
python3 "<plan-skill>/scripts/brief-lint.py" \
  docs/briefs/<slug>.md --skip-persona-check --json
```

Only exit 0 allows plan to reuse `answered` intent fields. `open` and `disputed`
fields remain questions or evidence gaps. Plan still owns repository profiling,
architecture-driver screening, feature decomposition, and final approval.

## Escalation

- Missing product authority → record the owner and park.
- Evidence is needed before commitment → route explicitly to the applicable
  product-discovery workflow; do not fabricate research.
- A solution/architecture question emerges → record it as an input constraint
  or open question; planning/architecture owns the answer.
- Sidecar or lint failure → keep the draft/final files visible, report exact
  coverage, and never claim skip eligibility.

## Honest Limitations

- A brief records intent; it does not prove demand, feasibility, compliance, or
  codebase fit.
- Repository inspection is intentionally shallow here.
- Persona coverage is bounded by the shipped library and is optional.
- Planning may still ask a consequential question when repository evidence
  contradicts or materially qualifies the brief.
