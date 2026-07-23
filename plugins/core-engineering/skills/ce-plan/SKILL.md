---
name: ce-plan
description: |
  Select a human-approved solution-architecture direction when requirements make it load-bearing, then decompose the project into an ordered feature plan with sizing, risk, reachability, architecture-convergence, and session-fit gates.
  Triggers: plan/decompose/break a project into features. It composes /core-engineering:ce-architecture first in bounded-report explore mode for whole-solution options and later in read-only shape mode to test the provisional cut; use that skill directly for the governed post-plan baseline. /core-engineering:ce-spec details one planned feature at a time.
argument-hint: "[project description]"
allowed-tools: Read, Write, Glob, Grep, Bash, AskUserQuestion, Skill
---

# Plan

**Invocation input:** Project description: $ARGUMENTS


Turn a project description into a human-selected architecture direction when
one is load-bearing, then an ordered, dependency-aware list of implementation
features validated for sizing, risk, reachability, architecture fit, and
session fit. Write the approved result as one planning artifact.

This skill is **staged**. `SKILL.md` (this file) is the orchestrator: it holds the
Execution Contract, Core Concepts, and the stage map. Each stage's detailed
procedure lives in a separate file you load only when you reach that stage — do
not load them all up front.

## Runtime Inputs

- **Project description (required):** provided by the invocation or the
  user's request. If it is empty or missing, ask the user for the project
  description in one short prompt before proceeding. Do not invent a description.
- **Project brief (optional):** a dedicated `brief:` input — `brief=docs/briefs/<slug>.md`
  on the invocation line, or a `brief:` argument when invoked directly (e.g. by `/core-engineering:ce-brief`
  at handoff). Distinct from the project-wide reference-document list, this channel
  arms the **Brief-Aware Skip Contract** in Stage 1.4: the brief's intent answers let
  Stage 1.4 skip what it already covers and ask only the codebase-grounded residue.
- **Optional inputs** (project-wide reference documents, target tool, ordering
  constraints, MVP notes, known risks, environment pitfalls, preferred stack,
  examples, existing conventions): collect interactively per Stage 1 only when
  needed for feature boundaries, ordering, risk, or reachability.

## Execution Contract

Follow the workflow exactly. Do not skip stages, gates, or validation. In particular:

0. **Proportionality Gate — before any profiling spend.** Run Stage 0's *Proportionality Routing* when the supplied request already matches `/core-engineering:ce-patch` admission. It renders the request-shape evidence, historically configured ceilings (never costs/floors/forecasts), attention difference, decision authority, and consequence-labelled patch/plan/route/abort choices. Record the consent; never route silently. A project or multi-feature request passes without a prompt.

1. **Never write the final artifact before the applicable Final Plan Approval** — Stage 4.1.3 `Accept and write the one-feature plan` for the complete minimal-artifact preview, or Stage 8.3 `Write` for a multi-feature plan. These are the only commit points and each follows separate material attestations. Distinct from them is the **gate-checkpoint scratch** at `docs/plans/.drafts/<slug>/scratch.md`: a terse resume transcript appended after each passed gate so a crash or compaction mid-plan resumes from the last passed gate instead of losing the whole 9-stage run (see **Gate Checkpoint & Resume**). The scratch is never the final artifact — it is never registered in `plans.json`, never a `brief:` or spec input, and Stage 9 deletes it on a successful write; appending a checkpoint is **not** writing the artifact early.
2. **Keep provisional IDs (`P01-…`) until write time**; freeze stable IDs only in Stage 9.
3. **Ask grouped questions, not one-by-one** (Stage 1.4 — 4–6 targeted decomposition questions in one logical, same-locator gate; split them into calls of **at most 4 questions each**, then collect references/pitfalls in later calls under that same locator; up to 10–12 decomposition questions total across rounds).
4. **Use the Two-Surface Rendering Rule** (Stage 5.3): print long tables, diagrams, and per-feature blocks in the conversation as Markdown; reserve compact decision dialogs for the short question + options only.
5. **Select architecture before detailed decomposition when it is load-bearing.** After Stage 1 has reconciled intent with repository evidence, load `${CLAUDE_SKILL_DIR}/stage-1a-architecture-direction.md`. Build a coarse `C01` capability map — never provisional features — and classify the stable architecture drivers as `required`, `recommended`, or `not-required`. A required route must pass the Evaluation Frame gate, persist and surface `docs/plans/.drafts/<slug>/architecture-options.md`, and return a fresh, human-owned `direction-selected` result from `/core-engineering:ce-architecture explore:<draft-slug>` before Stage 2. Recommended exploration may be explicitly deferred by the human; not-required records an explicit N/A. A material unknown takes the required path. Stage 3.9 re-screens the detailed candidate before Sizing can exit; a newly required or stale direction returns to Stage 1A and then reruns Stage 2. Required architecture can never collapse into the single-feature minimal shape or light-plan tier.
6. **Converge the selected direction with the candidate before freezing decomposition.** After Candidate Review and before Reachability, a required route invokes `/core-engineering:ce-architecture shape:<draft-slug>` through the `Skill` tool and loads `${CLAUDE_SKILL_DIR}/stage-5a-architecture-convergence.md`. A recommended route, including the light tier, first runs the explicit human shaping election in stage-4-7-gates.md §5.4.1 and records either current convergence or a same-revision defer; absence never becomes implicit deferral. Architecture may propose a paste-ready delta but never edits the plan; this skill and the human alone apply a re-cut. Re-screen after Reachability and after the final TZ/IC attestations. A changed capability or selection binding returns to Stage 1A; a changed candidate revision, driver, decision, journey, dependency, durable-state row, TZ/IC row, or decomposition-shaping NFR invalidates shaping convergence or the recorded defer.
7. **Run the Reachability / Consumability Trace** (Stage 6) and the **Session-Fit Check** (Stage 7) before final approval. Re-cut features when checks fail — prefer re-slicing over accumulating bridges. The user may also request a **scope-preserving Coarsen** at Candidate Review (Stage 5.5) to reduce feature count without dropping scope — a consented session-fit trade-off recorded as a lease, with the Session-Fit correctness guards still binding. The Session-Fit Check includes the **Interface Foundation Gate** (Stage 7.8): any plan with user-facing features must own a design foundation, detect an existing one, or record a consented exception — never ship UI with no visual contract.
8. **Honor both iteration caps:** Stage 6.6 allows at most 3 loops per journey, and architecture shaping allows at most 3 complete results per bounded sequence before it parks at a human cap gate. Only an explicit human-owned scope/evidence change starts another three-pass sequence; `architecture_iteration_count` remains cumulative.
9. **Record user overrides, architecture waivers, deferred journeys, and high-risk justifications in Notes.**
10. **Validate every item in the Validation Checklist Before Writing** (in `stage-8-9-write.md`) prior to writing.
11. **Output:** write the final artifact as a plan **directory** at `docs/plans/[project-slug]/` — index `feature-plan.md`, `shared-context.md`, exact `architecture-selection.json`, the human-readable `architecture-options.md` when directions were explored, `threat-model.md` (trust boundaries + data-classes + per-feature security obligations, a read-only re-projection of §3 / §6.3 / §7.5), `interaction-contract.md` (cross-feature protocol invariants + architecture-determining NFRs, a read-only re-projection of §3 / §8 / §10 / §6.3 / cited NFRs), one `features/<id>.md` per feature, and `plan.json` with the hash-bound `architecture_disposition.direction` — and update `docs/plans/plans.json` (the repo's plan registry). `[project-slug]` is derived per Stage 0 (Project Name Slug). For single-feature plans approved after the separate Stage 4.1.1 security attestation and complete Stage 4.1.2 preview, use the single-file Recommended Minimal Output instead.
12. **Prefer explicit assumptions over invented details** — when a fact is unknown, record a labeled assumption rather than fabricating specifics.
13. **Keep structured Markdown stable enough for parsing** — downstream tooling reads the artifact; do not break its field structure.
14. **Validate dependency direction programmatically when possible** — hard dependencies must point to an earlier feature in ship order.
15. **Treat unknown build/test commands as planning risk** — surface them; do not assume them.
16. **Do not let high-risk labels become a substitute for better slicing** — a high-risk tag is not a reason to skip re-cutting an oversized feature.
17. **Print a gate locator at every interactive gate** (`Gate N of M — <name>`, per HITL Gate Standard R5). Compute **M from the gates that will actually fire this run** — including conditional Stage 0 Proportionality Routing, Existing Plan Routing, Resume Planning, Sibling Plans, and Project Understanding gates; the conditional Stage 1A Evaluation Frame and Architecture Direction Selection gates; the conditional recommended-shaping election; each conditional Architecture-Plan Convergence or architecture iteration-cap gate; the Single-Feature Security Attestation and Single-Feature Final Plan Approval only on a minimal recommendation; the Reachability iteration-cap escalation only on non-convergence; and each applicable 8.2 attestation gate. Same-locator continuations or per-row questions do not increment N or M. Pass the plan's current locator into composed explore/shape calls; a child workflow never starts a competing `Gate 1 of 1` sequence. Never hardcode M; if a conditional gate changes the count mid-run, say so. **In the light-plan tier (item 19 / stage-4-7-gates.md §4.3) M is smaller** because Candidate Decision folds into Final Approval; security and interaction negatives remain separate material questions, while the recommended-shaping election still fires and any late required architecture or positive TZ/IC detection recomputes M.
18. **Revise, don't re-plan, when a written plan already exists.** When Stage 0 detects an existing written plan for the slug — an explicit `revise:` argument, a `/core-engineering:ce-patch` text handoff that names the existing plan, a downstream structural Boundary Conflict, a legacy plan with no `architecture_disposition`, or a change request against a plan already at `docs/plans/<slug>/` — load `${CLAUDE_SKILL_DIR}/stage-R-revision.md` and run **Stage R** instead of Stages 1–9: diff the delta against the frozen shape, re-run **only** the gates the delta touches (untouched gates are *held from the prior revision*, never re-asked), preserve untouched features' `features/<id>.md` + `specs/<id>/` byte-for-byte, and bump `plan_revision` in `plan.json` (absent = 1). Stage R is the **receiving end** of every downstream "escalate to `/core-engineering:ce-plan` and stop" path. A genuinely new project that merely collides on slug is **not** a revision — disambiguate to a new slug; never silently overwrite a written plan.
19. **Take the light-plan tier only when architecture is not required (stage-4-7-gates.md §4.3).** After Stage 3 confirms a **multi-feature** plan of **≤ 3 features** with **no contested Boundary-Owner**, **no `sensitive` data-class**, and architecture applicability other than `required`, run the **light-plan tier**: fold the standalone Candidate Decision into Final Approval, but keep the model-derived No Security Surface and No Cross-Feature Protocol judgments as separate evidence-first questions. This is a disclosed, recorded proportionality choice (`plan_tier: light`); the conditional recommended-shaping election, Reachability, Session-Fit, the late architecture re-screen, and every TZ/IC attestation still bind. If later evidence makes architecture required, restore the standard tier, run Candidate Review and architecture shaping, and recompute the gate manifest.
20. **Name authority at every material gate.** Apply *Material-Gate Decision Authority* below before asking any `[material]` question. A missing decision owner, authority, or load-bearing evidence is a routable gap, never implied consent: keep the prompt within four options and offer the applicable **Need evidence / route to owner** and **Park** paths.

## How to Run This Workflow

**The stage and template files named below are bundled in this skill's own directory.** Read each at `${CLAUDE_SKILL_DIR}/<file>` — `${CLAUDE_SKILL_DIR}` is the environment variable that resolves to this skill's directory regardless of the current working directory. Resolve it once if needed (`ls "${CLAUDE_SKILL_DIR}"`) and read each file by its resulting absolute path; **never load a companion file by bare name** — in an installed plugin the working directory is the user's project, so a bare name finds nothing and triggers a filesystem search.

Execute the stages in order. Load each stage file when you reach it — not before. Each opens with a **Next:** header naming the file to load after it.

| Stages | Load this file | Purpose |
|---|---|---|
| 0–1 | `${CLAUDE_SKILL_DIR}/stage-0-1-understand.md` | Inputs, codebase profile, brownfield friction, decomposition questions |
| 1A | `${CLAUDE_SKILL_DIR}/stage-1a-architecture-direction.md` | Build the coarse capability/evaluation frame; conditionally explore, score, and bind the human-selected architecture direction before features exist |
| 2–3 | `${CLAUDE_SKILL_DIR}/stage-2-3-decompose-score.md` | Draft candidate features; score complexity, risk, boundary ownership |
| 4–7 | `${CLAUDE_SKILL_DIR}/stage-4-7-gates.md` | Sizing Gate, Light-Plan Tier screen (§4.3), Candidate Review, Reachability Trace, Session-Fit Check |
| 5A | `${CLAUDE_SKILL_DIR}/stage-5a-architecture-convergence.md` | **Conditional:** invoke architecture shaping over provisional candidates; route deltas/decisions and record convergence |
| 8–9 | `${CLAUDE_SKILL_DIR}/stage-8-9-write.md` | Final Plan Review, Validation Checklist, write the artifact, closing |
| R | `${CLAUDE_SKILL_DIR}/stage-R-revision.md` | **Revision path** (only when Stage 0 routes here — a written plan already exists): diff the delta, re-run only the affected gates, preserve untouched specs, bump `plan_revision` |

`${CLAUDE_SKILL_DIR}/stage-8-9-write.md` directs you to **`${CLAUDE_SKILL_DIR}/artifact-template.md`** for the plan directory structure and per-file templates at write time. Do not reconstruct the artifact format from memory.

Stage 0 branches: when a written plan already exists for the slug (Execution Contract item 17), it routes to **Stage R** (`${CLAUDE_SKILL_DIR}/stage-R-revision.md`) — the revision path — instead of the 1–9 from-scratch spine.

To begin: load `${CLAUDE_SKILL_DIR}/stage-0-1-understand.md` and start Stage 0.

---

## Material-Gate Decision Authority

Before every gate marked `[material]` (or described as material), render this
short authority block with the evidence shown for that gate:

```text
Decision owner: <person or role accountable for this call, or unknown>
Decision authority: <request, accepted policy/ADR, ownership record, or explicit human mandate>
Authority/evidence gaps: <None, or the exact missing evidence/owner>
```

The current user may decide only when the rendered authority makes that role
clear. Do not infer authority from participation, silence, repository access, or
the ability to invoke the skill. If evidence or authority is incomplete, keep
the current `Gate N of M — <name>` locator and provide an escape path within the
four-option harness limit:

- **Need evidence / route to owner — keep this gate open** — name the exact
  artifact, check, or accountable owner required; gather or route only that
  input, then re-render the same gate without recording a disposition.
- **Park — stop without a final write** — preserve any existing draft scratch
  and evidence so the gate remains resumable when the named input or owner is
  available.

These are controls, not extra approvals. When the primary question already uses
four options, open a same-locator control follow-up (as Stage 1A does) rather
than creating a fifth option. An `Abort` also exits without a final write and
leaves any existing scratch/report in place; only an explicit **Start fresh**
choice deletes draft state.

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
| Architecture Evaluation Frame | User adjusts capabilities, constraints, quality scenarios, criteria, or weights | Stage 1A with incremented capability revision or exploration attempt |
| Architecture exploration | `blocked` or no defensible direction | Park for the named evidence, authority, or experiment; do not enter Stage 2 |
| Architecture direction selection | Human selects or overrides one viable direction | Candidate Feature Decomposition constrained by that exact selected result |
| Architecture direction selection | Human adjusts or parks | Stage 1A retry or exit; do not enter Stage 2 |
| Candidate decomposition / Stage 3.9 | New evidence makes the selected direction absent, stale, or no longer applicable | Stage 1A, then rerun Stage 2 from the fresh direction |
| Single-Feature Final Plan Approval | User selects Adjust scope or decomposition | Candidate Feature Decomposition, then rerun Sizing and the applicable minimal gates |
| Single-Feature Final Plan Approval | User selects Continue with the previewed multi-feature split | Candidate Plan Review and the full correctness gates |
| Candidate Plan Review | User selects Coarsen | Candidate Feature Decomposition (scope-preserving merge under a consented session-fit lease — §5.5) |
| Candidate Plan Review | User selects Adjust | Candidate Feature Decomposition |
| Candidate Plan Review | User selects Add context | Project Understanding / Candidate Feature Decomposition |
| Recommended shaping election | Human elects shaping | Architecture shaping for the exact candidate revision |
| Recommended shaping election | Human defers shaping | Reachability with explicit convergence `deferred`, iteration 0, and visible coverage gap |
| Architecture shaping | `requires-plan-delta` and human accepts | Candidate Feature Decomposition, then re-run affected gates |
| Architecture shaping | `requires-decision` | `/core-engineering:ce-decide`, then re-run shaping from the accepted human decision |
| Architecture shaping | `blocked` or third non-convergent loop | Park for evidence, authority, scope adjustment, or an independently verifiable discovery feature |
| Architecture convergence | Candidate revision or architecture driver changes | Architecture shaping with the new candidate revision |
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
| Final Plan Review | User selects Abort | Exit without a final write; preserve resumable draft state |

---

## Early-Exit Points

| Point | Trigger | Result |
|---|---|---|
| Single-Feature Final Plan Approval | User accepts the separately attested, complete minimal preview | Single-feature artifact is written |
| Reachability Trace | User aborts after unresolved third loop | Workflow exits without a final write and preserves resumable draft state |
| Final Plan Review | User selects Abort | Workflow exits without a final write and preserves resumable draft state |
| Closing | Normal completion | Artifact written and first feature identified |

---

## Gate Checkpoint & Resume

`/core-engineering:ce-plan` writes no **final plan** before the applicable commit
gate: Single-Feature Final Plan Approval (§4.1.3) or Stage 8.3 Write. Before then
it keeps only bounded draft inputs, the pre-approval architecture-options
report when exploration runs, selected-result JSON, and a **terse resume transcript**
so a crash or context compaction does not lose the entire 9-stage run. The transcript lives at:

```text
docs/plans/.drafts/<slug>/scratch.md
```

This scratch is **not** the plan. It is never registered in `plans.json`, never a
`brief:` or spec input, and the leading dot keeps `.drafts/` out of every plan-slug glob.
It exists only so an interrupted run resumes from the last **passed** gate instead of
re-asking settled questions.

**Checkpoint after each passed gate.** Append a checkpoint block to `scratch.md` (creating
`.drafts/<slug>/` on first write) immediately after the run passes each of these gates —
Stage 1.4 (project-understanding answers), the Stage 1A Evaluation Frame and Architecture
Direction Selection when they fire (or its explicit recommended-deferred / not-required
N/A checkpoint), the Single-Feature Security Attestation when the minimal route
fires, the Sizing Gate (Stage 4) when the run continues multi-feature, the Light-Plan Tier screen
(Stage 4.3), the Candidate Decision (Stage 5.4 — **standard tier only**; the light tier's
§4.3 checkpoint is its resume anchor), the Recommended Architecture Shaping election
(§5.4.1 when it fires in either tier), Architecture-Plan Convergence (Stage 5A when it
fires), the Reachability Decision (Stage 6.6), the Session-Fit
Check (Stage 7, after 7.8), and the applicable 8.2.1 / 8.2.2 attestations. The
light tier keeps their negative judgments as separate questions and checkpoints.
Each block records only:

```text
## <gate name> — passed
decided_by: human            # or "workflow (autonomous pass)" for a gate that fired no prompt
decision: <the option taken, e.g. "Approve routine rows and continue" / "Continue" / "Confirm this row">
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
the **next** gate — do not replay the codebase profile or re-ask settled questions. For an
interrupted Architecture Direction Selection, inspect both draft companions. A
report without `architecture-selection.json` proves only what was shown: retain
it as audit evidence, increment `exploration_attempt`, and replace it through a
fresh explore pass before asking. When schema-v2 selection JSON and its sibling
report both exist, run the current-schema linter; only a PASS may reconstruct
the missing passed-gate checkpoint from their exact human selection and report
hash and continue without re-asking. Any mismatch parks or starts a fresh
attempt; an `awaiting-selection` report alone is never inferred approval.

**Lifecycle.** Stage 9 first copies the immutable pre-approval options report into the final plan
when exploration ran, then deletes `docs/plans/.drafts/<slug>/` on a **successful**
write. **Abort or crash at any gate leaves the scratch and report in place** — the
interrupted run is exactly what resume recovers.

---

## Escalation

Whole-solution direction generation, scoring, and the one bounded pre-approval
report write are delegated to `/core-engineering:ce-architecture explore:<draft-slug>`
before detailed decomposition;
candidate coherence is delegated read-only to its `shape:<draft-slug>` mode afterward.
This skill retains sole write authority over the exploration input, selected-result
JSON/checkpoint, final report publication, and decomposition. A single bounded consequential fork can route to
`/core-engineering:ce-decide`; it does not replace whole-solution exploration. Downstream
Boundary Conflicts return here from `/core-engineering:ce-spec`,
`/core-engineering:ce-implement`, `/core-engineering:ce-review`, `/core-engineering:ce-verify`, or `/core-engineering:ce-debug`; this skill owns scope,
journey reachability, ship order, bridges, and cross-feature migration.


## Honest Limitations

- **Plan-time sizing is approximate.** Complexity and Risk-Profile are estimated from the description, references, user answers, and a **cheap codebase scan** — not from implementation. A feature can still prove larger than sized; the spec stage is where that surfaces (and narrows).
- **Whether a declared dependency is the *real* one is not machine-proven.** Dependency *direction* and *cycle-freedom* now **are** — Stage 9 runs `plan-lint.py` over the just-written plan directory as a write-time gate (H5 direction, H6 acyclicity, plus referential integrity and bridge/re-projection presence), so a Back-Edge or a cycle can no longer ship silently. What the lint cannot judge is whether a dependency the plan *declares* is the one the code actually needs — that still rests on the model's reading plus your review.
- **The codebase profile is a scan, not a study.** For brownfield work it samples structure and conventions cheaply; it can miss a hidden coupling or an undocumented constraint that only the spec / implement stages, working against real code, will hit.
- **Architecture option scores are decision support, not proof of a best design.** Stage 1A binds every criterion to stated requirements or repository evidence, hard-gates constraints, and preserves confidence/sensitivity gaps, but the weighting and synthesis remain judgments. The human selects the direction; a changed capability or evidence fingerprint invalidates it.
- **Reachability is only as complete as the journeys given.** The Reachability / Consumability Trace checks the journeys you provide; an unstated journey can still ship into a dead end.
- **Pre-freeze architecture convergence is a reasoned shaping check, not an accepted-for-specification architecture package.** Stable feature IDs, plan hashes, final diagrams, and the governed architecture acceptance receipt exist only after the written plan is passed to `/core-engineering:ce-architecture`; a hidden coupling can still force Stage R.
- **A plan is a map, not a contract with reality.** It is honored by the downstream stages, which escalate up (`spec → plan`) when map and territory disagree — the plan does not self-correct.
