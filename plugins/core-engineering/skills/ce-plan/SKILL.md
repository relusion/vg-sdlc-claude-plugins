---
name: ce-plan
description: |
  Decompose a project into an ordered, dependency-aware feature plan with sizing, risk, reachability, and session-fit gates — the spec-driven decomposition downstream stages consume.
  Triggers: plan/decompose/break a project into features or specs. Produces the multi-feature plan /ce-spec then details one feature at a time.
argument-hint: "[project description]"
allowed-tools: Read, Write, Glob, Grep, Bash, AskUserQuestion, Skill
---

# Plan

**Invocation input:** Project description: $ARGUMENTS


Decompose a project description into an ordered, dependency-aware list of
implementation features — validated for sizing, risk, reachability, and session
fit — and write it to a single planning artifact.

This skill is **staged**. `SKILL.md` (this file) is the orchestrator: it holds the
Execution Contract, Core Concepts, and the stage map. Each stage's detailed
procedure lives in a separate file you load only when you reach that stage — do
not load them all up front.

## Runtime Inputs

- **Project description (required):** provided by the invocation or the
  user's request. If it is empty or missing, ask the user for the project
  description in one short prompt before proceeding. Do not invent a description.
- **Project brief (optional):** a dedicated `brief:` input — `brief=docs/briefs/<slug>.md`
  on the invocation line, or a `brief:` argument when invoked directly (e.g. by `/ce-brief`
  at handoff). Distinct from the project-wide reference-document list, this channel
  arms the **Brief-Aware Skip Contract** in Stage 1.4: the brief's intent answers let
  Stage 1.4 skip what it already covers and ask only the codebase-grounded residue.
- **Optional inputs** (project-wide reference documents, target tool, ordering
  constraints, MVP notes, known risks, environment pitfalls, preferred stack,
  examples, existing conventions): collect interactively per Stage 1 only when
  needed for feature boundaries, ordering, risk, or reachability.

## Execution Contract

Follow the workflow exactly. Do not skip stages, gates, or validation. In particular:

0. **Proportionality Gate — before any profiling spend.** If the request is one bounded change (a single behavior in a known location, no new durable state, no cross-feature surface — the `/ce-patch` admission shape), stop *before* Stage 1's codebase profile and offer `/ce-patch` as the default route, stating the cost difference (the patch lane is one skill at ~$4 floor; the full plan → spec → implement spine is ≈$12+ of model calls and hours of attention). Proceeding with a full plan for a patch-shaped request is a legitimate, *consented* choice — record it; never route silently in either direction. A project or multi-feature request passes this gate without a prompt.

1. **Never write the final artifact before Final Plan Approval** (Stage 8.3 → `Write`) — this governs the **final artifact** only. Distinct from it is the **gate-checkpoint scratch** at `docs/plans/.drafts/<slug>/scratch.md`: a terse resume transcript appended after each passed gate so a crash or compaction mid-plan resumes from the last passed gate instead of losing the whole 9-stage run (see **Gate Checkpoint & Resume**). The scratch is never the final artifact — it is never registered in `plans.json`, never a `brief:` or spec input, and Stage 9 deletes it on a successful write; appending a checkpoint is **not** writing the artifact early.
2. **Keep provisional IDs (`P01-…`) until write time**; freeze stable IDs only in Stage 9.
3. **Ask grouped questions, not one-by-one** (Stage 1.4 — 4–6 targeted questions in a single round; up to 10–12 total across rounds).
4. **Use the Two-Surface Rendering Rule** (Stage 5.3): print long tables, diagrams, and per-feature blocks in the conversation as Markdown; reserve compact decision dialogs for the short question + options only.
5. **Apply the Sizing Gate** (Stage 4) before presenting any multi-feature plan. If the project warrants a single-feature plan, present the Sizing Result block and honor the user's choice.
6. **Run the Reachability / Consumability Trace** (Stage 6) and the **Session-Fit Check** (Stage 7) before final approval. Re-cut features when checks fail — prefer re-slicing over accumulating bridges. The user may also request a **scope-preserving Coarsen** at Candidate Review (Stage 5.5) to reduce feature count without dropping scope — a consented session-fit trade-off recorded as a lease, with the Session-Fit correctness guards still binding. The Session-Fit Check includes the **Interface Foundation Gate** (Stage 7.8): any plan with user-facing features must own a design foundation, detect an existing one, or record a consented exception — never ship UI with no visual contract.
7. **Honor the iteration cap** (Stage 6.6 — at most 3 loops per journey before escalating).
8. **Record user overrides, deferred journeys, and high-risk justifications in Notes.**
9. **Validate every item in the Validation Checklist Before Writing** (in `stage-8-9-write.md`) prior to writing.
10. **Output:** write the final artifact as a plan **directory** at `docs/plans/[project-slug]/` — index `feature-plan.md`, `shared-context.md`, `threat-model.md` (trust boundaries + data-classes + per-feature security obligations, a read-only re-projection of §3 / §6.3 / §7.5), `interaction-contract.md` (cross-feature protocol invariants + architecture-determining NFRs, a read-only re-projection of §3 / §8 / §10 / §6.3 / cited NFRs), one `features/<id>.md` per feature, and `plan.json` — and update `docs/plans/plans.json` (the repo's plan registry). `[project-slug]` is derived per Stage 0 (Project Name Slug). For single-feature plans accepted at the Sizing Gate, use the single-file Recommended Minimal Output instead.
11. **Prefer explicit assumptions over invented details** — when a fact is unknown, record a labeled assumption rather than fabricating specifics.
12. **Keep structured Markdown stable enough for parsing** — downstream tooling reads the artifact; do not break its field structure.
13. **Validate dependency direction programmatically when possible** — hard dependencies must point to an earlier feature in ship order.
14. **Treat unknown build/test commands as planning risk** — surface them; do not assume them.
15. **Do not let high-risk labels become a substitute for better slicing** — a high-risk tag is not a reason to skip re-cutting an oversized feature.
16. **Print a gate locator at every interactive gate** (`Gate N of M — <name>`, per HITL Gate Standard R5). Compute **M from the gates that will actually fire this run** — the Sizing Gate only on a single-feature recommendation, the Iteration-Cap escalation only on non-convergence, the 8.2.1 threat-model attestation as its own gate — so M is computed, never a hardcoded constant; if a conditional gate changes the count mid-run, say so (no silent cap). **In the light-plan tier (item 18 / stage-4-7-gates.md §4.3) M is smaller** — the Candidate Decision folds into Final Approval and, when both re-projections resolve negative, the 8.2.1 + 8.2.2 attestations combine into one (§8.2.3); a positive detection restores a separate gate mid-run, so recompute and say so.
17. **Revise, don't re-plan, when a written plan already exists.** When Stage 0 detects an existing written plan for the slug — an explicit `revise:` argument, a `/ce-patch` text handoff that names the existing plan, a `/ce-spec` structural Boundary Conflict, or a change request against a plan already at `docs/plans/<slug>/` — load `${CLAUDE_SKILL_DIR}/stage-R-revision.md` and run **Stage R** instead of Stages 1–9: diff the delta against the frozen shape, re-run **only** the gates the delta touches (untouched gates are *held from the prior revision*, never re-asked), preserve untouched features' `features/<id>.md` + `specs/<id>/` byte-for-byte, and bump `plan_revision` in `plan.json` (absent = 1). Stage R is the **receiving end** of every downstream "escalate to `/ce-plan` and stop" path. A genuinely new project that merely collides on slug is **not** a revision — disambiguate to a new slug; never silently overwrite a written plan.
18. **Take the light-plan tier for small plans (stage-4-7-gates.md §4.3).** After Stage 3 confirms a **multi-feature** plan of **≤ 3 features** with **no contested Boundary-Owner** and **no `sensitive` data-class** in sight, run the **light-plan tier**: fold the standalone Candidate Decision (5.4) into Final Approval (§5.5 Coarsen becomes moot) and — **when both read-only re-projections resolve negative** — combine the 8.2.1 + 8.2.2 attestations into one (§8.2.3), taking ~8 interactive stops to ~4. This is a **mechanical, disclosed, recorded** proportionality choice (`plan_tier: light` in `plan.json` + §13 Notes), rejectable at 8.3 (*Expand to full gates*) — never a silent skip. The **correctness guards still bind**: Reachability (Stage 6) and Session-Fit (Stage 7) run in full, and **any** positive threat-model / interaction-contract detection restores that re-projection's separate material gate automatically. A plan over 3 features, or one that fails the screen, is **standard tier — unchanged**.

## How to Run This Workflow

**The stage and template files named below are bundled in this skill's own directory.** Read each at `${CLAUDE_SKILL_DIR}/<file>` — `${CLAUDE_SKILL_DIR}` is the environment variable that resolves to this skill's directory regardless of the current working directory. Resolve it once if needed (`ls "${CLAUDE_SKILL_DIR}"`) and read each file by its resulting absolute path; **never load a companion file by bare name** — in an installed plugin the working directory is the user's project, so a bare name finds nothing and triggers a filesystem search.

Execute the stages in order. Load each stage file when you reach it — not before. Each opens with a **Next:** header naming the file to load after it.

| Stages | Load this file | Purpose |
|---|---|---|
| 0–1 | `${CLAUDE_SKILL_DIR}/stage-0-1-understand.md` | Inputs, codebase profile, brownfield friction, decomposition questions |
| 2–3 | `${CLAUDE_SKILL_DIR}/stage-2-3-decompose-score.md` | Draft candidate features; score complexity, risk, boundary ownership |
| 4–7 | `${CLAUDE_SKILL_DIR}/stage-4-7-gates.md` | Sizing Gate, Light-Plan Tier screen (§4.3), Candidate Review, Reachability Trace, Session-Fit Check |
| 8–9 | `${CLAUDE_SKILL_DIR}/stage-8-9-write.md` | Final Plan Review, Validation Checklist, write the artifact, closing |
| R | `${CLAUDE_SKILL_DIR}/stage-R-revision.md` | **Revision path** (only when Stage 0 routes here — a written plan already exists): diff the delta, re-run only the affected gates, preserve untouched specs, bump `plan_revision` |

`${CLAUDE_SKILL_DIR}/stage-8-9-write.md` directs you to **`${CLAUDE_SKILL_DIR}/artifact-template.md`** for the plan directory structure and per-file templates at write time. Do not reconstruct the artifact format from memory.

Stage 0 branches: when a written plan already exists for the slug (Execution Contract item 17), it routes to **Stage R** (`${CLAUDE_SKILL_DIR}/stage-R-revision.md`) — the revision path — instead of the 1–9 from-scratch spine.

To begin: load `${CLAUDE_SKILL_DIR}/stage-0-1-understand.md` and start Stage 0.

---

## Core Concepts

### Feature

A feature is a bounded unit of implementation that can be specified and implemented in one focused session without requiring context compaction.

A valid feature must be either:

- **independently valuable** — it delivers user-visible or stakeholder-visible value, or
- **independently verifiable** — it establishes a technical foundation that can be tested, reviewed, and consumed by later features.

Examples of independently verifiable features:

- authentication foundation
- persistence setup
- API client wrapper
- design-system shell
- observability baseline
- feature-flag infrastructure
- migration framework setup

---

### Feature ID

Feature IDs are provisional until the final plan is approved and written.

During candidate planning, use provisional IDs:

```text
P01-auth-foundation
P02-dashboard-shell
P03-user-profile
```

After final approval, freeze IDs as stable feature slugs:

```text
01-auth-foundation
02-dashboard-shell
03-user-profile
```

Once the plan is written, stable IDs should not be renamed except through an explicit plan revision. (Stable IDs are also the `features/<id>.md` filenames.)

---

### Hard Dependency

A hard dependency means the dependent feature cannot be meaningfully implemented, tested, or shipped before the dependency exists.

Hard dependencies must always point to an earlier feature in ship order.

Example:

```text
03-user-profile has a hard dependency on 01-auth-foundation.
```

---

### Soft Dependency

A soft dependency means the feature is easier, cleaner, or more complete if another feature exists first, but it can still be implemented with a bridge, stub, mock, placeholder, or temporary fallback.

Soft dependencies may point to later features only when the current feature explicitly defines the bridge or fallback that makes this safe.

Example:

```text
02-create-order has a soft dependency on 04-order-history.
The current feature ships a temporary "Order submitted" confirmation page until order history exists.
```

---

### Bridge

A bridge is a temporary implementation that keeps a journey usable until a later feature replaces it.

Examples:

- temporary navigation link
- placeholder page
- simplified confirmation screen
- stubbed integration response
- fallback CLI output
- temporary no-op event publisher

Every bridge must define:

```yaml
bridge:
  description:
  replaces:
  replaced_by:
```

---

### Boundary-Owner

A Boundary-Owner is the single feature that owns a system-wide chokepoint for a concern.

Allowed categories — two families:

**Cross-cutting concern owners** (required only when the concern is present):

```text
security
secrets
persistence
i18n
accessibility
```

**Interface foundation owners** (required when the plan exposes that surface — see the **Interface Foundation Gate**, Stage 7.8; one live surface today, extend on demand):

```text
design-system    # browser surface — design tokens + UI primitives
```

When a plan exposes another foundationed surface, add its category the same way
(e.g. `api-contract` for `http`); do not pre-add an unused category.

A feature should only claim Boundary-Owner when it is the authoritative
implementation point for that concern across the project. An interface-foundation
owner is the single feature that establishes the conventions every feature
touching that surface consumes — including the conformance checker that enforces
them.

A feature that merely touches security, persistence, secrets, i18n, or accessibility is not automatically the Boundary-Owner.

Only one feature per category may claim ownership in a single plan.

---


## Back-Edge Summary

| From | Trigger | To |
|---|---|---|
| Sizing Gate | User selects Adjust | Candidate Feature Decomposition |
| Sizing Gate | User selects Override | Candidate Plan Review |
| Candidate Plan Review | User selects Coarsen | Candidate Feature Decomposition (scope-preserving merge under a consented session-fit lease — §5.5) |
| Candidate Plan Review | User selects Adjust | Candidate Feature Decomposition |
| Candidate Plan Review | User selects Add context | Project Understanding / Candidate Feature Decomposition |
| Reachability Trace | Bridge cost exceeds ceiling | Provisional Ordering or Feature Decomposition |
| Reachability Trace | User selects Reorder | Provisional Ordering |
| Reachability Trace | User selects Adjust journeys | Journey / Consumability Collection |
| Reachability Trace | 3rd loop without convergence | Defer Journey or Abort |
| Session-Fit Check | Dependency failure | Provisional Ordering or Feature Decomposition |
| Session-Fit Check | Sizing failure | Feature Decomposition |
| Session-Fit Check | Boundary-owner conflict | Feature Decomposition |
| Final Plan Review | User selects Adjust | Feature Decomposition or Provisional Ordering |
| Final Plan Review | User selects Add context | Project Understanding / Revalidation |
| Final Plan Review | User selects Expand to full gates (light tier — §4.3) | Candidate Decision (§5.4) + separate 8.2.1/8.2.2 attestations, then Write |
| Final Plan Review | User selects Abort | Exit without writing |

---

## Early-Exit Points

| Point | Trigger | Result |
|---|---|---|
| Sizing Gate | User accepts single-feature recommendation | Single-feature artifact is written |
| Reachability Trace | User aborts after unresolved third loop | Workflow exits without writing |
| Final Plan Review | User selects Abort | Workflow exits without writing |
| Closing | Normal completion | Artifact written and first feature identified |

---

## Gate Checkpoint & Resume

`/ce-plan` writes **nothing durable** before Stage 8.3 Write, so a crash or a context
compaction after the Reachability marathon otherwise loses the entire 9-stage run. To
bound that loss, the workflow keeps a **terse resume transcript** — not the artifact — at:

```text
docs/plans/.drafts/<slug>/scratch.md
```

This scratch is **not** the plan. It is never registered in `plans.json`, never a
`brief:` or spec input, and the leading dot keeps `.drafts/` out of every plan-slug glob.
It exists only so an interrupted run resumes from the last **passed** gate instead of
re-asking settled questions.

**Checkpoint after each passed gate.** Append a checkpoint block to `scratch.md` (creating
`.drafts/<slug>/` on first write) immediately after the run passes each of these gates —
Stage 1.4 (decomposition answers), the Sizing Gate (Stage 4), the Light-Plan Tier screen
(Stage 4.3), the Candidate Decision (Stage 5.4 — **standard tier only**; the light tier's
§4.3 checkpoint is its resume anchor), the Reachability Decision (Stage 6.6), the Session-Fit
Check (Stage 7, after 7.8), and the 8.2.1 / 8.2.2 attestations (**or the one combined 8.2.3
attestation in the light tier**). Each block records only:

```text
## <gate name> — passed
decided_by: human            # or "workflow (autonomous pass)" for a gate that fired no prompt
decision: <the option taken, e.g. "Approve trace" / "Continue" / "Confirm">
state: |
  <the candidate table / journey rows / disposition rows already rendered at the gate,
   verbatim — nothing re-derived>
```

Keep it **terse** — decisions plus the tables already on screen, never a second artifact
shape — so the per-gate write cost stays trivial. A back-edge option (`Adjust`, `Coarsen`,
`Reorder`, …) loops **without** advancing, so it overwrites the pending state rather than
appending a new passed-gate block; only a gate the run actually *passes* appends one. The
newest passed block is the resume point.

**Resume** is offered in Stage 0 (`stage-0-1-understand.md` → *Resume Check*) when a
scratch for the slug already exists: *Resume at the last passed gate / Start fresh (deletes
the scratch) / Abort*. On resume, re-render the last checkpoint's `state` and continue at
the **next** gate — do not replay the codebase profile or re-ask settled questions.

**Lifecycle.** Stage 9 deletes `docs/plans/.drafts/<slug>/` on a **successful** write (the
final artifact now exists). **Abort or crash at any gate leaves the scratch in place** —
that is the entire point: the interrupted run is exactly what resume recovers.

---

## Escalation

Consequential technical forks with no dominant option can route to `/ce-decide`
before the plan is frozen. Downstream Boundary Conflicts return here from `/ce-spec`,
`/ce-implement`, `/ce-review`, `/ce-verify`, or `/ce-debug`; this skill owns scope,
journey reachability, ship order, bridges, and cross-feature migration.


## Honest Limitations

- **Plan-time sizing is approximate.** Complexity and Risk-Profile are estimated from the description, references, user answers, and a **cheap codebase scan** — not from implementation. A feature can still prove larger than sized; the spec stage is where that surfaces (and narrows).
- **Whether a declared dependency is the *real* one is not machine-proven.** Dependency *direction* and *cycle-freedom* now **are** — Stage 9 runs `plan-lint.py` over the just-written plan directory as a write-time gate (H5 direction, H6 acyclicity, plus referential integrity and bridge/re-projection presence), so a Back-Edge or a cycle can no longer ship silently. What the lint cannot judge is whether a dependency the plan *declares* is the one the code actually needs — that still rests on the model's reading plus your review.
- **The codebase profile is a scan, not a study.** For brownfield work it samples structure and conventions cheaply; it can miss a hidden coupling or an undocumented constraint that only the spec / implement stages, working against real code, will hit.
- **Reachability is only as complete as the journeys given.** The Reachability / Consumability Trace checks the journeys you provide; an unstated journey can still ship into a dead end.
- **A plan is a map, not a contract with reality.** It is honored by the downstream stages, which escalate up (`spec → plan`) when map and territory disagree — the plan does not self-correct.
