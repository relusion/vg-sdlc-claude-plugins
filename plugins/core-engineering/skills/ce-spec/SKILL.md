---
name: ce-spec
description: |
  Turn ONE planned feature into an implementation-ready spec — resolve unknowns, EARS acceptance criteria → tagged test cases, design against the real codebase, an ordered tasks.json — without widening the planned boundary (Scope Lock).
  Triggers: spec/specify/detail one planned feature for implementation. /core-engineering:ce-plan owns decomposition and the architecture disposition; /core-engineering:ce-architecture owns the conditionally required cross-feature solution baseline; /core-engineering:ce-spec owns feature-local design.
argument-hint: "[feature-id]"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion, Skill
---

# Spec

**Invocation input:** Feature to specify: $ARGUMENTS


Turn one planned feature into an implementation-ready specification.

The feature comes from a plan directory produced by `/core-engineering:ce-plan`
(`docs/plans/[slug]/`). This workflow closes the four gaps the plan
deliberately left open:

1. **Resolve unknowns** — turn the feature's open questions into recorded decisions.
2. **Make scope testable** — turn Scope into acceptance criteria and test cases.
3. **Design against the real codebase** — replace plan-time assumptions with a concrete design.
4. **Produce an executable task list** — ordered, verifiable tasks ready to implement.

It does this **without expanding the planned boundary**, and with **a human
owning every judgment call**. The spec is done when a competent implementer can
execute the task list with no further design decisions.

This skill is **staged**. `SKILL.md` (this file) is the orchestrator: it holds the
Runtime Inputs, Execution Contract, the always-on disciplines (Scope Lock,
Tiered HITL, ADR rules, the Mechanical Lint Gate), and the stage map. Each stage's
detailed procedure loads on demand — see *How to Run This Workflow* below.

## Runtime Inputs

- **Feature id (required):** e.g. `03-user-profile`, or the qualified form
  `<plan-slug>/03-user-profile` for explicit selection. Provided by the invocation
  or the user's request. If missing, read `docs/plans/plans.json` (the plan
  registry), list the features under each plan, and ask which to specify. Do not
  guess.
- **The plan directory:** resolve via the registry. An unqualified id that
  matches exactly one full plan's `features/<id>.md` or one minimal plan's
  explicit `Feature ID` is unambiguous; if it matches more than one, ask which.
- **Plan shape (auto-detected):** a full plan loads `features/<id>.md`,
  `shared-context.md`, `feature-plan.md`, and `plan.json`. A registry-backed
  single-feature minimal plan intentionally has no `plan.json`,
  `shared-context.md`, or `features/` directory: its regular, non-symlink
  `feature-plan.md` is the sole plan authority. Minimal mode is valid only when
  its `## 4. Single Feature` block has exactly one explicit
  `Feature ID: <id>` and exactly one qualified
  `Run: /core-engineering:ce-spec <slug>/<id>` line, and those values agree with
  the registry, invocation, and plan directory. Ambiguous or mismatched identity
  routes to `/core-engineering:ce-plan` for repair; never infer the id from a
  title or directory name. Set `plan_mode: single-feature-minimal` for the
  downstream N/A dispositions below; otherwise use full-plan behavior.
- **Loaded automatically for a full plan:** `threat-model.md` (this feature's
  **Per-Feature Security Obligations** — the `TZ-NNN` threat-ids §2.1 derives
  `[SECURITY]` criteria from, and the trust boundaries / data-classes its design
  must honor; absent ⇒ no security obligations for this feature),
  `interaction-contract.md` (this feature's **Per-Feature Interaction Obligations** —
  the `IC-NNN` behavioural-protocol invariants and architecture-determining NFRs §2.1
  derives `[CONTRACT]` criteria from; absent ⇒ no interaction obligations for this
  feature), the plan's required **`architecture_disposition`** (decision,
  triggers, rationale, human owner, convergence result, and accepted-ADR
  `decision_refs`), and any **approved architecture package** under
  `architecture/`. Stage 0 validates the full plan before interpreting the
  disposition and validates every present package before use. A
  `required` + `converged` disposition blocks specification until that package
  is present and current; `recommended`, `not-required`, and `waived` absence
  remain visible with their exact rationale. A valid package's feature mapping,
  components, plan-owned data and lifecycle mappings, flows, and quality
  scenarios are design context while accepted ADRs remain the binding decision
  records. Also load each hard
  dependency's `specs/<dep>/ce-spec.md` (or its built code), the project docs listed
  in `shared-context.md`, the accepted ADRs in `docs/adr/` relevant to this
  feature — opened individually via the Resolved Project Decisions ledger index
  when their decisions bear on this feature's surfaces (see Stage 3.1), not the
  whole directory — and the `shared-context.md` of every plan in this plan's
  `relates_to` (their ledger entries become readable defaults — see Stage 1.2).
  In minimal mode these full-plan, dependency, cross-feature, and architecture
  inputs are `N/A by construction`; use the Scope, Excluded, Open Unknowns,
  Validation Target, Project Context, Codebase Profile, and Notes recorded in
  the sole `feature-plan.md`. Discovery of any dependency or cross-feature
  obligation disproves the minimal shape and routes to planning before design.

## Execution Contract

Follow the workflow exactly. Do not skip stages, gates, or validation.

*Gate locator (HITL R5):* print `Gate N of M — <name>` at every interactive gate; compute M from the gates that actually fire this run, never a hardcoded constant.

*Proportionality:* invoked **ad hoc** (no plan behind the request) on a patch-shaped change — one bounded behavior, no new durable state, no cross-feature surface — offer `/core-engineering:ce-patch` before authoring a full spec, stating the cost difference. A **planned** feature is never silently re-routed: if it turns out patch-sized, say so and route the observation back to the plan's Sizing Gate; the Scope Lock still governs this run.

1. **Never write the spec before Final Approval** (Stage 5.4 → `Write`).
2. **Honor the Scope Lock** (below). Scope changes only through an approved, logged Boundary Conflict — never silently.
3. **Tiered human-in-the-loop** (below). Every judgment call is the human's. Default to asking; never assume silently.
4. **Enforce the architecture disposition** (Stage 0.1) before feature design. A
   missing, malformed, or non-converged required disposition routes to
   `/core-engineering:ce-plan` Stage R. A `required` + `converged` disposition
   without a current approved package routes to
   `/core-engineering:ce-architecture <slug>` and stops. A recommended gap or
   human waiver is context to surface, never authority to invent cross-feature
   design.
5. **Enforce dependency order** (Stage 0.2). Do not proceed unless every hard dependency is specced or built. For a valid single-feature minimal plan, record dependency order `N/A by construction`; discovering a dependency routes to planning.
6. **Maintain traceability:** Scope item → Acceptance Criterion → Test Case → Task, and every journey step this feature owns → ≥ 1 Test Case (carrying the step's modality). No orphans at any link. A minimal plan has no Journey Map, so only the Scope chain applies unless planning expands the shape.
7. **Stay focused.** Scale effort to feature size — a Simple feature with no unknowns runs light. Do not manufacture ceremony. The artifact template's **Tier-scaling** rule names which `ce-spec.md` sections such a feature omits (omit the empty section, never the analysis); `spec-lint` H1–H5 still pass on the reduced spec.
8. **Log every decision** with its options, choice, rationale, tier, and `decided_by: human`. Propagate cross-feature resolutions — architecturally-significant ones to a project ADR, others to the shared-context ledger (Stage 5.2). Minimal mode has no shared ledger: a cross-feature resolution invalidates that mode and routes to planning rather than creating a missing artifact from inside spec.
9. **Run the Mechanical Lint Gate** (below) before Final Approval — auto-build runs the same script as a blocking spec-artifact gate.
10. **Output:** write `ce-spec.md` and `tasks.json` to `docs/plans/[slug]/specs/<id>/`.

## Scope Lock — the planned feature boundary

The feature's **Scope** and **Excluded** lists, from `features/<id>.md` in a full
plan or the `## 4. Single Feature` block in a minimal plan, are the frozen
boundary. Three invariants:

- **Frozen.** Every unknown resolution, acceptance criterion, test case, design
  element, and task is **boundary-checked** — it must trace up to a Scope item, and
  must not cover an Excluded item or unplanned scope.
- **Narrow, never widen.** The spec may **narrow** within boundary (defer something
  as a recorded, signed-off limitation) but never **widen** it on its own.
- **Structural changes escalate and stop.** The spec edits **only this feature's
  authority** (`features/<id>.md`, or the minimal plan's Single Feature block),
  and only **local** fields: Scope, Excluded, surfaces, open unknowns,
  validation target. Anything **structural** — dependencies, IDs, ship order,
  impact on other features, or a **new cross-feature flow the plan never traced**
  (§3.6) — is beyond a single feature edit: escalate to a plan
  revision (`/core-engineering:ce-plan`) and stop.

Scope changes only via a **Boundary Conflict**, applied to `features/<id>.md` or
the minimal plan's Single Feature block by the canonical procedure in **Stage
3.3** (detect → present as *material* → human approves → stamp/log the revision
in the owning plan artifact). Never widen Scope to absorb a conflict.

## Human-in-the-Loop — tiered

The workflow does the legwork — research, drafting, checks. **The human owns
every judgment call.** The workflow recommends; it never commits a judgment call
without the human selecting.

Tag each judgment call **material** or **routine**, and show the reason:

- **Material → explicit decision prompt.** A call is material if it affects Scope
  or the boundary; affects architecture or a cross-cutting concern (a
  reviewer-trigger — auth, secrets, persistence, i18n, accessibility,
  security-sensitive data, migration); is a Boundary Conflict or a feature-file
  edit; or is a genuine tradeoff with no dominant option.
- **Routine → bulk approve-with-veto.** Wording refinements, mechanical task
  splits, test-case enumeration for an already-approved criterion, an unknown
  where one option clearly dominates with contained impact. List routine items
  together and ask once; the human may pull any item up into an explicit decision.

Approval is always an affirmative action — never silence or assumption.

**Decision prompt format.** Print the analysis as Markdown first, then use the
`AskUserQuestion` tool for the choice itself:

```text
Decision [D-n] — <short title>   [material]
Context:   <1–3 sentences>
Question:  <the question>
Options:
  A. <option> — <consequence>
  B. <option> — <consequence>
Recommendation: <A/B> — <reasoning>
```

Record every decision: id, question, options, choice, rationale, tier,
`decided_by: human`. These become the spec's **Resolved Decisions** and
**Boundary-Conflict Log**.

**Escalating a hard fork to `/core-engineering:ce-decide` (optional, human-triggered).** When a material
decision has **no dominant option** *and* is genuinely consequential — a **one-way door**
(an irreversible schema / contract / data choice), a **wide or cross-feature blast
radius**, or a choice that hinges on a **load-bearing unmeasured number** — the single
`Recommendation: <A/B>` line is too thin to carry it. The human may escalate *that one
decision* to `/core-engineering:ce-decide` for a situation-weighted, evidence-tagged scorecard
(gate-then-weight + a falsifiable DEAD-IF). `/core-engineering:ce-decide` **drafts** a proposed ADR that flows
back through the ADR-promotion path below — the human promotes it and the Resolved
Decisions entry references it (`see ADR-NNNN`); no new artifact shape. This is a **rigorous
upgrade of the Recommendation line, not a replacement**: where one option dominates (the
common case), stay inline — do not manufacture a scorecard. The escalation is always the
human's call, never automatic, and the **Scope Lock still binds** — a fork that changes
*scope* is a Boundary Conflict to `/core-engineering:ce-plan`, not a `/core-engineering:ce-decide`.

## Architecture Decision Records

Most decisions this workflow makes are feature-local — they live in the spec's
Resolved Decisions. A few are not: they are **architecturally significant** (they
shape structure, a technology choice, or a cross-cutting concern) **and
cross-feature** (a later feature's spec will need them). Examples: token format
and lifetime, the concurrency-control strategy, an event-sourcing choice.

When a material decision meets **both** tests — and after the human approves it,
confirming it is ADR-worthy (itself a material call) — promote it to a
project-level **ADR**:

- Write `docs/adr/NNNN-short-title.md` (next free 4-digit number) in Nygard
  format: **Context · Decision · Status · Consequences**. `Status` starts
  `accepted`. In **Context**, cite the qualified origin —
  `<plan-slug>/<feature-id>` — so a reader a year from now can trace which plan
  and feature surfaced the decision.
- The spec's Resolved Decisions entry then **references** the ADR (`see ADR-NNNN`)
  rather than restating it.
- Keep the bar high — feature-local decisions stay in the spec. ADR sprawl is the
  failure mode.

ADRs are durable project knowledge: they live in `docs/adr/` with the code, not
in the plan directory. If an ADR supersedes an earlier one, set the old one's
`Status: superseded by ADR-NNNN`.

## Mechanical Lint Gate

Before Final Approval, check the **mechanical** traceability invariants on-disk
rather than by eye — a blocking gate that **supplements** the human Validation
Checklist (Stage 5.3), never replaces it. The final artifact is not written until
Stage 5.5, so assemble `ce-spec.md` + `tasks.json` to a **scratch** directory and lint
that:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/spec-lint.py" <scratch-dir> \
  --threat-model docs/plans/<slug>/threat-model.md --feature <id>   # enables H5 when present
```

Pass `--threat-model` **and** `--feature <id>` here: the scratch dir is outside the
canonical `specs/<id>/` layout, so spec-lint can neither auto-discover the
threat-model nor infer the feature id from the path — give it both explicitly. (The
auto-build orchestrator needs neither flag — it lints the real `specs/<id>/`, where
both are auto-discovered.)

For a single-feature minimal plan, omit both `--threat-model` and `--feature`:
the absent threat model is an intentional `N/A`, while H1–H4 still validate the
normal `ce-spec.md` + `tasks.json` output. Do not manufacture full-plan files to
enable H5.

It checks (H1–H4, and **H5** when `--threat-model` is passed): every `tasks.json`
`verifies` resolves to a real TC; every TC carries a `modality:` and a
`verification:` tag, with `manual` modality paired to `manual:judgment`; no orphan
task or TC; and every `TZ-NNN` the threat-model assigns this feature is covered by a
`[SECURITY: TZ-NNN]` AC. Pass `--threat-model` whenever the plan has one — omit it
and H5 is simply N/A (no false fail on a plan without a threat-model). Disposition:

- **PASS (exit 0)** → annotate the items it covers in Stage 5.3 as **`[machine-verified]`**.
  They **stay in the checklist** — the lint *supplements* the gate, it never removes a check.
- **FAIL (exit 1)** → a **material finding**: surface each failure; fix and re-lint,
  or record an explicit human acknowledgement. Do **not** reach Final Approval (5.4)
  on an unacknowledged FAIL.
- **Could-not-run (exit 2)** → fall back to full manual self-attestation in Stage 5.3 and
  **say so loudly** ("spec-lint did not run — checklist verified by hand"). Never silently skip.

The lint covers only the mechanical subset; the judgment items in Stage 5.3 (is a
`manual:judgment` genuinely un-automatable, is the boundary right) stay the human's.
auto-build runs this same script as a **blocking** spec-artifact gate.

---

## Autonomous Mode

When invoked by `/core-engineering:ce-auto-build`, load `${CLAUDE_SKILL_DIR}/autonomous-mode.md` and apply it before Stage 0; outside autonomous mode, the Tiered HITL gates in this file apply as written.

---

## How to Run This Workflow

**The stage and template files named below are bundled in this skill's own directory.** Read each at `${CLAUDE_SKILL_DIR}/<file>` — `${CLAUDE_SKILL_DIR}` is the environment variable that resolves to this skill's directory regardless of the current working directory. Resolve it once if needed (`ls "${CLAUDE_SKILL_DIR}"`) and read each file by its resulting absolute path; **never load a companion file by bare name** — in an installed plugin the working directory is the user's project, so a bare name finds nothing and triggers a filesystem search.

Execute the stages in order. Load each stage file when you reach it — not before.
Each stage file opens with a **Next:** header naming the file to load after it.

| Stages | Load this file | Purpose |
|---|---|---|
| 0–1 | `${CLAUDE_SKILL_DIR}/stage-0-1-frame-resolve.md` | Frame the feature; resolve open unknowns (Gap 1) |
| 2–3 | `${CLAUDE_SKILL_DIR}/stage-2-3-testable-design.md` | Make scope testable — EARS + conformance (Gap 2); design against the codebase (Gap 3) |
| 4–5 | `${CLAUDE_SKILL_DIR}/stage-4-5-tasks-write.md` | Build the task list (Gap 4); assemble, triage, lint, approve, write |

At the write step, `${CLAUDE_SKILL_DIR}/stage-4-5-tasks-write.md` directs you to **`${CLAUDE_SKILL_DIR}/artifact-template.md`**
for the `ce-spec.md` + `tasks.json` formats and to the **Mechanical Lint Gate** above.
Do not reconstruct the artifact format from memory.

When Stage 2.1 reaches a feature that renders a user-facing surface, it directs you to **`${CLAUDE_SKILL_DIR}/surface-critique.md`** — the canonical definition of the **Surface Critique** discipline (the six-dimension rubric, the functional-vs-taste classifier, the three-tier evidence model, the canvas-vs-DOM honesty) that the Surface-Quality criteria authored here are later checked against by `/core-engineering:ce-implement`, `/core-engineering:ce-verify`, `/core-engineering:ce-auto-build`, and the UX skills.

To begin: load `${CLAUDE_SKILL_DIR}/stage-0-1-frame-resolve.md` and start Stage 0.

---

## Back-Edge Summary

| From | Trigger | To |
|---|---|---|
| Stage 0.4 | Boundary needs revision | Escalate to `/core-engineering:ce-plan` |
| Stage 2 | New unknown surfaces | Stage 1 |
| Stage 3.3 | Local Boundary Conflict, approved | Stage 1 or Stage 2 |
| Stage 3.3 | Structural Boundary Conflict | Escalate to `/core-engineering:ce-plan` |
| Stage 3.5 | Breaking shared-shape change | Boundary Conflict → escalate to `/core-engineering:ce-plan` |
| Stage 3.6 | New cross-feature flow the plan never traced | Boundary Conflict → escalate to `/core-engineering:ce-plan` |
| Stage 4.3 | Orphan task reveals missing scope | Stage 3.3 (Boundary Conflict) |
| Stage 5.4 | User selects Adjust | Relevant earlier stage |
| Any stage | User selects Abort | Exit without writing |

Allow at most ~3 loops on any one decision before escalating to the human.

---

## Escalation

Boundary revisions, breaking shared-shape changes, and new cross-feature flows
(§3.3 / §3.5 / §3.6) escalate to `/core-engineering:ce-plan` **Stage R**, which revises the existing
plan in place — diffing the delta against the frozen shape and re-running only the
affected gates — rather than re-planning from scratch. Technical forks with no dominant
option may route to `/core-engineering:ce-decide`. Implementation infeasibility returns here from
`/core-engineering:ce-implement` as a Spec Conflict; this skill narrows the contract and never widens the plan.

## Honest Limitations

- **Designs, does not build.** Produces an implementation-ready spec + task list; it writes no production code and runs no tests. Whether the design survives contact with the real code is `/core-engineering:ce-implement`'s to prove (a Spec Conflict escalates back here).
- **Narrows, never widens.** Bound by the feature's planned Scope / Excluded (the Scope Lock): it can defer within boundary but cannot grow it — a structural change escalates to `/core-engineering:ce-plan` and stops. The spec is only as right as the plan it refines.
- **The human owns every judgment call.** Material decisions are the human's; the workflow recommends and never commits a judgment silently. Its "done" means *executable without further design decisions*, not *correct* — correctness is verified downstream.
- **Shares the model's blind spots.** Unknowns are resolved by research and reasoning on the same model that will later help implement them; an error shared across both can pass into the spec unflagged.
- **Spec §8 is the artifact's limits, not the skill's.** The `Assumptions & Limitations` section inside the emitted `ce-spec.md` records *that feature's* caveats — distinct from these limits of the spec **process** itself.
