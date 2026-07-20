---
name: ce-brief
description: |
  Interview a user about a raw idea via library-selected persona lenses and synthesize a structured brief whose lead section is a self-sufficient Project Description for /core-engineering:ce-plan. Elicits and records intent only — never profiles code, decides, or decomposes.
  Triggers: shape a raw idea or thin feature request into planning input. Feeds /core-engineering:ce-plan, which does the codebase-grounded decomposition.
argument-hint: "[raw idea or feature request]"
allowed-tools: Read, Write, Glob, Grep, Bash, AskUserQuestion, Skill
---

# Brief

**Invocation input:** Raw idea: $ARGUMENTS


Turn a raw idea into a structured brief that the `plan` stage can consume
without re-discovering intent. This skill **elicits and records** — it does not
decide product questions, profile the codebase, design a solution, validate the
idea, or decompose work.

This skill is a **thin orchestrator**. `SKILL.md` (this file) holds the Execution
Contract, the invariant, and the stage map. The persona **lenses** that shape the
interview live one-per-file under `${CLAUDE_SKILL_DIR}/personas/`; you load a
lens file **only when you select it** (Stage 0.5) — never all up front, and you
**never invent a persona** that is not in that library.

**The persona lens files named below are bundled in this skill's own directory.** Read each at `${CLAUDE_SKILL_DIR}/personas/<lens>.md` — `${CLAUDE_SKILL_DIR}` is the environment variable that resolves to this skill's directory regardless of the current working directory. Resolve it once if needed (`ls "${CLAUDE_SKILL_DIR}/personas"`) and read each lens by its resulting absolute path; **never load a companion file by bare name** — in an installed plugin the working directory is the user's project, so a bare name finds nothing and triggers a filesystem search.

> **Optional upstream:** a separate, evidence-bound **ce-market-scan** skill
> (in the companion `product-discovery` plugin — source + date, three-state
> evidence, unverified items labeled) may be composed
> **before** `/core-engineering:ce-brief`. It is **not** part of this skill; if such a research doc
> exists, treat it only as an input Reference Document. Do not perform or fabricate
> market research here.

## Runtime Inputs

- **Raw idea (required):** from the invocation or the user's request. If
  empty, ask once in a short prompt. Do not invent an idea.
- **Light repo signal (auto, optional):** a cheap glance at manifests/README to
  detect greenfield-vs-brownfield and primary stack — used only to tailor
  questions and to help select lenses, never written as a codebase profile.
- **Upstream research doc (optional):** a market-scan artifact produced by the
  separate upstream skill, if the user supplies one. Recorded as a reference;
  its claims are not re-asserted by this skill.
- **Existing draft (auto, optional):** a `docs/briefs/.drafts/<slug>.md`
  checkpoint left by an interrupted earlier run. Detected in Stage 0 and offered
  as a resume — never silently reused and never silently discarded.

## Execution Contract

Follow the workflow in order. Do not skip the meta-prompt, the reasoning blocks,
or the invariant. In particular:

1. Capture the raw idea **verbatim** into the brief; never fabricate intent.
2. **Run the Stage 0.5 meta-prompt before interviewing.** Read the raw idea + repo
   glance, classify domain / project type / stakes, **select 2–4 persona lenses
   from the library** under `${CLAUDE_SKILL_DIR}/personas/`, and assemble a
   deduplicated, prioritized question plan. Load only the selected lens files
   (progressive disclosure); never invent a persona.
3. Ask **grouped** questions (≤4 options per AskUserQuestion call). Precede the
   meta-prompt and **every** lens-round with a **reasoning block**: the driving
   lens, what is known, what is ambiguous, why these questions matter. **No silent
   caps** — if you select, drop, deepen, or skip a lens or round, say so and name
   what was dropped.
4. Treat the **~5 round / ~20 question** budget as a **triage cap**, not a quota:
   select the highest-value questions across the selected lenses, deepen only where
   stakes or uncertainty are high, and stop early when the brief is sufficient.
5. If a lens is **dropped** or a round **skipped**, state it and log the skipped
   territory as **Open Questions** — never leave a gap silent.
6. **Honor the invariant** (below): a lens may shape *what* is asked and *what* risk
   is surfaced; it may **never** decide, design, validate, or assert. Every
   persona-surfaced item routes only to **Assumptions**, **Open Questions**, the
   **Known Risks & Pitfalls** section, or the **Decision Log** — never to a new
   expert-asserted-facts bucket.
7. Treat "unknown / you decide" as a valid answer → record it as an **Open
   Question**, never as a decision the tool makes.
8. Mark every gap as an explicit **Assumption** or **Open Question** — no invented
   details.
9. Record product/scope decisions the human makes **verbatim** in the Decision
   Log. The human owns judgment.
10. **Never write the final brief before Brief Approval** (Stage 3). The one
    exception is the per-round `docs/briefs/.drafts/<slug>.md` **draft
    checkpoint** — a crash-resume artifact, never the brief and never a plan
    input; the dot-directory plus the DRAFT header keep `/core-engineering:ce-plan` from ever
    reading it (its `brief:` channel takes `docs/briefs/<slug>.md` only).
11. **Never launch /core-engineering:ce-plan** without an explicit user choice.
12. The synthesized **Project Description** must stand alone as plan's
    required input.

## Two-Surface Rendering

Render long context, the reasoning blocks, and the full brief as Markdown in the
conversation. Reserve AskUserQuestion for the compact question + up to 4 options
only; take open-ended answers as free text in the conversation.

---

## Stage 0 — Seed & Orient

1. Record the raw idea verbatim.
2. Cheap repo glance (Glob/Grep on manifests + README) → greenfield vs brownfield,
   primary language/framework. Do **not** build a full profile.
3. If the user supplied an upstream market-scan doc, note it as a Reference
   Document. Do not validate or extend it here.
4. Restate your understanding back to the user as findings, not verdicts:
   "Here is what I think you want to build; correct anything wrong." Derive a
   provisional lowercase, filesystem-safe `<slug>` from the most specific noun
   phrase.
5. **Resume check.** Look for `docs/briefs/.drafts/<slug>.md`. If it exists, its
   `> DRAFT — round <n> …` header records the last completed interview round
   `<n>`; present the **resume gate** below *before* re-interviewing — never
   silently reuse or silently overwrite a draft. If no draft exists, skip
   straight to Stage 0.5.

### Resume Gate

**Gate 1 of 2 — Resume or start fresh.** This gate fires **only when a draft
exists**; when it does, `M = 2` for this run and Stage 3's approval becomes
*Gate 2 of 2*. With no draft, this gate never fires and approval is the sole
*Gate 1 of 1* (the interview rounds in between are elicitation, not decision
gates). Render what the draft already holds — rounds completed, `Lenses Applied`,
which sections are filled — as Markdown first, then ask with each option carrying
its consequence (HITL Gate Standard R1):

- **Resume from round `<n>`** → reload the draft's filled sections and recorded
  lenses and continue the interview at round `<n+1>`; nothing already answered is
  re-asked.
- **Start fresh** → **deletes the draft** and restarts the interview from round 1;
  the earlier draft's answers are gone.
- **Abort** → stop now, write nothing, **leave the draft in place** so a later
  `/core-engineering:ce-brief` on the same idea can resume it.

## Stage 0.5 — Meta-Prompt: Select Persona Lenses

Before interviewing, decide **which lenses** will shape the questions. This is a
single planning step, not an interview round.

1. **Classify the idea** from the raw idea + repo glance:
   - **domain** (e.g. fintech, healthcare, devtool, consumer, internal tooling, data/ML),
   - **project type** (greenfield service, brownfield feature, integration, migration, UI app, CLI/library, platform),
   - **stakes** (regulated/safety/money/PII → high; reversible internal tool → low).
2. **Survey the library.** List the persona files under
   `${CLAUDE_SKILL_DIR}/personas/`. For each, read **only** its `## Role`,
   `## Select When`, and `## Skip When` sections to judge fit — do **not** load the
   full file yet.
3. **Select 2–4 lenses** whose `Select When` signals match and whose `Skip When`
   signals do not dominate. Prefer breadth of distinct risk coverage over piling on
   overlapping lenses. **The decided range is 2–4 (Decision 2).** Two named
   **exceptions** to that range are permitted, and each must be logged as a
   deliberate deviation in the Lens-Selection reasoning block **and** in the brief's
   `Lenses Applied` section:
   - **Under-selection (fewer than 2):** allowed only when the idea is genuinely
     narrow and a single lens covers it — record it as a deliberate
     under-selection with the reason.
   - **Zero fitting lenses:** allowed only when *no* library lens fits; fall back to
     the generic spine per step 4 and say so explicitly.
   Never silently fall outside the range.
4. **Load the selected lenses on demand.** Now read each selected file in full
   (Question Bank, Must-Surface Checklist, Boundary). **Never invent a persona** or
   a question theme that is not in the library; if no lens fits, fall back to the
   generic Problem / Users / Scope / Technical / Constraints spine in Stage 1 and
   **say so explicitly** as the zero-lens exception in step 3. (The library is small
   and growing — see Honest Limitations — so a thin-library run that finds only one
   fitting lens, or none, is expected; handle it via the named exceptions above, not
   silently.)
5. **Assemble and DEDUP a tailored plan.** Merge the always-ask questions of the
   selected lenses, drop duplicates and near-duplicates (keep the sharper phrasing),
   lightly tailor each surviving question to the specific idea, and **prioritize**
   into a small set of sequenced rounds — one round per driving lens, highest-value
   first.
6. **Print a Lens-Selection reasoning block** (Markdown, two-surface). It must name:
   - the classification (domain / type / stakes),
   - the lenses **selected** and the matching signal for each,
   - the lenses **considered and dropped** and the `Skip When` reason for each,
   - any **named range exception** taken (under-selection or zero-lens fallback) and
     its reason,
   - the rough round plan and the deduped question count.

   This block exists so selection is **reviewable and reproducible** — **no silent
   caps**. Loading is on demand; selection is from the library only.

### The Invariant

A persona lens may shape **what** is asked and **what** risk is surfaced. It may
**never** decide a product question, design a solution, validate the idea, or
assert a fact. The interview stays **single-threaded and sequenced** — lenses are
rounds in **one voice**, not parallel interrogators. Every item a lens raises lands
in **Assumptions**, **Open Questions**, the **Known Risks & Pitfalls** section, or
the **Decision Log** (a human-made decision, verbatim). There is **no
expert-asserted-facts bucket**. If a lens is
tempted to answer instead of ask, its own `Boundary` line forbids exactly that
over-reach.

## Stage 1 — Structured Interview (Sequenced Lens-Rounds)

Run the rounds assembled in Stage 0.5, **in one voice**, one driving lens per round,
highest-value first. Before each round, print a **reasoning block** naming the
**driving lens**, what is known, what is ambiguous, and why these specific questions
matter for planning. Skip questions already answered by the idea, repo glance, or
research doc — and **say what you skipped**. For any question that is a genuine
**tradeoff** (an MVP-scope cut, a stack commitment), carry the **consequence in each
option's text** — what choosing it commits the brief to (HITL Gate Standard
R1) — so the choice is decidable in the dialog. And surface **"I don't know / you
decide"** as an explicit option (Execution Contract item 7), routed to an Open
Question — never an answer the tool invents.

The selected lenses replace fixed rounds, but they still cover the core spine —
**Problem & Users**, **Scope & Journeys**, **Technical Context**, **Constraints &
Risks**. Treat that spine as required *territory* (a dropped lens must still leave
its territory as Open Questions), while each lens decides the *emphasis* and the
*sharp questions* within it. When no lens fits a part of the spine, ask the plain
spine questions directly.

Within **Scope & Journeys**, treat the *durable-noun lifecycle* as required territory: for any entity the idea has a user create, save, or accumulate, surface — in **one grouped prompt, intent-only** — how they later **find, return to, edit, and switch between** instances. An unanswered loop becomes an **Open Question** (`return-to-manage loop for <noun> not stated`), never a silent create-only default.

**Triage, do not quota.** The ~5 round / ~20 question budget is a ceiling:
- pick the **highest-value** questions across lenses; do not pad to fill it,
- **deepen** a lens with a follow-up only where stakes or uncertainty are high,
- if you **drop** a lens or **skip** a round, state it and log its territory as
  **Open Questions**.

After each lens-round, run that lens's **Must-Surface Checklist**: anything still
unresolved becomes an **Assumption** or **Open Question** (findings, not verdicts).

**Checkpoint each round.** Immediately after a lens-round's checklist,
**write/overwrite `docs/briefs/.drafts/<slug>.md`** — the Brief Template below
with every section filled *so far*, topped by a
`> DRAFT — round <n> of interview, not approved` header (`<n>` = rounds
completed). This is a crash-resume checkpoint only: the dot-directory and the
DRAFT header keep it from ever being read as a brief or a `/core-engineering:ce-plan` input, so an
interrupted run degrades to *resume-from-round-`<n>`* instead of total loss.

If a first synthesis reveals blocking ambiguity, run one optional follow-up round
(2–4 questions) within the cap. Otherwise proceed.

## Stage 2 — Synthesize the Brief

Compose the artifact using the template below. Write the **Project Description**
as a tight 1–2 paragraph statement that is self-sufficient as plan input,
then fill the structured sections. Push every gap into Assumptions or Open
Questions. **Route every persona-surfaced item to exactly one of Assumptions,
Open Questions, the Known Risks & Pitfalls section, or the Decision Log** — never
restate a lens's hypothesis as an asserted fact in any other section.

## Stage 3 — Brief Approval → Write & Handoff

1. Render the complete brief in the conversation.
2. **Gate 2 of 2 — Brief Approval** (*Gate 1 of 1* when no draft was resumed this
   run — see the Resume Gate for how `M` is computed). Ask the user to choose —
   label each option by its consequence (HITL Gate Standard R1); `Discard` is
   destructive, so say so:
   - **Approve & write** → write `docs/briefs/<slug>.md`, **delete the
     `docs/briefs/.drafts/<slug>.md` draft**, and **stop here**; you run
     `/core-engineering:ce-plan` yourself later when ready.
   - **Adjust** → return to Stage 1 with their corrections; **the final brief is
     not written yet** — the draft keeps absorbing each further round.
   - **Approve, write & plan now** → write the brief, **delete the draft**, then
     **immediately launch the full
     `/core-engineering:ce-plan` decomposition interview** (the heavier, multi-gate workflow) — invoking the
     `ce-plan` skill, passing **two distinct inputs**:
     1. the **Project Description** as plan's required free-text input, and
     2. the brief as a **dedicated, named brief input** — `brief: docs/briefs/<slug>.md`
        — so plan's Stage 1.4 brief-aware step can map-and-skip against it
        (see **The Brief → Plan Seam** below).
     The brief travels through this **dedicated `brief:` channel**, *not* the
     project-wide Reference Documents list — that generic list only validates and
     auto-loads paths at spec time and would **not** arm the skip. (The brief may
     *additionally* be listed as a reference doc if the user wants it auto-loaded
     downstream, but that listing is never what drives the skip.)
   - **Discard** → **delete the `docs/briefs/.drafts/<slug>.md` draft; no brief is
     written.** (No final brief is produced — but because every round was
     checkpointed, the destructive scope is just the draft file, not an
     unrecoverable 20-question interview.)
3. **On any write approval, emit the sidecar and lint the pair.** After writing
   `docs/briefs/<slug>.md`, also write `docs/briefs/<slug>.json` —
   `{"schema_version": 1, "sections": {"<section-slug>": "answered"|"open"|"disputed"}, "lenses": [<applied lenses>], "open_questions": <N>}`
   — one entry per Brief-Template section (unresolved → `open`; a claim the code
   may contradict → `disputed`). This sidecar arms `/core-engineering:ce-plan` Stage 1.4's skip
   **from data** rather than prose (see **The Brief → Plan Seam**), so run
   `python3 "${CLAUDE_SKILL_DIR}/scripts/brief-lint.py" docs/briefs/<slug>.md`
   and render its verdict in this gate: **PASS** → hand off; **hard FAIL (exit
   1)** → return to Stage 2 and fix the named sections; **exit 2** → the lint
   could not run — degrade loudly to the manual approval self-attestation.
4. On a write-only approval, print the exact next skills and note the brief path,
   so the brief is handed off through the dedicated channel rather than as a loose
   reference:
   `/core-engineering:ce-plan <one-line description> brief=docs/briefs/<slug>.md`

---

## Brief Template

```text
# Project Brief — <Title>
slug: <slug>

## Raw Idea
<verbatim user input>

## Lenses Applied
<personas that ran (e.g. solutions-architect, business-analyst) + personas considered and dropped with the one-line reason (e.g. sparring-partner — premise looked solid); record any named range exception taken (under-selection <2, or zero-lens generic-spine fallback) and its reason>

## Project Description
<synthesized 1–2 paragraphs — the required input for /core-engineering:ce-plan>

## Problem & Goals
## Users & Roles
## Primary Journeys
<forward paths; and for each durable noun the user creates/saves, its management loop (find · return · edit · switch) — or that loop as an Open Question>
## Scope
- MVP:
- Later:
- Non-Goals:
## Success Criteria
<observable outcomes; phrased to seed downstream acceptance criteria>
## Technical Context
- Preferred stack:
- Forbidden / constrained:
- External integrations:
- Data & persistence:
- Deployment / runtime target:
## Constraints & Ordering
## Known Risks & Pitfalls
## Delivery Target
## Reference Documents
## Assumptions
## Open Questions
## Decision Log
<product decisions the human made during intake, verbatim>
```

## The Brief → Plan Seam

This section describes the **contract the brief offers** to `/core-engineering:ce-plan` — the inputs
this skill supplies and the skip behavior the plan side is **expected to perform**
once it implements the matching step. It does **not** assert that `/core-engineering:ce-plan` performs
that skip today: stating a skip the receiving layer silently fails to do would
itself be a silent cap. The contract is live only when both halves ship.

The brief carries **intent**: problem, users, journeys, scope, success criteria,
stack preferences, integrations-as-intent, constraints, risks, pitfalls,
references. It does **not** carry codebase-grounded answers.

`/core-engineering:ce-plan` owns the **codebase-grounded residue**: the nine-dimension profile,
brownfield friction, existing-surface extend-vs-isolate, foundations forced by
current code, ordering forced by hot files, migration against real data surfaces.

**The offered contract.** When a brief is supplied through the dedicated `brief:`
input, `/core-engineering:ce-plan` Stage 1.4 is **expected to**: map the brief's sections onto its
decomposition question list, **skip the questions the brief already answered**, ask
only the codebase-grounded residue plus the brief's Open Questions that affect
decomposition, and **state which questions it skipped because the brief answered
them**. The brief therefore *reduces* the `/core-engineering:ce-plan` interview without *replacing* it.

**This half supplies the inputs that make that skip possible** — a self-sufficient
Project Description, sectioned intent that maps cleanly onto the plan's
decomposition questions, and an explicit Open Questions list flagging what is still
undecided. **The matching plan-side step ships alongside this skill** — `plan`
Stage 1.4's Brief-Aware Skip Contract reads the `brief:` input and prints its skips
— so the seam is live when both are present. The skip arms **only** through the
dedicated `brief:` channel: pass no brief and `/core-engineering:ce-plan` simply re-asks — no silent
skip occurs. This skill's output alone (a brief left unpassed) does not arm it.

## Escalation

If the idea needs evidence before commitment, route to `/product-discovery:ce-market-scan` or
`/product-discovery:ce-idea-score` (both in the companion `product-discovery` plugin — install it if
not present). If the user is ready to decompose, hand off to `/core-engineering:ce-plan` with the
brief path. If a product decision blocks the brief, record it as an Open Question or
Decision Log entry rather than deciding it here.

## Honest Limitations

- **No codebase profiling** — plan Stage 1.2 does that; the repo glance
  here only tailors questions and lens selection.
- **No deciding, designing, validating, or decomposing** — it surfaces options and
  records the human's choice; plan and the spec stages own the rest.
- **Persona coverage is bounded by the library** under
  `${CLAUDE_SKILL_DIR}/personas/`, which is **small and growing** (today it ships a
  limited set of lenses, not exhaustive domain coverage). Lenses are selected,
  lightly tailored, and never invented; a risk no library lens is primed to surface
  can be missed. When fewer than two lenses fit, or none do, the run takes a **named
  range exception** (Stage 0.5 step 3) and falls back toward the generic spine —
  and says so; it never silently drops below the decided 2–4 range.
- **Lenses shape, never assert** — persona lenses shape questions and surface risk
  only; by the invariant they never assert facts, so the brief contains intent and
  findings, not expert verdicts.
- **Reduces, never eliminates the plan interview** — a brief hands off via the
  **Brief → Plan Seam** above, and codebase-grounded questions still arise
  downstream in `/core-engineering:ce-plan`.
- **The Brief → Plan skip is a two-part contract, not a guarantee from this skill.**
  This skill supplies the inputs through a dedicated `brief:` channel; the actual
  skip is performed by `plan` Stage 1.4's Brief-Aware Skip Contract (which
  ships alongside it). When no `brief:` argument is passed, `/core-engineering:ce-plan` re-asks normally
  — nothing is silently skipped, and this skill does not claim otherwise.
- **No market research** — an upstream evidence-bound research skill (composed
  before `/core-engineering:ce-brief`) is the place for that, and its output is consumed here only as a
  labeled Reference Document.
