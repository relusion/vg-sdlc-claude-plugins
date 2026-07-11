---
name: ce-onboard
description: |
  Interactively teach a developer the implementation that was built — a paced, evidence-grounded walkthrough of a plan's as-built code (architecture, the decisions behind it, the gotchas, the verified behavior) with comprehension checks, for the maintainer who now owns code they (or /ce-auto-build) didn't hand-write. Reads the plan's own artifacts when present; degrades to code + git grounding when absent. Read-only on code; teaches, never patches.
  Triggers: onboard/walk me through/teach me/explain how this was built so I can maintain it. For the business domain the code encodes (actors, domain nouns, business rules, vocabulary) use /ce-domain; for a one-off question use /ce-ask; for user-facing docs use /ce-ship-document; for process metrics use /ce-retro.
argument-hint: "[plan-slug | feature-id | path]"
allowed-tools: Read, Write, Glob, Grep, Bash, AskUserQuestion, Skill
---

# Onboard

**Invocation input:** Target to teach (optional): $ARGUMENTS


Teach a developer the **as-built implementation** — a paced, guided walkthrough
that adapts to their answers — so they can own and extend code they (or
`/ce-auto-build`) didn't hand-write. This is the missing closure on the autonomous-build
story: the pipeline produces verified, reviewed code, and this tool **transfers
understanding of it to a human**.

The workflow is **read-only on code and existing artifacts**. It teaches; it never
patches code, edits specs, or modifies any other artifact. The only thing it may
write is one optional, consented **learning guide** — a maintainer-internal document,
never the user-facing docs that `/ce-ship-document` owns.

It **owns a curriculum and drives it** — that is the load-bearing distinction from
`/ce-ask`. `/ce-ask` is reactive and human-driven (you ask, it answers); this tool sets the
learning path, paces the walk, and **checks that the learner understood**. Reactive,
ad-hoc questions mid-session are routed back to `/ce-ask`, so the tutor's agenda stays
intact.

## Runtime Inputs

- **Target (optional):** a plan slug, a feature id (`<slug>/<id>`), or a path. Without
  one, list the plans under `docs/plans/` and ask which to teach — or whether to teach
  the repo plan-free. Never guess.
- **The repository:** the current working directory.
- **Grounding artifacts (read-only, consumed when present):** `feature-plan.md`
  (overview, *Why This Split*, journey map, feature table, dependency flow),
  `shared-context.md` (codebase profile + Resolved Project Decisions ledger),
  `plan.json` (ship order, DAG), `features/<id>.md` (charter: scope / excluded /
  unlocks / open unknowns), `ce-spec.md` (Frozen Boundary, EARS ACs, traceability matrix),
  `tasks.json` (`files[]` → the real code), `code-review.md` + `review-summary.json`
  (`confirmed`-first gotchas), `threat-model.md` (trust boundaries, per-feature
  obligations), `interaction-contract.md` (cross-feature protocol invariants +
  architecture-determining NFRs), `verification.md` (the Try-It-Yourself runbook), the relevant `docs/adr/`
  files, `diagnosis.md` (failure history). **When an artifact is absent, the tutor
  teaches the absence — it never invents a finding from a missing file.**

## Execution Contract

0. **Session write lease (structural, first act).** `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --set --skill ce-onboard --allow 'docs/onboarding/**' --allow 'docs/plans/**/onboarding/**'` — only the optional learning guide is writable, and the write guard now enforces that. Last act: `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --restore-baseline`. A denied write mid-session means this contract and the action disagree — reconcile; never edit or delete the lease to proceed.
1. **Never patch code, edit specs, or modify feature files.** Teach, do not fix. The
   `/ce-onboard` skill's `allowed-tools` deliberately exclude `Edit`.
2. **Read-only on existing artifacts.** Write only the one optional learning guide
   (Stage 6), and only with consent.
3. **Every claim cites `file:line` or an artifact.** No citation, no claim. Show code
   over paraphrasing it — quote 1–5 load-bearing lines inline. (The `ask` grounding
   contract, reused verbatim: this tool is a *sibling* of `/ce-ask`, not a rival.)
4. **No fabrication.** If a file, symbol, or artifact isn't found, say so; never invent
   paths, decisions, or behaviors. Anything not directly evidenced is named as a *known
   unknown*, never papered over.
5. **The tutor owns the agenda.** It proposes the next lesson and asks a comprehension
   check; it does not wait to be asked. Ad-hoc reactive questions are answered briefly,
   then explicitly routed to `/ce-ask`.
6. **Teach from evidence, in build order.** The curriculum follows the artifact trail
   (orient → map → per-feature deep-dive → gotchas → behavior); rationale comes from the
   decisions ledger and ADRs, not from guesswork.
7. **Adaptive depth, never silent.** The walk adjusts to how the learner answers, but
   any narrowing of scope is stated — no silent caps on what was skipped.
8. **Maintainer audience.** The output explains *how and why the code was built* for the
   person who must extend it — categorically not the user-facing "how to use it" that
   `/ce-ship-document` produces.

## The Teaching Contract — curriculum, citations, comprehension checks

This tool's job is to *transfer understanding*, measured three ways:

| Element | Rule |
|---|---|
| **Curriculum** | The tutor sets and announces the path (orient → map → per-feature → gotchas → behavior) and drives it. The learner may reorder or skip — stated, not silent. |
| **Citations** | Every factual claim is pinned to `file:line` or a named artifact; load-bearing code is quoted, not paraphrased. |
| **Comprehension checks** | After each deep-dive, a short check the learner answers in their own words. A shaky answer → re-teach at greater depth with a fresh citation; a confident answer → advance, optionally deeper. Checks adapt depth; they never grade or gate progress against the learner's will. |
| **Routing** | A reactive "wait, what's X?" is answered in one or two cited lines, then: *"for more one-off lookups like that, `/ce-ask` is the dedicated tool."* |

The tutor **never declares the learner "done" or "qualified"** — comprehension is the
learner's to claim. It reports what was covered and what was deferred.

## Human-in-the-Loop — adaptive

The session is a dialog; two *bounded* decision points are gated, the rest is the
teaching loop itself.

- **Setup — confirm scope & depth (material).** Confirm the target and pick a depth:
  a *checked walkthrough* (comprehension checks per feature) or a *narrated tour*
  (faster, no checks). Each option states its consequence inline.
- **Wrap-up — save a learning guide? (its own prompt).** Writing a durable file is the
  one side effect on disk; it gets its own clearly-labeled consent prompt — never a
  bullet that rides through on a single "OK".
- The comprehension loop itself is **not** gated with "Gate N of M" numbering: the loop
  is open-ended (it runs until the learner is satisfied), so M is genuinely uncomputable
  and a hardcoded constant is forbidden (HITL Gate Standard R5). Use plain locators
  (*Setup*, *Wrap-up*) and consequence-labeled options (`Checked walkthrough — I quiz you
  per feature` / `Narrated tour — faster, no checks`), never bare `Yes/No`.

If a Stage-0 scope inference is auto-derived (e.g. "you said you're extending auth, so
I'll start there"), **show the basis**, don't ask for blind confirmation (R2 spirit).

---

## Stage 0 — Load, detect, and scope  [material gate]

1. **Resolve the target.** If a plan slug / feature id is given, load it via
   `docs/plans/plans.json`. If a path is given, treat it as a plan-free target. If
   nothing is given, list the plans and ask which to teach (or offer plan-free over the
   repo). If multiple plans match, ask.
2. **Detect the evidence available.** Probe which grounding artifacts exist for the
   target (see Runtime Inputs). Classify the mode:
   - **Plan-tied (rich):** a `docs/plans/<slug>/` directory exists — teach from the full
     artifact trail.
   - **Patch-lane:** registered with `origin:"patch"` — teach from `ce-spec.md` +
     `verification.md` + the `eligibility.json` lease (no threat-model / review by design).
   - **Plan-free (lean):** no plan — teach structure + flow from code, citing
     `git log`/`git blame`/tests for rationale (the `/ce-ask` degradation).
3. **State what exists and what doesn't.** Print a short evidence inventory — *"Teaching
   from: plan, 6 specs, code-review (4 confirmed findings), verification. No
   threat-model (attested No Security Surface). No verification-report yet — features are
   `implemented` but not plan-`Verified`."* Graceful degradation is named, never silent
   (see the table below).
4. **Confirm scope & depth** with the human (the material gate): the target, and
   *checked walkthrough* vs *narrated tour*.

### Graceful degradation — what the tutor does when evidence is thin

| Evidence state | How the tutor teaches it |
|---|---|
| `/ce-patch` feature | Teach from spec + verification + the lease's seven clause verdicts (the *why this was small enough to skip ceremony* story). A patch with **no** `verification.md` is an *abandoned patch* — surface it, don't treat it as done. |
| Single-feature plan (Sizing Gate accepted) | One flat `feature-plan.md`, no `features/` dir — the deep-dive collapses into the orient step. |
| No `threat-model.md` | If an attested **"No Security Surface"** negative exists, teach the absence as *attested*. Otherwise flag the gap honestly. |
| No `interaction-contract.md` | If an attested **"No Cross-Feature Protocol"** negative exists, teach the absence as *attested*. Otherwise flag the gap honestly. |
| No `verification-report.md` | `/ce-verify` hasn't run — teach features as `implemented` (per-feature `verification.md`) but **not** plan-`Verified`; no cross-feature integration proof exists yet. |
| `code-review.md` Highs all `suspected` | The adversarial pass couldn't reproduce them — teach as *open questions to verify*, not confirmed defects. |
| No `review-policy.md` | Review ran uncalibrated and says so — tell the learner the repo has no codified quality bar yet. |
| Plan-free | Teach structure + flow from code; rationale from `git log`/`git blame`/tests, flagged explicitly when unrecoverable. |

---

## Stage 1 — Orient

*"Here's the system, the stack it lives in, and why it was sliced this way."*

- From `feature-plan.md`: the **Overview** and **Why This Split** (the whole mental model
  in two sections).
- From `shared-context.md`: the **Codebase Profile** (stack, hot files, brownfield
  friction) and a first pass over the **Resolved Project Decisions ledger** — the running
  record of every cross-feature *why*.
- Cite each claim to its artifact. End with a one-line check: *"In your words, what is
  this system and why is it broken into these pieces?"* (checked mode only).

Plan-free: substitute the codebase profile with a detected stack summary (manifest,
entry points, test layout), cited to the files that prove it.

---

## Stage 2 — Map

*"Every feature, the order it ships in, and the journeys that thread them."*

- From `feature-plan.md`: the **Feature Table** + **Dependency Flow** graph + **Journey
  Map**, cross-read with `plan.json` for the canonical **ship order** and DAG.
- Present the dependency flow as the spine of the tour — name which feature unlocks which,
  and which journeys cross multiple features.
- Check: *"Which feature would you have to understand first, and why?"* (the dependency
  root — confirms they read the DAG).

Plan-free: derive a module/dependency map from imports and directory structure; cite the
representative files. Say explicitly that there is no journey map to ground user flows.

---

## Stage 3 — Per-feature deep-dive  (the core loop)

Walk features in `ship_order`. For each:

1. **Charter** — `features/<id>.md`: Description, **Scope**, **Excluded** (the high-signal
   "why doesn't it do X"), **Unlocks**, and **open_unknowns** (what was uncertain at plan
   time). Cite the feature file.
2. **Contract** — `ce-spec.md`: the **EARS Acceptance Criteria** (what it must do) and the
   **Traceability Matrix** (the literal Scope → AC → TC → Task teaching graph). Flag any
   `[SECURITY: TZ-NNN]` ACs.
3. **Code** — `tasks.json` `files[]` → open the **real code** that realizes each AC. Quote
   the load-bearing lines; trace the main flow through 3–8 files (the `ask` flow
   strategy). Pin every claim to `file:line`.
4. **Why** — whenever a Resolved Decision cites an **ADR**, pull it: teach the **Context**
   (the origin), the **Decision**, and the **Consequences** (the trade-off the team
   accepted, the alternative it killed). This is the deepest *why* layer.
5. **Comprehension check** (checked mode): a short question that requires having understood
   the flow — e.g. *"If you needed to change how X is persisted, which file and which AC
   would you touch, and what would break?"* Adapt depth to the answer; re-teach a shaky
   spot with a fresh citation.

Keep the loop honest: walk every in-scope feature; if the learner narrows scope, say what
is being skipped.

---

## Stage 4 — Gotchas

*"What's sharp, what crosses a trust boundary, and what already bit us."*

- From `review-summary.json` then `code-review.md`: surface **CR-N findings**,
  **`confirmed` first**, each pinned to `file:line` with its lens and observation. Teach
  `suspected` findings as open questions, not facts.
- From `threat-model.md`: the trust boundaries and per-feature `security_obligations`
  the learner must respect when extending the code.
- From `diagnosis.md` (if present): **DX-N root causes at `file:line`** and their
  classification (bug / spec-gap / structural) — the subtle traps, with proof of how they
  bit. Absence of this file is normal (nothing failed), not a gap.
- Cross-reference `review-policy.md` / `review-learnings.md` so the learner knows *this
  repo's* quality bar and which false-positive shapes were deliberately silenced.

---

## Stage 5 — Behavior

*"Run this to see it work; here's the proof it works with everything else."*

- From `verification.md`: present the **Try-It-Yourself** runbook — the *real* commands
  that were run. **With the learner's consent**, run them live (read-only / safe commands
  only; never destructive, never a deploy) so they see the feature behave, not just read
  about it. Without consent, walk the runbook as text.
- From `verification-report.md` (if present): the per-journey verdicts and the
  **Per-Feature Status** roll-up — the authoritative `Verified` picture and what's still
  partial or blocked.
- Final check (checked mode): *"Run the auth journey yourself and tell me where the
  request first crosses a trust boundary."*

---

## Stage 6 — Optional learning guide  [its own consent prompt]

Ask — as its own prompt, never a buried bullet — whether to save a durable **maintainer
learning guide**:

- **Save the guide** — writes a durable `.md` the learner (and the next maintainer) keeps.
- **Skip** — the session stays a throwaway walkthrough.

If saved, write to the **internal** tree, never the user-facing doc paths `/ce-ship-document`
owns:
- Plan-tied → `docs/plans/<slug>/onboarding/<date>-walkthrough.md`
- Plan-free → `docs/onboarding/<date>-<target>.md` (dated, never overwritten — the same
  snapshot discipline as the other discovery tools)

Use the template below.

---

## Learning Guide Template — `<date>-walkthrough.md`

````markdown
# Onboarding Walkthrough: <target>

> Generated by `/ce-onboard`
> Date: YYYY-MM-DD · Mode: plan-tied (<slug>) | patch | plan-free
> Covered: <N> features · Depth: checked | narrated
> Evidence taught from: <artifacts present>  ·  Absent (attested/degraded): <list>

## The system in one paragraph
<what it is and why it was sliced this way — cited to feature-plan.md / detected stack>

## Map
- **Ship order & dependencies:** <the DAG, named>
- **Journeys:** <the user flows that thread the features>

## Per-feature notes
### <id> — <title>
- **Does:** <scope, cited>   ·   **Explicitly out:** <excluded>
- **Contract:** <key EARS ACs, incl. any [SECURITY: TZ-NNN]>
- **Code:** `path/to/file.ts:42-68` — <what realizes the contract>
- **Why this way:** <Resolved Decision / ADR-NNNN, the trade-off accepted>
- **Watch out for:** <CR-N confirmed finding @ file:line, threat obligation, DX-N trap>
- **Extension points:** <where a maintainer would safely add to it>

## Gotchas (whole-plan)
| Source | Where | Watch out for |
|---|---|---|
| CR-N (confirmed) | `file:line` | <observation> |
| Threat TZ-NNN | <surface> | <obligation> |
| DX-N | `file:line` | <root cause> |

## Behavior — run it yourself
<the Try-It-Yourself runbook, verbatim, plus the Verified roll-up>

## Known unknowns
- <each uncertainty, named with the area where evidence is missing>
````

---

## Closing

After the session (and the optional guide), confirm:

```text
Onboarding complete: <target> — <mode>
Features taught:  <N> (depth: checked | narrated)
Gotchas covered:  <C> (<confirmed> confirmed, <suspected> suspected)
Guide:            docs/plans/<slug>/onboarding/<date>-walkthrough.md | not saved
```

Point to the next action: if the learner intends to extend a feature, name `/ce-spec <id>`
or `/ce-patch`; for an isolated follow-up question, name `/ce-ask`. Never commit; never deploy.

---

## Escalation

If the learner wants to change behavior, route to `/ce-spec` for planned feature
extensions or `/ce-patch` for a genuinely small change. One-off code questions go to
`/ce-ask`; user-facing documentation goes to `/ce-ship-document`; process metrics go
to `/ce-retro`. This skill teaches and writes only optional learning guides.

## Honest Limitations

- **Teaches what's evidenced, nothing more.** If the build left no artifact and the code
  carries no recoverable rationale (no comments, no tests, no `git` history), the *why*
  is named as a known unknown — never invented.
- **Comprehension is the learner's to claim.** The tutor checks understanding and adapts,
  but never certifies that someone is "qualified" to own the code.
- **Not a code-modification tool.** It is read-only on code; extending a feature is
  `/ce-spec` → `/ce-implement` (or `/ce-patch`), not this.
- **Not user-facing docs.** The learning guide is maintainer-internal; for product docs
  use `/ce-ship-document`.
- **Not a Q&A tool.** For reactive, one-off lookups use `/ce-ask`; this tool drives a
  curriculum and will route you there.
- **Plan-free mode is leaner.** Without a plan there is no decisions ledger, no journey
  map, and no verification proof — rationale falls back to `git`/tests and is flagged when
  unrecoverable.
- **Live runs are opt-in and safe-only.** The Try-It-Yourself lap runs only with consent
  and only non-destructive commands; it never deploys or mutates state.
