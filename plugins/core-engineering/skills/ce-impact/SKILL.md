---
name: ce-impact
description: |
  Analyze the codebase impact of a proposed change described in plain text (e.g. an Azure DevOps work item pasted in) — affected components, blast radius, an approximate sizing hint, similar prior work, and the open questions a thin description leaves — as file:line-cited FINDINGS, never a verdict. Refuses loudly when the description is too thin to ground. Read-only on code; ephemeral; one-way (renders a paste-ready summary the human posts back themselves — no tracker API, no write-back).
  Triggers: estimate/assess the impact or blast radius of a proposed change or work item before building it. For a question about existing code use /core-engineering:ce-ask; to decompose a whole project use /core-engineering:ce-plan; to investigate a failure use /core-engineering:ce-debug.
argument-hint: "[work-item text or change description]"
allowed-tools: Read, Glob, Grep, Bash, AskUserQuestion, Skill
---

# Impact

**Invocation input:** Change to analyze: $ARGUMENTS


Given a **proposed change described in plain text** — typically the title +
description of an issue tracker work item (Azure DevOps, Jira, GitHub) pasted in —
report what that change would **touch in this codebase**: affected components, the
blast radius, an approximate sizing hint, similar prior work, and the questions the
description leaves unanswerable. Output is **grounded, cited findings** that a human
reads during refinement — never a go/no-go verdict.

This tool is **read-only**, **plan-free**, and **repo-agnostic**. It is **not** part
of the plan/spec/implement pipeline and consumes none of those artifacts. It is the
*forward-looking* sibling of `/core-engineering:ce-ask` (which answers questions about code as it is) and
reuses `/core-engineering:ce-ask`'s scoping discipline plus `/core-engineering:ce-plan`'s reachability / blast-radius
vocabulary — it does not re-derive that reasoning.

**The tool is tracker-agnostic by design.** It takes plain text and knows nothing
about Azure DevOps or any API. The most common source is an ADO work item, but the
skill never reads from or writes to a tracker — see *Cross-cutting rule — One-Way*.

## Runtime Inputs

- **Change description (required):** the text of the proposed change. Usually a
  pasted work item (title + description, and acceptance criteria if present), but any
  natural-language change request works. Examples:
  - *"Add CSV export to the orders report"*
  - *"Bug: login is slow when a user has many sessions"*
  - *"Move rate limiting from the gateway into each service"*
- **Optional area hint:** a component, path, service, or symbol the change concerns
  (e.g. `billing/`, `OrderService`), if the requester knows it. Narrows scoping.
- **The repository:** the current working directory, at its current commit.

## Execution Contract

0. **Session write lease (structural, first act).** `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --set --skill ce-impact` — this session writes nothing (the summary is rendered, not written), and the write guard now enforces that. Last act: `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --restore-baseline`. A denied write mid-session means this contract and the action disagree — reconcile; never edit or delete the lease to proceed.
1. **Ground-check first (the Thin-Description Gate).** Before any analysis, decide
   whether the description is concrete enough to ground. If not, **refuse loudly** —
   say what is missing, not a guessed impact. See *Thin-Description Gate* below.
2. **Two-phase.** Scope first (cheap search — grep, glob, symbol search), then read
   only the relevant files. Never bulk-read.
3. **Every factual claim cites `file:line`** (or a small range). No citation, no claim.
4. **Findings, not a verdict.** Report impact, risk, and an approximate size. Do
   **not** say "this is too risky, don't do it", do **not** emit a confident effort
   number, and do **not** restate the title. The human owns the decision.
5. **Approximate by construction.** The sizing hint is `S` / `M` / `L`, explicitly
   labelled approximate, with its basis shown. It is a coarse read for refinement,
   not an estimate.
6. **Honest about uncertainty.** Anything the description leaves unanswerable, or any
   impact you cannot evidence, goes under *Open questions* — never papered over.
7. **Read-only.** No commits, no edits, no writes. The `/core-engineering:ce-impact` skill's
   `allowed-tools` deliberately exclude `Write` and `Edit`. The output is the
   conversation answer plus a paste-ready block the human copies.
8. **Repo-agnostic.** Don't assume language, framework, or layout — detect.
9. **Out of scope:** the plan/spec/implement/verify artifacts under `docs/plans/`.
   Treat them as ordinary docs if they surface via search; don't seek them out.

## Cross-cutting rule — One-Way

This tool **never touches the tracker**. It reads code and renders a summary; a human
reviews it and pastes it back into the work item if they choose. There is **no API,
no write-back, no sync** — the same posture `/core-engineering:ce-ship-backlog` takes for the reverse
direction. Two consequences, both made explicit in the output:

- The paste-ready block carries a **provenance stamp** — `Analyzed against: <repo>@<short-sha>`
  (from `git rev-parse --short HEAD`) — so a point-in-time finding against a moving
  codebase is auditable and visibly stale once the code moves.
- It is labelled **AI-assisted analysis, not a review** — the reader owns the call.

## Thin-Description Gate

A fresh work item is often a one-line stub with nothing the codebase can be reasoned
about. Analyzing it produces fluent-but-baseless output — the exact failure this
toolset exists to prevent. So **ground-check before analyzing**:

- The description is **analyzable** when it names at least one **subject the codebase
  recognizes** (a component, entity, endpoint, behavior, or symbol you can locate)
  **and** an **action** (add / change / remove / fix). A cheap scoping pass (one or
  two greps) must find a real anchor.
- If it does **not** — no locatable subject, or pure process work ("schedule a
  meeting", "update the roadmap") — **stop and report**:
  - that the description is too thin to ground (don't guess),
  - **what specifically is missing** (e.g. "no component or behavior named that maps
    to code"), and
  - **what would make it analyzable** (e.g. "name the screen/endpoint/module, or the
    user-visible behavior that changes").

Refusing on a stub is a feature: a tool that knows when to stay silent is the only
kind a team learns to trust.

## Scoping strategy — reuse `/core-engineering:ce-ask`'s contract, don't re-derive it

Repository exploration here **is `ask`'s discipline**, applied to a
forward-looking question — not a second copy of it. Treat the `ask` skill's
**Execution Contract** and **Question Types** as the single source of truth for *how*
to explore: **two-phase** (cheap scope → selective read, never bulk-read), **every
claim `file:line`-cited**, **repo-agnostic**, and **honest about what isn't found**.
The primary `ask` question type for impact is **Impact / Callers** (reverse
search for what depends on the subject); its *Location*, *Flow*, and
*Convention/Placement* types apply when the change implies them. Don't restate that
table here — if `ask`'s scoping discipline improves, this skill inherits it.

**One deliberate deviation — completeness over satisfice.** `ask` is tuned to
*stop scoping once it has enough for a crisp answer* (3–8 files). Impact analysis needs
the **opposite stopping rule for the blast-radius lenses**: keep going until the
reachability set is *covered*, not merely sufficient — an un-found caller is a missed
impact. So borrow `ask`'s mechanics, but scope for **coverage** on callers/
consumers, durable state, and surface, and record any reachability you could not
exhaustively confirm under *Open questions* (never imply completeness you didn't reach).

## Blast-radius vocabulary (borrowed from `/core-engineering:ce-plan`, not re-derived)

When tracing impact, reuse `/core-engineering:ce-plan`'s reachability / blast-radius lenses rather than
inventing new ones:

- **Reachability / consumers** — who calls or depends on the touched code; how far the
  change propagates outward.
- **Durable-state closure** (`/core-engineering:ce-plan` §6.3) — does the change add/alter/remove
  persisted state (a table, column, schema, migration, stored event)? Durable changes
  are higher blast radius.
- **Surface / interface closure** (`/core-engineering:ce-plan` §6.4) — does it change a public interface,
  API contract, event shape, or CLI surface that other code or other teams depend on?
- **Test surface** — which existing tests cover the touched code; where new coverage
  would be needed.

## Workflow

### 1. Parse & ground-check

Extract the subject(s) and action from the description. Run the cheap scoping pass.
If the Thin-Description Gate fails, emit the *Not analyzable* output (below) and stop.

### 2. Scope — find the anchor files (cheap)

Apply the scoping strategy above — `ask`'s two-phase discipline — but scope for
**coverage** on the blast-radius lenses, not just a sufficient answer. Index → detail;
never load whole large files. Stop when the reachability set is covered, not when it's
merely enough.

### 3. Trace impact & blast radius (read selectively)

From the anchors, trace the blast-radius lenses: direct touch points, callers/
consumers, durable-state and surface changes, and the test surface. Read only the
relevant ranges.

### 4. Assess

- **Risk read** — does the change touch sensitive ground? (auth/authz, persistence/
  migrations, money/billing, an external boundary, a widely-consumed interface.) Name
  it; don't score it.
- **Sizing hint** — `S` / `M` / `L`, approximate, with the basis (e.g. "L — alters a
  migration and 3 call sites across 2 services").
- **Similar prior work** — `git log` / grep for related changes, components, or
  patterns the implementer can reuse.
- **Open questions** — what the description leaves unanswerable, and the uncertainties
  in your own trace.

### 5. Render — findings + paste-ready block

Use the output shape below. End with the one-way reminder: the human pastes the block
back into the tracker themselves; the tool does not.

## Output shape

### When analyzable

````markdown
**TL;DR:** <one paragraph, ≤ 3 sentences — what this change touches and its rough size>

**Affected components**
- `path/to/file.ts:42-68` — <what changes here and why>
- `path/to/other.py:15` — <…>

**Blast radius**
- Reachability: <callers/consumers, cited>
- Durable state: <tables/schemas/migrations touched, or _none_>
- Surface/contract: <interfaces/APIs/events changed, or _none_>
- Test surface: <covering tests, gaps>

**Risk read:** <named sensitive ground touched, or "no sensitive ground touched"> (cited)

**Sizing hint:** S | M | L — _approximate_ — <basis>

**Similar prior work**
- <linked change/component the implementer can reuse, cited> — or _none found_

**Open questions**
- <what the description leaves unanswerable / what the codebase can't settle>

---
**Paste-ready (for the work-item discussion)**

```
🤖 AI-assisted impact analysis (not a review — confirm before acting)
Analyzed against: <repo>@<short-sha>

Touches: <components, terse>
Blast radius: <durable-state? surface/contract? key consumers>
Risk: <sensitive ground or "none">
Rough size: S|M|L (approximate)
Reuse: <prior work> | Open questions: <the gaps that need answering>
```
````

The **TL;DR**, **Affected components**, and **Sizing hint** sections are mandatory.
The paste-ready block is what the human copies into the tracker.

### When not analyzable (Thin-Description Gate failed)

````markdown
**Not analyzable yet** — the description is too thin to ground an impact analysis.

- **What's missing:** <e.g. no component, behavior, or symbol that maps to code>
- **What would make it analyzable:** <e.g. name the endpoint/screen/module, or the
  user-visible behavior that changes>

I did not guess an impact. Re-run once the item names something the codebase recognizes.
````

## Honesty norms

- **If the codebase doesn't contain the subject, say so** — "I searched X, Y, Z and
  found nothing matching `<subject>`; it may not exist here yet, or be named
  differently." That is itself a finding (the change may be greenfield).
- **Greenfield changes** — if the change adds something with no existing analog, say
  so and describe where it would land + what it would touch, flagged as forward-looking.
- **Shallow trace** — if you traced only the obvious path, offer to go deeper rather
  than implying completeness.
- **Stale evidence** — if a comment contradicts the code, prefer the code and flag it.

## Escalation

If the change is analyzable and meaningful, route to `/core-engineering:ce-plan` for decomposition or
`/core-engineering:ce-patch` only when the impact is genuinely bounded. If the analysis exposes a
technical choice with multiple viable options, route to `/core-engineering:ce-decide`. Thin inputs stop
at the Thin-Description Gate instead of guessing.

## Honest Limitations

- **Not a verdict.** It will not tell you whether to do the work — that's the human's
  call (use `/core-engineering:ce-decide` for a weighed technical recommendation).
- **Not an estimate.** The sizing hint is a coarse refinement aid, not a commitment.
- **Point-in-time.** The analysis is pinned to the current commit (stamped); it goes
  stale as the code moves. There is no sync.
- **Not a planning or spec tool** — use `/core-engineering:ce-plan` to decompose a
  project, `/core-engineering:ce-spec` to specify one feature.
- **Read-only.** It never edits code and never writes to a tracker.
