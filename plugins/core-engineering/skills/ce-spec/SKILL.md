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

It does this **without expanding the planned boundary**. The workflow derives
routine wording, trace links, and task splits from repository evidence; humans
own substantive boundary, adequacy, security, architecture, and irreversible
decisions. The spec is done when a competent implementer can execute the task
list with no further design decisions.

This skill is **staged**. `SKILL.md` (this file) is the orchestrator: it holds the
Runtime Inputs, Execution Contract, the always-on disciplines (Scope Lock,
Tiered HITL, ADR rules, the Mechanical Lint Gate), and the stage map. Each stage's
detailed procedure loads on demand — see *How to Run This Workflow* below.

## Runtime Inputs

- **Feature id (required):** e.g. `03-user-profile`, or qualified
  `<plan-slug>/03-user-profile`. Resolve it through `docs/plans/plans.json` and
  `features/<id>.md`; ask only when an unqualified id matches multiple plans.
- **Canonical plan directory:** load `plan.json`, `feature-plan.md`,
  `features/<id>.md`, `shared-context.md`, and
  `architecture-selection.json`. A missing, mixed, symlinked, or mismatched
  authority is a planning defect; do not infer identity from titles or directory
  names.
- **Specification route:** read the exact
  `plan.json.features[].specification_route` value. It is the machine authority;
  require one matching `**Specification route:** compact|explicit` Markdown
  projection. Missing, duplicate, or mismatched values return to Plan Stage R.
  `explicit` is the normal interactive workflow. `compact` may use the
  caller-only composition mode below; it does not relax the artifact or lint
  contract.
- **Loaded automatically:** `threat-model.md` (this feature's
  **Per-Feature Security Obligations** — the `TZ-NNN` threat-ids §2.1 derives
  `[SECURITY]` criteria from, and the trust boundaries / data-classes its design
  must honor; absent ⇒ no security obligations for this feature),
  `interaction-contract.md` (this feature's **Per-Feature Interaction Obligations** —
  the `IC-NNN` behavioural-protocol invariants and architecture-determining NFRs §2.1
  derives `[CONTRACT]` criteria from; absent ⇒ no interaction obligations for this
  feature), the plan's required **`architecture_disposition`** (decision,
  triggers, rationale, human owner, convergence result, and accepted-ADR
  `decision_refs`), and any published **accepted-for-specification architecture
  package** under
  `architecture/`. Stage 0 validates the full plan before interpreting the
  disposition and validates every present package before use. A
  selected + `converged` `required` or `recommended` disposition blocks
  specification until that package is present and current; explicitly deferred
  `recommended` and `not-required` absence remain visible with their exact
  rationale. A valid package's feature mapping,
  components, plan-owned data and lifecycle mappings, flows, and quality
  scenarios are design context while accepted ADRs remain the binding decision
  records. Also load each hard
  dependency's `specs/<dep>/ce-spec.md` (or its built code), the project docs listed
  in `shared-context.md`, the accepted ADRs in `docs/adr/` relevant to this
  feature — opened individually via the Resolved Project Decisions ledger index
  when their decisions bear on this feature's surfaces (see Stage 3.1), not the
  whole directory — and the `shared-context.md` of every plan in this plan's
  `relates_to` (their ledger entries become readable defaults — see Stage 1.2).

## Execution Contract

Follow every applicable stage and validation. Interactive gates fire only for
the decisions named below; a deterministic PASS or an unambiguous derived row is
reported, not turned into a question.

*Gate locator (HITL R5):* print `Gate N of M — <name>` at every interactive gate; compute M from the gates that actually fire this run, never a hardcoded constant.

*Proportionality:* invoked **ad hoc** (no plan behind the request) on a patch-shaped change — one bounded behavior, no new durable state, no cross-feature surface — offer `/core-engineering:ce-patch` before authoring a full spec, stating the cost difference. A **planned** feature is never silently re-routed: if it turns out patch-sized, say so and route the observation back to the plan's Sizing Gate; the Scope Lock still governs this run.

1. **Write authority.** Direct `explicit` runs write only after Final Approval
   (Stage 5.4 → `Write`). Caller-validated compact composition may write after a
   clean non-waivable lint only when it found no substantive decision.
2. **Honor the Scope Lock** (below). Scope changes only through an approved, logged Boundary Conflict — never silently.
3. **Selective human-in-the-loop** (below). Ask only when repository evidence
   cannot settle a substantive boundary or adequacy decision.
4. **Enforce the architecture disposition** (Stage 0.1) before feature design. A
   missing, malformed, or non-converged required disposition routes to
   `/core-engineering:ce-plan` Stage R. A `required` + `converged` disposition
   without a current published accepted-for-specification package routes to
   `/core-engineering:ce-architecture <slug>` and stops. An explicitly deferred
   recommendation is context to surface, never authority to invent
   cross-feature design.
5. **Enforce dependency order** (Stage 0.2). Do not proceed unless every hard dependency is specced or built.
6. **Maintain traceability:** Scope item → Acceptance Criterion → Test Case → Task, and every journey step this feature owns → ≥ 1 Test Case (carrying the step's modality). No orphans at any link.
7. **Stay focused.** Scale effort to feature size — a Simple feature with no unknowns runs light. Do not manufacture ceremony. The artifact template's **Tier-scaling** rule names which `ce-spec.md` sections such a feature omits (omit the empty section, never the analysis); `spec-lint` H1–H7 still pass on the reduced spec.
8. **Log substantive decisions** with options, choice, rationale, tier, and
   `decided_by: human`. Record material repository-derived defaults as
   `decided_by: agent` with their evidence; do not manufacture decision rows for
   mechanical wording or trace generation. Propagate cross-feature resolutions
   only through the existing ADR/ledger routes.
9. **Run the Mechanical Lint Gate** (below) before Final Approval — auto-build runs the same script as a blocking spec-artifact gate.
10. **Output:** write `ce-spec.md` and `tasks.json` to `docs/plans/[slug]/specs/<id>/`.

## Scope Lock — the planned feature boundary

The feature's **Scope** and **Excluded** lists in `features/<id>.md` are the
frozen boundary. Three invariants:

- **Frozen.** Every unknown resolution, acceptance criterion, test case, design
  element, and task is **boundary-checked** — it must trace up to a Scope item, and
  must not cover an Excluded item or unplanned scope.
- **Narrow, never widen.** The spec may **narrow** within boundary (defer something
  as a recorded, signed-off limitation) but never **widen** it on its own.
- **Structural changes escalate and stop.** The spec edits **only
  `features/<id>.md`**, and only local fields: Scope, Excluded, surfaces, open unknowns,
  validation target. Anything **structural** — dependencies, IDs, ship order,
  impact on other features, or a **new cross-feature flow the plan never traced**
  (§3.6) — is beyond a single feature edit: escalate to a plan
  revision (`/core-engineering:ce-plan`) and stop.

Scope changes only via a **Boundary Conflict**, applied to
`features/<id>.md` by the canonical procedure in **Stage 3.3** (detect →
present as material → human approves → stamp/log the revision). Never widen
Scope to absorb a conflict.

## Human-in-the-Loop — tiered

The workflow asks only for a substantive choice:

- changing or interpreting the Scope Lock when evidence does not yield one safe
  reading;
- product or acceptance-criterion adequacy with no dominant answer;
- security, privacy, external-contract, cross-feature, ADR, destructive, or
  irreversible decisions;
- classifying a genuinely subjective case as `manual:judgment`; or
- final acceptance of an explicit spec.

Routine wording, test enumeration, trace links, and mechanical task splits are
derived, recorded with evidence where useful, and presented in the final diff.
Do not ask the human to confirm a lint PASS or a repository fact already
demonstrated. Silence never resolves a substantive decision.

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

Record each prompted decision with `decided_by: human`. A dominant,
repository-derived engineering default may be recorded as `decided_by: agent`
with its evidence and reversal path; it is not an approval event.

## Compact Composition — caller-validated

`/core-engineering:ce-implement` may request compact composition only when
`ce-spec.md` and `tasks.json` are absent and the manifest route is `compact`.
Re-run the planning screen as a drift guard. Compact is disqualified when:

- `final_complexity` is `Complex`;
- a security/privacy obligation or security reviewer trigger is present;
- the feature owns or changes an external/public API, CLI, event, schema, or
  configuration contract;
- a hard-dependency interface is unresolved;
- the feature owns or changes a cross-feature flow, shared shape, or interaction
  contract;
- material migration, concurrency, failure, compatibility, destructive, or
  irreversible design remains;
- any product, scope, boundary, acceptance-adequacy, or `manual:judgment`
  decision remains, or behavior, acceptance, test location, validation
  commands, and a small ordered task cut are not all known.

A stable built dependency or already selected architecture direction does not
disqualify compact by itself. If current facts no longer support the manifest
route, stop and return to Plan Stage R; do not silently switch routes.

When eligible, run the same stages in a concise autonomous pass: derive EARS
criteria, tagged test cases, real-file design, and ordered tasks; assemble the
canonical `ce-spec.md` and `tasks.json`; and run the exact Mechanical Lint Gate.
Only exit 0 permits the artifacts to be written. Exit 1 must be repaired and
re-run or stopped; exit 2 stops. If any substantive decision emerges, stop
compact composition and return the evidence to an explicit
`/core-engineering:ce-spec <slug>/<id>` run. The approved compact route is
authority to derive a contract, not to change scope or accept new risk.

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
confirming it is ADR-worthy (itself a material call) — prepare a project-level
**ADR candidate** in scratch:

- Use the next free `docs/adr/NNNN-short-title.md` path and Nygard
  format: **Context · Decision · Status · Consequences**. `Status` starts
  `accepted`. In **Context**, cite the qualified origin —
  `<plan-slug>/<feature-id>` — so a reader a year from now can trace which plan
  and feature surfaced the decision.
- The spec's Resolved Decisions entry then **references** the ADR (`see ADR-NNNN`)
  rather than restating it.
- Keep the bar high — feature-local decisions stay in the spec. ADR sprawl is the
  failure mode.

Do not write or supersede an ADR yet. Include the exact candidate bytes and any
supersession edit in Final Approval; Stage 5 writes the approved transaction.
ADRs are durable project knowledge: they land in `docs/adr/`, not the plan
directory.

## Mechanical Lint Gate

Before approval or compact write, check the **mechanical** traceability
invariants on disk. Assemble `ce-spec.md` + `tasks.json` in a **scratch**
directory and lint that:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/spec-lint.py" <scratch-dir> \
  --threat-model docs/plans/<slug>/threat-model.md --feature <id> \
  --plan-dir docs/plans/<slug> --repo-root . --require-architecture-context
```

Pass `--threat-model` **and** `--feature <id>` here: the scratch dir is outside the
canonical `specs/<id>/` layout, so spec-lint can neither auto-discover the
threat-model nor infer the feature id from the path — give it both explicitly. (The
auto-build orchestrator needs neither flag — it lints the real `specs/<id>/`, where
both are auto-discovered.)

It checks H1–H7: every `tasks.json`
`verifies` resolves to a real TC; every TC carries a `modality:` and a
`verification:` tag, with `manual` modality paired to `manual:judgment`; no orphan
task or TC; and every `TZ-NNN` the threat-model assigns this feature is covered by a
`[SECURITY: TZ-NNN]` AC. H7 requires exact tasks/Markdown architecture-context
parity and freshness against the current consumer-linted package or typed
no-package disposition. Pass `--threat-model` whenever the plan has one — omit it
and H5 is simply N/A (no false fail on a plan without a threat-model). Disposition:

- **PASS (exit 0)** → report the H1–H7 rows as **machine-verified** with the
  command/result. Do not ask the human to re-attest those rows.
- **FAIL (exit 1)** → fix the artifact and re-run, or stop. A human
  acknowledgement cannot waive a structural failure.
- **Could-not-run (exit 2)** → stop with the tooling/integrity gap. Manual
  self-attestation cannot replace the validator.

The lint proves structure, not adequacy. Boundary correctness, the substance of
security/interaction criteria, and whether `manual:judgment` is genuine remain
human-owned in explicit mode. Auto-build and compact composition run the same
script as a blocking spec-artifact gate.

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
| Stage 0.4 | Feature identity or boundary is materially ambiguous | Ask or escalate to `/core-engineering:ce-plan` |
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
- **Humans own substantive decisions.** The workflow may derive reversible
  engineering defaults, but it never accepts a boundary, security, architecture,
  external-contract, or irreversible tradeoff silently. "Done" means executable,
  not proven correct.
- **Shares the model's blind spots.** Unknowns are resolved by research and reasoning on the same model that will later help implement them; an error shared across both can pass into the spec unflagged.
- **Spec §8 is the artifact's limits, not the skill's.** The `Assumptions & Limitations` section inside the emitted `ce-spec.md` records *that feature's* caveats — distinct from these limits of the spec **process** itself.
