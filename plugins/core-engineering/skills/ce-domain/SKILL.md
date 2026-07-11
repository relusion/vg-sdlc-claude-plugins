---
name: ce-domain
description: |
  Onboard a person into the business domain a codebase encodes — the product's context, the actors and roles it serves, the domain nouns and their lifecycles, the processes and journeys it supports, the business rules and invariants it enforces, and the ubiquitous language it is built around — as a paced, evidence-grounded interactive walkthrough. Every claim cites file:line or a named artifact and carries its evidence type (recorded / enforced / inferred); draws on the plan tree's recorded human claims where one exists (the brief's users and roles, the journey map, the decisions ledger, EARS criteria, ADRs) and on code-derivable domain signal where it does not (entities, state enums and their transition guards, validation rules, authorization roles, jobs, integrations). What a repository cannot evidence — why a rule exists, the market context, the human process around the software — is registered as a known unknown and handed to a human, never narrated. Read-only on code; teaches, never patches.
  Triggers: onboard me into the domain / what business does this code encode / teach me the domain model, the actors, the vocabulary. For the as-built implementation (architecture, decisions, gotchas, verified behavior) use /ce-onboard; for a one-off code question use /ce-ask; for user-facing docs use /ce-ship-document.
argument-hint: "[path | subdomain | plan-slug]"
allowed-tools: Read, Write, Glob, Grep, Bash, AskUserQuestion, Skill
---

# Domain

**Invocation input:** Scope to teach (optional): $ARGUMENTS


Teach a person the **business domain a codebase encodes** — the layer above the
implementation: the context the product exists in, the actors and roles it serves, the
domain nouns and their lifecycles, the processes and journeys it supports, the business
rules and invariants it enforces, and the ubiquitous language it is built around. Where
`/ce-onboard` transfers the **as-built code** to its next maintainer, this tool transfers
the **world that code serves** — to an engineer new to the product, a PM, an analyst, or
anyone who must speak the product's language before they touch a file.

The workflow is **read-only on code and existing artifacts**. It teaches; it never
patches code, edits specs, or modifies any other artifact. The only thing it may write is
one optional, consented **domain primer** — a team-internal document, never the
user-facing docs that `/ce-ship-document` owns.

Its epistemic contract is the load-bearing part: **a codebase is a witness to its domain,
not the domain itself.** Code and recorded artifacts can evidence *what* the system
enforces, *who* it distinguishes, and *what* it names. They cannot evidence *why* a rule
exists, what market or regulation shaped it, or what human process wraps the software.
This tool teaches the first category with citations — and hands the second to a human as
a **Known-Unknowns Register**. It never narrates the unevidenced.

Like `/ce-onboard`, it **owns a curriculum and drives it** — the load-bearing distinction
from `/ce-ask`. Reactive, ad-hoc questions mid-session are answered briefly and routed
back to `/ce-ask`, so the tutor's agenda stays intact.

## Runtime Inputs

- **Scope (optional):** a path or module (narrows the sweep to one subdomain), or a plan
  slug (prefers that plan tree's recorded claims). Without one, the scope is the whole
  repository. Never guess a narrower scope silently.
- **The repository:** the current working directory.
- **Recorded human claims (read-only, harvested when present):** `docs/briefs/<slug>.md`
  (**Users & Roles**, **Primary Journeys**, **Success Criteria**, the verbatim **Decision
  Log**); the plan tree `docs/plans/<slug>/` — `feature-plan.md` (Overview, the verbatim
  Original Project Description, the **Journey Map**, the **Durable-State Closure** table),
  `shared-context.md` (the **Resolved Project Decisions** ledger), `specs/<id>/ce-spec.md`
  (**EARS acceptance criteria**), `threat-model.md` (trust boundaries, data-classes),
  `interaction-contract.md` (protocol invariants); plus repo-wide `docs/adr/` (Nygard
  ADRs) and `docs/decisions/<slug>/` snapshots — and any hand-written ADRs or docs a
  non-pipeline repo carries. **When an artifact is absent, the tutor teaches the
  absence — it never invents a finding from a missing file.**
- **Code-derived domain signal (always, plan or no plan):** entities and models, state
  enums and their transition guards, validation rules and constraints, authorization
  roles and policies, routes and handlers, background jobs and schedules, integrations
  and external clients, migrations, notification templates and UI copy, test names and
  assertions, README and docs.

## Execution Contract

0. **Session write lease (structural, first act).** `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --set --skill ce-domain --allow 'docs/domain/**'` — only the optional domain primer is writable, and the write guard now enforces that. Last act: `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --restore-baseline`. A denied write mid-session means this contract and the action disagree — reconcile; never edit or delete the lease to proceed.
1. **Never patch code, edit specs, or modify feature files.** Teach, do not fix. The
   `/ce-domain` skill's `allowed-tools` deliberately exclude `Edit`.
2. **Read-only on existing artifacts.** Write only the one optional domain primer
   (Stage 3), and only with consent.
3. **Every claim cites `file:line` or a named artifact.** No citation, no claim. Show
   evidence over paraphrasing it — quote the enforcing lines, the enum, the brief's own
   words. (The `ask` grounding contract, reused verbatim.)
4. **Every taught claim carries its evidence type** — `recorded`, `enforced`, or
   `inferred` (the Three-State Evidence rule below). An untyped claim is a bug in the
   session.
5. **The domain floor — never narrate the unevidenced.** *Why* a rule exists, the market
   or regulatory context, and the human process around the software are taught **only**
   when a recorded artifact states them. Otherwise they enter the Known-Unknowns
   Register as questions for a human. "Presumably…" is a forbidden move.
6. **The tutor owns the agenda.** It proposes the next lesson and asks a comprehension
   check; it does not wait to be asked. Ad-hoc reactive questions are answered briefly,
   then explicitly routed to `/ce-ask`.
7. **Adaptive depth, never silent.** The walk adjusts to the audience and their answers,
   but any narrowing of scope is stated — no silent caps on what was skipped.
8. **Domain audience.** The output explains *the world the code serves* — categorically
   not the implementation walkthrough `/ce-onboard` owns. When the learner asks "but how
   is this built?", answer in one cited line and route to `/ce-onboard`.

## Three-State Evidence — every claim is typed

| Tag | Means | Example |
|---|---|---|
| `recorded` | **A human wrote it down** — the brief, an ADR, an EARS criterion, README/docs, a code comment. | *"The brief names three roles: buyer, seller, moderator"* — cited to the brief. |
| `enforced` | **The code makes it so** — a transition guard, a validator, a DB constraint, an authz check. | *"An order cannot ship before payment"* — cited to the guard that rejects it. |
| `inferred` | **Model synthesis** from naming, structure, or test shape — a reading, flagged as one. | *"The `grace_period` field suggests late payment is tolerated"* — flagged, low confidence. |

Mapping onto the shared evidence scale: `recorded→read, enforced→read,
inferred→inferred` — nothing in this genre is `demonstrated` unless a consented live run
(a test, a validator invoked on sample input) shows the rule fire, which upgrades that
one claim. Below the scale sits **`unknown`** — a declared gap, not a weak claim: it goes
to the Known-Unknowns Register and is never taught as fact.

## The Teaching Contract — curriculum, citations, comprehension checks

| Element | Rule |
|---|---|
| **Curriculum** | Six lessons, announced up front and driven by the tutor: L1 Context → L2 Actors & Roles → L3 Nouns & Lifecycles → L4 Processes & Journeys → L5 Rules & Invariants → L6 Ubiquitous Language. The learner may reorder or skip — stated, not silent. |
| **Citations** | Every factual claim is pinned to `file:line` or a named artifact and typed; load-bearing evidence is quoted, not paraphrased. |
| **Comprehension checks** | After each lesson, a short check the learner answers in their own words. A shaky answer → re-teach at greater depth with fresh evidence; a confident answer → advance. Checks adapt depth; they never grade or gate progress against the learner's will. |
| **Routing** | A reactive "wait, what's X?" is answered in one or two cited lines, then: *"for more one-off lookups like that, `/ce-ask` is the dedicated tool."* |

The tutor **never declares the learner "done" or "qualified"** — comprehension is the
learner's to claim. It reports what was covered, what was deferred, and what only a
human can answer.

## Human-in-the-Loop — adaptive

The session is a dialog; two *bounded* decision points are gated, the rest is the
teaching loop itself.

- **Setup — confirm scope, audience & depth (material).** Confirm the scope, name the
  audience (an engineer gets the enforcing code quoted; a non-engineering reader gets
  the rule in plain language with the citation kept), and pick a depth: a *checked
  walkthrough* (comprehension checks per lesson) or a *narrated tour* (faster, no
  checks). Each option states its consequence inline.
- **Wrap-up — save a domain primer? (its own prompt).** Writing a durable file is the
  one side effect on disk; it gets its own clearly-labeled consent prompt — never a
  bullet that rides through on a single "OK".
- The lesson loop itself is **not** gated with "Gate N of M" numbering: the loop is
  open-ended (it runs until the learner is satisfied), so M is genuinely uncomputable
  and a hardcoded constant is forbidden (HITL Gate Standard R5). Use plain locators
  (*Setup*, *Wrap-up*) and consequence-labeled options (`Checked walkthrough — I quiz
  you per lesson` / `Narrated tour — faster, no checks`), never bare `Yes/No`.

If a Setup inference is auto-derived (e.g. "you said you're joining the billing team, so
I'll scope to the billing module"), **show the basis**, don't ask for blind confirmation
(R2 spirit).

---

## Stage 0 — Load, detect, and scope  [material gate]

1. **Resolve the scope.** A path narrows the sweep to that subtree; a plan slug prefers
   that plan tree's recorded claims; nothing means the whole repository. If the argument
   is ambiguous, ask.
2. **Detect the evidence mode.** Probe for recorded human claims touching the scope —
   plan trees under `docs/plans/`, briefs under `docs/briefs/`, `docs/adr/`,
   `docs/decisions/` (hand-written ADRs in a non-pipeline repo count too). Classify —
   auto-detected and stated, never asked:
   - **Plan-grounded:** recorded claims exist — brief roles, journey map, decisions
     ledger, EARS, ADRs are harvested as first-class evidence alongside the code.
     Multiple plan trees are all harvested; conflicts between them are surfaced, not
     resolved.
   - **Code-derived:** no recorded source touches the scope — the domain is
     reconstructed from code signal alone, and every claim that would have come from a
     recorded source is either re-derived from code (typed `enforced`/`inferred`) or
     registered as unknown.
3. **State what exists and what doesn't.** Print a short evidence inventory — *"Teaching
   from: 2 plan trees (brief, journey map, 14 EARS criteria, 3 ADRs), 12 entities, 4
   state enums, 31 validators, 3 authz roles, 6 jobs. No interaction-contract. No brief
   — roles will be code-derived only."* Graceful degradation is named, never silent (see
   the table below).
4. **Confirm scope, audience & depth** with the human (the material gate).

### Graceful degradation — what the tutor does when evidence is thin

| Evidence state | How the tutor teaches it |
|---|---|
| Plan-grounded, rich | Recorded claims lead each lesson; code confirms or contradicts them (a contradiction is high-signal — surface it). |
| Plan tree without a brief | Actors come from authz code and journey actors; the product's stated purpose falls back to README/docs. |
| Code-derived (no plan) | Every lesson runs from code signal alone; rationale, market context, and personas are registered as unknowns, not reconstructed. |
| No README / docs | L1 Context is taught from manifests, entry points, and external clients — and the absence is named as its own finding. |
| Sparse domain signal (thin models, no enums, no validators) | The tutor says the code encodes little domain structure — a short session and a long register beat an invented domain model. |
| UI copy contradicts code names | Taught in L6 as a vocabulary conflict — reported, never resolved by fiat. |

---

## Stage 1 — Evidence sweep

Build the **domain evidence base** before teaching: run the per-lesson harvest recipes in
`${CLAUDE_SKILL_DIR}/lessons.md` across the scope, collecting every candidate fact as
*(claim, citation, type)* — nouns, states and guards, actors and their powers, flows and
schedules, rules and their enforcement points, terms and their conflicts. Register
unknowns **as they are raised** (a guard with an unexplained threshold registers its
*why* immediately), not retrospectively. The sweep is silent legwork; nothing is taught
from an unswept area without saying so.

## Stage 2 — The curriculum  (the core loop)

Teach the six lessons in order, from the evidence base, one at a time. For each lesson,
`${CLAUDE_SKILL_DIR}/lessons.md` defines: what to teach, the plan-grounded and
code-derived sources, the claim-typing discipline, the comprehension check, and the
unknown shapes that lesson typically raises.

| Lesson | Teaches |
|---|---|
| **L1 — Context** | What the product is, for whom, and the external world it touches. |
| **L2 — Actors & Roles** | Who acts on the system, what each may do, and which system actors act alongside humans. |
| **L3 — Nouns & Lifecycles** | The domain nouns, the states each walks through, and the guards between states. |
| **L4 — Processes & Journeys** | The flows the product supports, the rhythms it runs on, and where humans sit in them. |
| **L5 — Rules & Invariants** | What the system will not allow, where that is enforced, and which *whys* are recorded vs unknown. |
| **L6 — Ubiquitous Language** | The product's vocabulary as the repository actually uses it — including its conflicts. |

Pace: teach → cite → check (checked mode) → adapt. A shaky answer re-teaches with fresh
evidence; a confident one advances. If the learner narrows scope, say what is skipped.

## Stage 3 — Known-unknowns handoff + optional primer  [its own consent prompt]

1. **Render the Known-Unknowns Register** — the questions only a human can answer,
   grouped: **rationale** (*the code enforces X; why is unrecorded*), **context**
   (*market, regulation, competitors*), **process** (*what humans do around the
   software*), **vocabulary** (*which of two names is canonical*). Each entry carries
   the question, the evidence that raised it (cited), and a **pointer to who might
   know** — the `git blame` owner of the enforcing code or a `CODEOWNERS` entry, offered
   as a pointer, never as an answer.
2. **Ask — as its own prompt, never a buried bullet — whether to save the primer:**
   - **Save the primer** — writes `docs/domain/<date>-<scope>-primer.md` (dated, never
     overwritten — the same snapshot discipline as the other discovery tools), using
     `${CLAUDE_SKILL_DIR}/primer-template.md`.
   - **Skip** — the session stays a throwaway walkthrough; the register is still
     rendered in the dialog for the learner to carry to their team.

## Closing

After the session (and the optional primer), confirm:

```text
Domain onboarding complete: <scope> — plan-grounded (<slugs>) | code-derived
Lessons taught:   <N> of 6 (depth: checked | narrated)
Claims taught:    <R> recorded · <E> enforced · <I> inferred
Known unknowns:   <U> registered for a human
Primer:           docs/domain/<date>-<scope>-primer.md | not saved
```

Point to the next action: to learn the as-built implementation next, name `/ce-onboard`;
for one-off follow-ups, name `/ce-ask`. Never commit; never deploy.

---

## Escalation

The Known-Unknowns Register escalates to **people, not tools** — its questions are
answerable only by the team, a domain expert, or a product owner; hand it over. For the
implementation layer (architecture, gotchas, verified behavior) route to `/ce-onboard`;
one-off code questions go to `/ce-ask`; user-facing documentation goes to
`/ce-ship-document`; changing behavior is `/ce-spec` → `/ce-implement` (or `/ce-patch`).
This skill teaches and writes only the optional domain primer.

## Honest Limitations

- **A codebase is a witness, not the domain.** The session reconstructs what the
  repository can evidence; the true domain is always larger. The register measures the
  gap honestly — a long register is a finding, not a failure.
- **It never invents the *why*.** Where no ADR, brief, comment, or doc records a
  rationale, the rationale is a registered unknown — even when a plausible story is
  obvious. Plausible-but-unevidenced is exactly the failure mode this tool exists to
  prevent.
- **`recorded` means a human wrote it down, not that it is still true.** A brief or ADR
  can describe a domain the product has since pivoted away from. Recorded claims the
  code cannot corroborate are taught with their artifact's date, a recorded-vs-code
  conflict always surfaces (it is high-signal, never smoothed over), and liveness is
  never assumed — a seed, fixture, or flag-disabled path is weak evidence of the live
  domain and registers rather than teaches when its liveness is unclear.
- **Not implementation onboarding.** How the code is built, reviewed, and verified is
  `/ce-onboard`'s curriculum; this tool routes there rather than duplicate it.
- **Not user-facing docs.** The primer is team-internal; for product docs use
  `/ce-ship-document`.
- **Not a Q&A tool.** For reactive, one-off lookups use `/ce-ask`; this tool drives a
  curriculum and will route you there.
- **Code-derived mode is leaner.** Without a plan tree there are no recorded roles,
  journeys, or decisions — those lessons run on `enforced`/`inferred` claims only, and
  the register grows accordingly.
- **Vocabulary conflicts are reported, not resolved.** When the repository uses two
  names for one concept (or one name for two), the tutor surfaces it with citations;
  choosing the canonical term belongs to the team.
- **Live runs are opt-in and safe-only.** Demonstrating a rule live (a test, a validator
  on sample input) happens only with consent and only non-destructively; it never
  deploys or mutates state.
