# Workflow Recipes

Choose an outcome, run the smallest path, and stop when evidence changes the
route. Every recipe states its durable result and its escalation boundary.

## Recipe 1: Answer A Codebase Question

Run `/core-engineering:ce-ask <question>`.

**Expected artifacts:** a cited answer in the conversation; no repository
write.

**Stop or escalate:** use impact when the question is really a proposed change.

## Recipe 2: Refine A Work Item

Run `/core-engineering:ce-impact <change>`. If intent remains materially thin,
use optional `/core-engineering:ce-brief`, then `/core-engineering:ce-plan`.

**Expected artifacts:** blast radius, contracts, risks, and open questions;
optionally a brief and canonical plan directory.

**Stop or escalate:** do not estimate or implement across unresolved product or
boundary decisions.

## Recipe 3: Plan A New Feature

Run `/core-engineering:ce-plan <request>`.

Straightforward work plans directly. When architecture is load-bearing, plan
composes `/core-engineering:ce-architecture explore:<draft-slug>` and keeps the
human at one evidence-rich select/inspect/adjust/park gate. After selection it
decomposes and runs read-only shape. Publish the governed baseline only when the
plan requires or deliberately chooses it.

**Expected artifacts:** one canonical `docs/plans/<slug>/` shape, selected
architecture evidence when applicable, ordered features, and each feature's
`Specification route: compact|explicit`.

**Stop or escalate:** park when the architecture owner, evidence, or product
decision is missing.

## Recipe 4: Build One Planned Feature

For `compact`, run `/core-engineering:ce-implement <feature-id>`; it re-screens,
composes canonical spec/tasks, and requires spec lint before code. For
`explicit`, run `/core-engineering:ce-spec <feature-id>` first, then implement.

**Expected artifacts:** `ce-spec.md`, `tasks.json`, code, tests, task evidence,
and `verification.md` on either route.

**Stop or escalate:** route material decisions to explicit specification and
shared-boundary conflicts to planning. Never waive a deterministic lint.

## Recipe 5: Review And Verify Before Handoff

Run `/core-engineering:ce-review <feature>` and
`/core-engineering:ce-verify` for a pre-handover plan pass (or
`/core-engineering:ce-verify <journey>` for one milestone). They may be
orchestrated together but must produce independent evidence.

**Expected artifacts:** `code-review.md`, `review-summary.json`, and cumulative
verification evidence.

**Stop or escalate:** demonstrated PASS and clean negatives continue without
confirmation. Route failures, uncertainty, target ambiguity, stakeholder
acceptance, or material manual judgment.

## Recipe 6: Handle A Small Fix

Run `/core-engineering:ce-patch <change>`.

**Expected artifacts:** a test-first change within the admitted two-file set,
one final diff/evidence decision, and the express ledger entry.

**Stop or escalate:** any structural, dependency, security-sensitive, or
uncertain change routes to plan before editing.

## Recipe 7: Investigate A Failure

Run `/core-engineering:ce-debug <symptom>`.

**Expected artifacts:** reproduced evidence or ranked hypotheses, the cheapest
discriminating check, owning repair layer, and closure test.

**Stop or escalate:** diagnosis does not patch; route the confirmed cause to
implementation, specification, planning, or operations.

## Recipe 8: Probe Risk

Choose the surface:

- `/core-engineering:ce-probe-sec <target>`;
- `/core-engineering:ce-probe-perf <target>`;
- `/core-engineering:ce-probe-infra <path>`;
- `/core-engineering:ce-probe-deps <path>`;
- `/core-engineering:ce-ux-audit <plan-or-target>`.

**Expected artifacts:** evidence-tagged findings and explicit coverage gaps.

**Stop or escalate:** missing tools or access is could-not-run, never clean.
Probes do not accept risk or fix findings.

## Recipe 9: Prepare A Release Handoff

Use this order:

1. finish independent review and verification;
2. when documentation impact requires it, run
   `/core-engineering:ce-ship-document <plan>` from verified behavior;
3. run `/core-engineering:ce-doc-audit <doc>` when a quickstart, runbook,
   migration, safety procedure, or high-impact journey changed;
4. optionally use `/core-engineering:ce-humanize <doc>` for tone, then recheck
   facts;
5. if documentation or its audit changed repository state, incorporate those
   artifacts into the candidate HEAD;
6. after such a change, refresh `/core-engineering:ce-review` and
   `/core-engineering:ce-verify` so their receipts bind that candidate;
7. run `/core-engineering:ce-ship-release <plan>` last.

**Expected artifacts:** documentation-impact disposition, verified
documentation and reader-role audit when required, current review/verification
receipts, rollback and supply-chain evidence, and a final GO/NO-GO package.

**Stop or escalate:** release remains NO-GO when required evidence is missing or
stale. The workflow never tags, publishes, or deploys.

## Recipe 10: Run The Full Spine Autonomously

Run `/core-engineering:ce-plan-audit <slug>` first, triage its findings, then
run `/core-engineering:ce-auto-build <slug>` with explicit feature, retry, park,
and budget bounds.

The orchestrator processes one feature at a time and preserves the same
compact/explicit specification contract. A leaf returns a real gate to its
parent as a structured `Needs decision` handoff, with evidence, options,
consequences, and resume input, without treating silence as approval.

**Expected artifacts:** per-feature spec, implementation, independent review and
verification, `STATUS.md`, and an end-review package.

**Stop or escalate:** product, architecture, security acceptance, destructive,
scope, and repeated-failure decisions park for a human.

## Recipe 11: Learn A Built System

Run `/core-engineering:ce-onboard <target>` for implementation or
`/core-engineering:ce-domain <path>` for business actors, nouns, rules, and
lifecycles.

**Expected artifacts:** a cited walkthrough; optional learning guide or domain
primer.

**Stop or escalate:** inferred “why” belongs in known unknowns, not confident
narration.

## Recipe 12: Shape Product Direction

Install the optional discovery plugin, then use:

- `/product-discovery:ce-idea-scout` to create a shortlist;
- `/product-discovery:ce-idea-score` to score one direction;
- `/product-discovery:ce-market-scan` for sourced market context.

Feed the chosen direction directly to plan, or through optional
`/core-engineering:ce-brief` when product intent still needs clarification.

**Expected artifacts:** evidence-tagged discovery outputs, not a release or
investment authorization.

**Stop or escalate:** unknown evidence stays unknown; a model score does not own
the product decision.

## Recipe 13: Make A Technical Decision

Run `/core-engineering:ce-decide <decision and supplied options>` for one bounded
fork.

**Expected artifacts:** a scored proposed ADR with evidence and trade-offs.

**Stop or escalate:** complete solution exploration belongs to the planning
architecture workbench; ADR promotion remains human-owned.

## Recipe 14: Audit Planning And Process

Run `/core-engineering:ce-plan-audit <slug>` for plan quality and
`/core-engineering:ce-retro <slug>` for recorded delivery signals.

**Expected artifacts:** findings, metrics gaps, and optionally a compiled
evidence pack.

**Stop or escalate:** neither artifact is compliance attestation or permission
to ship.

## Recipe 15: Check Planned UX

Run `/core-engineering:ce-ux-audit <slug>` against planned journeys, or against a
bounded running target for plan-free discovery.

**Expected artifacts:** journey evidence and prioritized UX findings.

**Stop or escalate:** do not widen target or mutate the application.

## Recipe 16: Export Work Items

Run `/core-engineering:ce-ship-backlog <feature-id>`.

**Expected artifacts:** paste-ready ADO, Jira, or GitHub import output grounded
in plan/spec artifacts.

**Stop or escalate:** the workflow does not call a tracker API or invent missing
ownership.

## Recipe 17: Use Focused Agents

Choose `spec-author` for plan/spec artifact work and `spec-impl` for
implementation. They use the same skills, validators, and write scopes.

**Expected artifacts:** the same durable outputs as direct invocation.

**Stop or escalate:** a leaf returns a real decision to the caller and resumes
from the named checkpoint; it does not spawn nested agents or land changes.

## Recipe 18: Bootstrap A Repository

Run `/core-engineering:ce-init --readiness`, then
`/core-engineering:ce-init --write` after reviewing the proposed files. Use
`/core-engineering:ce-go <goal>` as the ongoing front door.

**Expected artifacts:** repository profile, starter review policy, write-scope
baseline, and explicit local versus host-control gaps.

**Stop or escalate:** administrator-only branch protection cannot be locally
attested.

## Recipe 19: Return To A Plan Mid-Flight

Read `docs/plans/<slug>/STATUS.md`, then validate plan/spec/task artifacts. Use
`/core-engineering:ce-auto-build <slug> --resume` only when you intend to
continue the stored bounds.

**Expected artifacts:** a re-derived status and one explicit next action.

**Stop or escalate:** stale projections or changed architecture/spec bindings
must be repaired at their owning layer before resume.

## Recipe 20: Operate An Unattended Run

Watch `STATUS.md` between features. Treat queued, running, parked, failed,
budget-exhausted, and complete as distinct states. Use `--resume` after a park
only with the named decision and unchanged bounds.

**Expected artifacts:** append-only run state, bounded retry/park records, and a
final human-review package.

**Stop or escalate:** loss of evidence, exhausted bounds, or a material decision
stops unattended execution. Never convert absence into approval.
