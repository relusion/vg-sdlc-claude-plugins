# How It Works

`vg-coding` has two layers:

1. repository-aware Claude Code workflows that create reviewable artifacts;
2. deterministic repository gates that validate structure and committed state
   without trusting model prose.

Use the [Usage Matrix](USAGE-MATRIX.md) to choose a command. This page defines
the behavior and authority boundaries.

## 1. Adaptive workflow

The default is the shortest safe path, not the longest artifact chain:

```text
[optional ce-brief] → ce-plan
  ├─ direct planning when architecture is neither load-bearing nor requested
  └─ evidence-rich architecture workbench when load-bearing or explicitly opted in
       explore ↔ question / inspect / adjust → human selection
       → decompose ⇄ read-only shape
       → governed baseline only when required or deliberately chosen
→ plan records Specification route: compact | explicit
  ├─ compact: ce-implement composes and lints ce-spec.md + tasks.json
  └─ explicit: ce-spec resolves design and human decisions first
→ ce-implement
→ ce-review ∥ ce-verify
→ ce-ship-document when documentation impact requires it
→ ce-doc-audit when reader or operational risk warrants it
→ commit the documentation candidate, then refresh ce-review ∥ ce-verify
  whenever documentation or its audit changed bound repository state
→ ce-ship-release (final decision package)
```

`/core-engineering:ce-brief` is optional. Use it when the product request is too
thin or conflicted for planning; do not manufacture a brief for already clear
repository work.

`/core-engineering:ce-plan` always writes one canonical plan-directory shape.
It adapts its questions and architecture work to repository evidence, risk, and
unresolved decisions.

Plan validation has one current contract and no legacy mode. Every `plan.json`
must carry its project identity, planned status, revision, tier, relationships,
complete human-owned architecture disposition/direction, and a fresh
current-schema `architecture-selection.json` binding. Missing, stale, or older
authority is a hard planning defect on every plan-lint invocation; downstream
work routes it to Plan Stage R rather than selecting a looser consumer mode.

### Architecture only when load-bearing or explicitly requested

Architecture is load-bearing when the work changes shared boundaries, public
contracts, durable data, cross-feature flows, deployment/trust topology,
material quality attributes, or an accepted technical direction.

In that case—or when repository policy or the accountable human explicitly
requests a comparison now—plan invokes
`/core-engineering:ce-architecture explore:<draft-slug>` to **generate and
score complete solution directions before decomposition**. The workbench
persists two to four complete viable options when available, eliminated and
unresolved alternatives, explicit criteria and weights, repository evidence,
assumptions, trade-offs, recommendation, confidence, and sensitivity.

Generic future reuse, a baseline preference inferred by the model, or the mere
availability of the workflow does not trigger architecture work.

The complete comparison lives in the linted report. Chat shows a compact
decision projection—one row per direction, decisive trade-offs, recommendation,
uncertainty, cost if wrong, and the report path/hash—rather than repeating the
evidence ledger and every score basis. No selectable gate exists until the
report has been persisted, re-read, and validated; an interrupted or
budget-exhausted synthesis remains visibly incomplete.

A deterministic workbench renderer turns the model's semantic direction
judgments into the report, derives weighted totals and content bindings, preserves a
hash-chained question/revision audit, and emits the complete preselection
checkpoint. The model does not hand-build projections or reverse-engineer
validators. This keeps the human evidence surface complete while removing
mechanical authoring from the expensive conversational path.

Questions, option edits, and decision-frame changes return to the same gate.
Every revision must match the last displayed report hash; changed or removed
directions remain archived as considered alternatives. Before returning a
frame delta, the workbench rewrites that same report as a durable
`frame-change-pending` checkpoint. Its envelope binds the last selectable hash
H1, while the pending report itself has a distinct hash H2 and is rejected by
the default selectable-report lint. Planning can safely resume after an
interruption by validating and extracting the pending delta from H2, then
applies only that delta. Recomputed architecture must revise H2—not H1—and
carries both prior hashes in the audit before selection is enabled again.

The architecture decision remains human-owned. At the stable `Architecture
Direction Selection` gate the decision owner can:

1. select a direction;
2. inspect evidence or ask a question;
3. adjust requirements, weights, constraints, an option, or add an alternative;
4. park or abort.

A frame adjustment first persists a hash-bound, non-selectable pending delta
so plan can rewrite the authoritative frame without relying on chat state. The
workbench then recomputes against that frame and records the applied change in
the next linted, non-selected revision.
Option-only changes recompute directly inside the workbench. Both return to the
same locator. Each persisted revision records a compact delta and prior hash;
only the final selected snapshot becomes immutable and hash-bound.

The decision frame hash-binds the owner's identity or role and authority basis.
The recorded `approved_by` must match that owner exactly; delegation first
requires a visible frame revision. Every numeric option score carries an
option-specific basis inside the option hash, so the comparison is inspectable
rather than an unexplained total.

After decomposition, `shape:<draft-slug>` runs read-only under the parent
workflow's existing authority. It reports converged, requires-plan-delta,
requires-decision, or blocked. It does not ask for another consent gate.

Normal architecture mode publishes the strict five-file baseline only when
`plan.json` records it as required, or a human deliberately accepts a
recommended baseline. **A selected and converged required or recommended
direction blocks specification and implementation until its governed package
is current.** The package is specification context, not security acceptance,
deployment permission, or release approval. A recommended baseline may instead
be explicitly deferred from the same workbench with human rationale; a
required baseline may not. The downstream invariant is “selected and converged
architecture requires a current package; explicitly deferred recommended
architecture remains a visible coverage gap.”
Architecture package compatibility follows its stable generator contract
version, independent of routine plugin delivery-version bumps. A generator
contract change requires package regeneration and renewed human approval.
Baseline synthesis does not ask the human to re-confirm the already approved
plan. An Evidence Boundary Resolution gate appears only when candidate sources
conflict, a missing source could materially change the model, or the human asks
to change the evidence boundary. Material architecture choices and Final
Architecture Approval remain explicit.

### Conditional specification

Plan writes `plan.json.features[].specification_route` as `compact` or
`explicit` for every feature and projects it once in feature Markdown. Plan
lint rejects a missing, duplicate, unknown, or mismatched route.

- `explicit` means `/core-engineering:ce-spec` must resolve detailed behavior,
  tests, tasks, and material decisions before implementation.
- `compact` means the feature is already build-ready. On entry,
  `/core-engineering:ce-implement` re-screens the route, composes the same
  canonical `ce-spec.md` and `tasks.json` through the normal specification
  stages, and requires `spec-lint` to pass before editing code.

Compact is refused for complex work; security/privacy obligations; owned or
changed public API/CLI/event/schema/config contracts; unresolved dependency
interfaces; owned or changed shared shapes/cross-feature flows; material
migration, concurrency, failure, compatibility, destructive, or irreversible
design; or any unresolved product, scope, boundary, acceptance-adequacy, or
manual judgment. The behavior, acceptance, test location, validation commands,
and small ordered task cut must all be known. A stable built dependency or
already selected architecture direction does not disqualify compact by itself.
Route drift returns to Plan Stage R; there is no silent override.

### Independent assurance, one handoff

Review and verification are peers:

- `/core-engineering:ce-review` evaluates correctness, security, performance,
  maintainability, conformance, and simplicity.
- `/core-engineering:ce-verify` demonstrates acceptance behavior, journeys,
  dependencies, and test evidence.

An orchestrator may run them together, but neither consumes the other's
conclusion as proof. Demonstrated PASS rows and clean negative findings are
reported without a confirmation gate. Failures, uncertainty, target ambiguity,
stakeholder acceptance, and material manual judgments are routed explicitly.

### Documentation before release

`/core-engineering:ce-ship-document` generates user and operator documentation
from verified behavior and runnable evidence. Run
`/core-engineering:ce-doc-audit` before release when a changed quickstart,
runbook, migration, safety procedure, or high-impact user journey needs an
independent reader-role check. Clean audit results do not require
re-attestation; findings route back to documentation.

`/core-engineering:ce-ship-release` is the final workflow. It compiles the
current plan, implementation, independent review and verification, required
documentation/audit, rollback, and supply-chain evidence into GO/NO-GO input.
It re-runs deterministic review and verification freshness gates against one
resolved HEAD; stale receipts, changed plan/spec/task authority, or changed
implementation files block GO. It never tags, publishes, or deploys.

Documentation and doc-audit changes are part of that candidate HEAD. After
either workflow changes repository state, the human incorporates those changes
into the candidate commit and refreshes both review and verification before
release. This is a freshness rerun, not another product or architecture
decision: unchanged evidence stays automatic, while any new finding follows its
normal owning route.

## 2. Routing and escalation

The plugin has **29 skills** and **2 plugin-shipped custom agents**. `ce-go` is
the front door: it derives repository state, auto-routes an unambiguous
model-invocable destination, and otherwise asks one discriminating question or
returns the exact direct-only command.

Each stage owns one scope. A conflict routes upward:

- implementation conflict → specification;
- specification or shared-boundary conflict → planning;
- material architecture uncertainty → the architecture workbench and owner;
- review or verification defect → implementation, specification, or planning
  according to the validated route;
- documentation finding → documentation;
- missing release evidence → the producing workflow.

A stage never widens its own Scope Lock.

## 3. Durable artifacts

All planned work uses the same directory shape:

```text
docs/plans/
  plans.json
  <slug>/
    plan.json
    feature-plan.md
    shared-context.md
    threat-model.md
    interaction-contract.md
    architecture-options.md
    architecture-selection.json
    architecture/
      architecture.json
      solution-architecture.md
      data-and-integrations.md
      quality-attributes.md
      views.md
    features/
      <id>-<slug>.md
    specs/
      <id>/
        ce-spec.md
        tasks.json
        verification.md
        code-review.md
        review-summary.json
    verification-report.md
    verification-summary.json
    release/
      <release-key>-release.md
    STATUS.md
```

Only artifacts required by the chosen route are present. For example,
architecture workbench/baseline files are conditional, and documentation audits
exist only when that risk trigger fires. `STATUS.md` is a projection, not a
second source of truth.

Machine JSON owns exact structure and digests. Human Markdown and diagrams are
review views; where a deterministic projector exists, do not hand-maintain a
second schema in prose.

Dated reports use `<date>`. A second run on the same day receives `-2`, then
`-3`, consistently across its report and companions. Drafts under
`docs/plans/.drafts/` are resumable work, not approved plan inputs.

## 4. Human authority

A human gate exists only for an actual choice, consent, exception, or
authority-owned judgment. It is not required for:

- deterministic PASS;
- a completed read-only step;
- a generated projection;
- a demonstrated verification PASS;
- a clean review, audit, or probe result.

Deterministic failure stops or routes. A human cannot make it green through
re-attestation.

Material product, scope, architecture, security acceptance, destructive or
irreversible operation, contract break, accepted-risk, and release choices are
human-owned. Their gate shows repository evidence, alternatives, consequences,
unknowns, recommendation, confidence, decision owner, and a gather-evidence,
route, or park path. See the
[HITL Gate Standard](contributing/HITL-GATE-STANDARD.md).

## 5. Runtime safety

Claude Code hooks provide cooperative backstops:

- recognized shared-history and PR mutations ask or deny;
- credential-store and out-of-workspace secret reads are denied;
- the active skill's session-bound write lease limits writes;
- recognized outbound calls follow repository network policy;
- session start checks installed hook integrity.

Decisions append to a hash-chained guard log. These hooks are tamper-evident
pattern checks, not a complete sandbox or data-loss-prevention system. Skills
still have no authority to push, merge, deploy, publish, tag, or rotate secrets.

## 6. Deterministic control plane

Small stdlib-only validators own exact checks: plan graphs and references, spec
traceability, architecture packages, test weakening, dependency declarations,
write scope, review summaries, and evidence freshness.

Their result shape is:

- pass;
- finding/failure;
- could-not-run.

Missing tools or malformed evidence never become a clean result.

The merge bar asks two separate questions:

1. did deterministic integrity gates pass against the committed base and head?
2. did the Git host enforce the required human review?

[`scripts/gate_runner.py`](../scripts/gate_runner.py) answers only the first and
records the policy's validity requirement. Branch protection, CODEOWNERS, normal
build/test jobs, and required reviewers enforce the second. A green merge bar
does not prove the project compiles, tests are sufficient, or the system is
secure.

## 7. Automation

The `spec-author` and `spec-impl` custom agents are leaf wrappers around the same
skills and artifacts. At a real decision they return a structured `Needs
decision` checkpoint to their caller. They do not spawn nested workers or gain
repository-history authority.

`/core-engineering:ce-auto-build` is the bounded sequential orchestrator. It
fixes feature range, attempts, parks, and budget up front; processes one feature
at a time; persists status; and re-derives state on `--resume`. Product,
architecture, security-acceptance, destructive, scope, and release decisions
park for a human.

## 8. Evidence and evaluation

Repository validation includes:

- `scripts/check.py` and delegated corpus/product/supply-chain checks;
- stdlib portability checks;
- unit tests for hooks, gates, artifacts, and orchestration;
- deterministic eval fixtures and goldens;
- optional live-model runs with hard per-scenario budgets.

A live-eval workflow conclusion is not itself behavioral evidence. The workflow
emits an evidence receipt that records whether a clean, graded live summary was
actually produced. The main-health canary requires that receipt and checks its
freshness; a successful skipped run is unhealthy evidence state.

[Benchmarks](BENCHMARKS.md) separates design verification from current live
evidence. [Real Outputs](EXAMPLES.md) records provenance. Neither an evidence
pack nor this framework is a compliance attestation.

## 9. Contributor model

`SKILL.md` contains the always-loaded contract. Stage detail is loaded on
demand. The [Skill Authoring Standard](contributing/SKILL-AUTHORING.md) enforces
line and token-proxy ceilings so progressive disclosure is measurable.

When public routing, authority, artifacts, or failure behavior changes, update
this overview, the README, Usage Matrix, recipes, tests, and changelog in the
same change.
