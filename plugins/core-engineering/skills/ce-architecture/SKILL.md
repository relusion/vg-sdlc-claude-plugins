---
name: ce-architecture
description: |
  Turn one WRITTEN multi-feature plan into a repository-grounded, human-approved solution-architecture baseline: system context, runtime/container and deployment views, data/integration flows, quality scenarios, feature traceability, and explicit coverage gaps. Read-only on code and plan; the Scope Lock forbids re-cutting features or reassigning plan-owned TZ/IC obligations. Triggers: design/document/revise the cross-feature solution architecture for an existing plan. For decomposition use /core-engineering:ce-plan, for one technical option set use /core-engineering:ce-decide, and for feature-level design use /core-engineering:ce-spec.
argument-hint: "[plan-slug]"
allowed-tools: Read, Write, Glob, Grep, Bash, AskUserQuestion, Skill
---

# Architecture

**Invocation input:** Plan to architect: $ARGUMENTS

Turn a written multi-feature plan into a reviewable solution-architecture
baseline under `docs/plans/<slug>/architecture/`. The package explains the
cross-feature system shape and traces it back to the plan and repository. It
never edits the plan, accepted ADRs, specifications, source, tests, or
deployment configuration, and it never represents an architecture package as
security, compliance, release, or production approval.

This is an optional seam between planning and feature specification:

```text
/core-engineering:ce-brief -> /core-engineering:ce-plan -> [/core-engineering:ce-plan-audit]
    -> /core-engineering:ce-architecture -> /core-engineering:ce-spec
```

## Runtime Inputs

- **Plan slug (required):** a plan registered in `docs/plans/plans.json`. When
  omitted, select the sole plan or ask when several exist.
- **Written multi-feature plan (required):** `plan.json`, `feature-plan.md`,
  `shared-context.md`, `threat-model.md`, `interaction-contract.md`, and every
  `features/<id>.md`. A raw request routes to `/core-engineering:ce-brief`; work
  not yet decomposed routes to `/core-engineering:ce-plan`. A single-feature
  minimal plan is recognized before `plan.json` is required when its registered
  directory has a sole plan authority `feature-plan.md`, no full-plan files, and
  matching `Feature ID: <id>` /
  `Run: /core-engineering:ce-spec <slug>/<id>` identity fields. With no package
  it routes directly to that qualified `/core-engineering:ce-spec` command after
  the publication-transaction scan, unless the human first expands it through
  planning. If a prior architecture
  package exists after a revision collapses the plan to one feature, this skill
  owns its explicit human-approved obsolete-package disposition before spec.
- **Loaded evidence:** valid project documents listed by the plan, the matching
  approved brief when present, relevant accepted ADRs named by the plan, and a
  bounded one-hop read of manifests, runtime entry points, data surfaces, and
  deployment files needed to verify the plan's system boundaries.
- **Existing package (optional, auto-detected):** any lstat-style namespace
  occupant at the same plan's `architecture` path, including a broken symlink,
  non-directory, or partial directory. Valid directories enter revision mode;
  malformed occupants enter explicit recovery. Preserve source-backed content
  that remains valid, increment `architecture_revision`, and never overwrite or
  retire it without the applicable human gate.

## Execution Contract

Follow the workflow and companion templates exactly.

*Gate locator (HITL R5):* print `Gate N of M — <name>` at every interactive
gate. Before Scope Confirmation, compute `M` from a named gate manifest: Scope
Confirmation, Final Architecture Approval, one entry for each already visible
material decision candidate, and Invalid Architecture Package Recovery when it
applies. Never collapse unrelated decisions into one manifest entry or hardcode
`M`. If synthesis exposes a new candidate or splits one candidate into separate
decisions, invalidate the manifest and return to Scope Confirmation with the
recomputed sequence before asking for any affected choice. The single-feature
obsolete-package branch uses its own one-entry `Gate 1 of 1` manifest.

0. **Validate, then lease the exact output.** Accept only a slug matching
   `[a-z0-9]+(?:-[a-z0-9]+)*`; resolve its registered directory beneath
   `docs/plans/`, prove the resolved path remains beneath that directory, and
   require the directory basename to equal the slug. Never interpolate a raw
   registry or user value into a shell command. After validation and before any write,
   run `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --set --skill
   ce-architecture --allow 'docs/plans/<slug>/architecture'
   --allow 'docs/plans/<slug>/architecture/**'
   --allow 'docs/plans/<slug>/.architecture-publish-*'
   --allow 'docs/plans/<slug>/.architecture-publish-*/**'`. The hidden sibling
   patterns are reserved for the bundled publisher's bounded lock, stage,
   backup, and rejected paths; no other workflow writes there. Restore the
   deny-only baseline on every exit with the bundled write-lease helper's
   `--restore-baseline --root .` mode. A denied write is a contract conflict;
   reconcile it instead of weakening the lease.
   **Gate-pause least privilege:** immediately before yielding at any human
   gate, restore the deny-only baseline; do not leave write authority active
   while waiting. A continuation must revalidate the registered slug/path and
   rescan `.architecture-publish-*` siblings, then reacquire this exact lease
   before any repository write or publisher/retirement call. Read-only modeling
   and scratch review may continue under the baseline. Setting or restoring the
   lease can create/update `.claude/ce-write-scope.json`; phrases such as “write
   nothing” mean no architecture, plan, spec, code, or deployment artifact and
   do not conceal that guard-control write. Report the guard path when it was
   created.
1. **Require a supported plan shape.** A registry-backed single-feature minimal
   plan with matching explicit `Feature ID` / qualified `Run` identity routes
   directly to spec after transaction recovery and package disposition; it has
   no `plan.json` to lint. For every full plan, run
   `python3 "${CLAUDE_SKILL_DIR}/scripts/plan-lint.py"
   docs/plans/<slug> --json`. A hard FAIL routes to `/core-engineering:ce-plan`
   Stage R and stops. Exit 2 also means the required plan package is invalid or
   unreadable and routes to Stage R. Only command-unavailable/no-result may use
   a loud manual precondition check at Scope Confirmation.
2. **Honor the Scope Lock.** The written plan's features, journeys,
   dependencies, data classes, `TZ-NNN` obligations, and `IC-NNN` obligations
   are frozen for this run. Re-project them; never reassign or widen them.
3. **Separate evidence from synthesis.** Label architecture claims `recorded`
   (approved plan/brief/ADR), `observed` (repository file), `inferred` (model
   synthesis), or `unknown` (coverage gap). On the shared evidence scale,
   `recorded` and `observed` map to `read`, `inferred` maps to `inferred`, and
   `unknown` is below the scale. Every inferred structural claim needs a source
   and human review; unknowns are never silently filled.
4. **Keep tables and `architecture.json` authoritative.** Mermaid diagrams are
   projections for humans. If rendering is unavailable, the tables still carry
   the complete relationship and deployment data.
5. **Do not duplicate sibling ownership.** `/core-engineering:ce-plan` owns
   decomposition and plan revision; `/core-engineering:ce-decide` owns a scored
   recommendation for one consequential option set; `/core-engineering:ce-spec`
   owns files, schemas, APIs at implementation detail, acceptance criteria,
   tests, and tasks. This skill owns only cross-feature views, rationale,
   mappings, and documented gaps.
6. **Escalate structural discoveries before approval.** A new feature,
   dependency, journey, cross-feature flow, data-class assignment, `TZ-NNN` /
   `IC-NNN` obligation, or decomposition-shaping NFR routes to
   `/core-engineering:ce-plan` Stage R and stops. A consequential technical fork
   with no dominant option routes to `/core-engineering:ce-decide`; resume only
   from the human's recorded decision and accepted ADR when ADR-worthy.
7. **Make coverage explicit.** Record each required dimension as `complete`,
   `gap`, or `not-applicable` with a reason. A material gap parks the run. A
   non-material gap may remain only under human-approved
   `approved-with-gaps` status.
8. **Never write the final package before Final Architecture Approval.** Build
   the five files in a temporary scratch directory, lint them, and render them
   for review first. Scratch is not a repository artifact or downstream input.
9. **Run the deterministic gate.** Before approval, run
   `python3 "${CLAUDE_SKILL_DIR}/scripts/architecture-lint.py" <scratch-dir>
   --repo-root . --allow-proposed --json`. Exit 1 or 2 is a package failure and
   must be corrected before approval. Inability to execute the bundled command
   at all (no linter result) parks publication; the manual checklist may
   diagnose the package but cannot replace the publisher's pre-stage-final lint
   chain.
10. **Publish one coherent package:**
    `solution-architecture.md`, `views.md`, `data-and-integrations.md`,
    `quality-attributes.md`, and `architecture.json` under
    `docs/plans/<slug>/architecture/`. After approval, use the bundled publisher
    to perform only the approved JSON status/approval transition, verify and
    copy the reviewed bytes, lint before and after its transactional
    same-filesystem swap, and roll back on detected failure. Do not hand-edit
    the destination.
11. **No external authority.** Never commit, push, open or merge a PR, deploy,
    provision, accept security risk, promote an ADR, or claim production
    readiness.

## Scope Lock — the written plan boundary

The plan is the architecture run's frozen boundary. Architecture may explain
how planned features collaborate and may expose a missing decision, but it may
not add planned behavior or silently make the plan fit a preferred design.

- **Re-project, do not re-own:** threat and interaction obligations remain in
  `threat-model.md` and `interaction-contract.md`; architecture references their
  ids and explains realization.
- **Synthesize, do not specify:** components are logical runtime
  responsibilities. File/class/schema/test/task design stays in
  `/core-engineering:ce-spec`.
- **Escalate up:** if coherence requires a boundary change, stop and hand the
  exact delta to `/core-engineering:ce-plan` Stage R.

## Human-in-the-Loop — tiered

The human owns the architecture baseline and every material technical call.
The workflow gathers evidence, proposes a coherent model, and runs structural
checks; approval is always affirmative.

- **Scope Confirmation** always fires after the plan, evidence set, and computed
  gate manifest are shown.
- **Material Architecture Decisions** fires only when unresolved material
  choices remain after evidence gathering. Render evidence and cost-if-wrong
  first. Each option carries its consequence; a fork with no dominant option
  offers the `/core-engineering:ce-decide` route.
- **Final Architecture Approval** always fires after the scratch package passes
  lint. Exit 2 or command-unavailable/no-result is not an override path; park
  until deterministic validation can run.

At dense gates lead with **What needs your decision** and collapse routine,
source-backed rows to a count. Never collapse an unknown, bulk inference, or
coverage gap.

Final approval options:

| Option | Consequence |
|---|---|
| **Approve & publish** | Publish all five files. Status is `approved` when coverage is complete, otherwise `approved-with-gaps`; the documented gaps remain visible downstream. |
| **Adjust** | Return to the owning model/evidence stage; write no final package yet. |
| **Park** | Stop for an upstream plan/decision/evidence action; write no final package. |
| **Abort** | Stop under the deny-only baseline; write no architecture or other domain artifact. The reported lease-control baseline may remain. |

## Adoption and Ownership

Adopt this seam only for multi-feature work where a shared system baseline will
reduce downstream design rework; single-feature plans stay on the shorter
plan-to-spec path. A named solution/technical architecture owner approves the
baseline and owns recovery or revision decisions. Re-run after plan revision or
blocking plan/brief/ADR hash drift, and review repository-drift advisories at
each consuming spec. Track first-pass lint rate and spec rework attributable to
missing cross-feature design; invocation count alone is not evidence of value.
The schema and workflow version with the `core-engineering` plugin.

## How to Run This Workflow

Load companion files only when their stages run:

| Stages | Load this file | Purpose |
|---|---|---|
| 0–2 | `${CLAUDE_SKILL_DIR}/stage-0-2-evidence-model.md` | Resolve and lint the plan; inventory evidence and build the structural model |
| 3–5 | `${CLAUDE_SKILL_DIR}/stage-3-5-review-write.md` | Reconcile scope, disposition material calls, lint, approve, and publish |

At assembly time load `${CLAUDE_SKILL_DIR}/artifact-template.md`; do not
reconstruct the package schema from memory.

To begin, load `${CLAUDE_SKILL_DIR}/stage-0-2-evidence-model.md` and start Stage
0.

## Back-Edge Summary

| From | Trigger | To |
|---|---|---|
| Evidence inventory | Raw intent or missing product boundary | `/core-engineering:ce-brief`, then `/core-engineering:ce-plan` |
| Model reconciliation | New feature/dependency/journey/flow or changed TZ/IC/NFR ownership | `/core-engineering:ce-plan` Stage R; stop |
| Material decision gate | Consequential option set with no dominant option | `/core-engineering:ce-decide`; resume from the human decision |
| Final approval | Adjust | Owning evidence/model stage |
| Any stage | Abort or material evidence unavailable | Restore baseline and stop |

## Escalation

Malformed or structurally conflicted plans route to
`/core-engineering:ce-plan-audit` for findings and `/core-engineering:ce-plan`
Stage R for repair. Scope and cross-feature contract changes route directly to
planning and stop. One unresolved technical fork routes to
`/core-engineering:ce-decide`. Feature-local design questions become explicit
inputs to `/core-engineering:ce-spec`; this skill does not answer them early.

## Honest Limitations

- The package is a reasoned baseline, not proof that the system will satisfy
  its quality attributes. Verification and runtime probes provide evidence
  after implementation.
- Mermaid text is not renderer-tested by this skill. Authoritative tables and
  JSON preserve the model when diagram rendering is unavailable.
- `architecture-lint` proves package shape, reference/coherence rules, source
  hashes, and selected literals. It cannot prove that a component model is a
  good design or that a cited selector semantically entails a human-normalized
  deployment claim; Final Architecture Approval owns that judgment.
- The bounded repository read can miss hidden runtime coupling or undocumented
  infrastructure. Missing evidence is a gap, never permission to invent it.
- Source hashes detect recorded-input drift, not semantic drift in unlisted
  external systems or human knowledge.
- Architecture synthesis requires a multi-feature `plan.json`; a registered
  single-file minimal plan is supported only as a safe direct-to-spec or
  obsolete-package-disposition route. There is no durable mid-session resume
  draft, so an interrupted synthesis run restarts from disk evidence.
- Publication uses a two-rename same-filesystem transaction with rollback for
  detected failures, not a crash-atomic filesystem primitive. Orphan transaction
  paths after process death block the next run until human recovery.
- Automated retirement of an obsolete single-feature package requires the
  host's fd-relative no-follow filesystem primitives. On a host without them,
  the helper parks with an explicit coverage gap instead of falling back to an
  unsafe recursive delete.
- Human approval records review of this architecture baseline only. It is not
  security acceptance, compliance attestation, release approval, or deployment
  authority.
