---
name: ce-plan
description: |
  Turn a repository-grounded outcome into an approved, dependency-ordered feature plan, using an evidence-rich architecture comparison only when architecture changes the delivery cut. Triggers: plan, decompose, scope, or revise a project/feature. Composes /core-engineering:ce-architecture for load-bearing direction work; use /core-engineering:ce-spec only when a feature needs a separate detailed contract.
argument-hint: "[project description | brief=<path> | revise:<slug>]"
allowed-tools: Read, Write, Glob, Grep, Bash, AskUserQuestion, Skill
---

# Plan

**Invocation input:** $ARGUMENTS

Produce the smallest durable plan that makes implementation safe. Inspect the
repository before asking questions, preserve human ownership of scope and
architecture, and do not turn deterministic checks into human attestations.

This skill is staged. Load only the file for the stage being executed.

## Runtime Inputs

- **Outcome (required):** the requested product or engineering result. Ask one
  short question only when no usable outcome was supplied.
- **Brief (optional):** `brief=docs/briefs/<slug>.md`. A brief is discovery
  context, not a prerequisite. Revalidate its `.json` sidecar before using it to
  skip answered intent questions.
- **Revision (optional):** `revise:<slug>` or a request that clearly targets an
  existing registered plan.
- **Repository evidence:** project rules, relevant code and tests, existing
  plans/ADRs, build and verification commands, and direct integration surfaces.

## Execution Contract

1. **Inspect before asking.** Resolve the repository shape, existing decisions,
   constraints, and affected surfaces before asking the human for information
   the repository already contains.
2. **Ask only consequential questions.** Ask when an answer changes outcome,
   scope, feature boundaries, architecture, security acceptance, priority, or a
   hard dependency. Use at most four questions per call and at most two rounds
   unless the human explicitly continues discovery.
3. **Keep the Scope Lock.** Planning may shape the requested outcome; it may not
   silently add adjacent work. Record non-goals and route a materially wider
   outcome back to the human.
4. **Triage architecture before decomposition.** Build a coarse capability and
   driver frame. If architecture is `not-required`, record the reason and
   continue without a gate. If it is `recommended` or `required`, use the
   architecture decision workbench in Stage 1A.
5. **Make architecture selection decision-ready.** Before a direction is chosen,
   show the comparison summary, every option considered, eliminated options and
   reasons, criteria/weights, repository evidence, reasoning, assumptions,
   unknowns, trade-offs, consequences, recommendation, and confidence. The
   human may ask questions, change constraints/weights, revise an option, or
   request another option; recompute the report and return to the same decision
   locator. Only an explicit human selection binds a direction.
6. **Decompose after the direction is stable.** Produce independently valuable
   or verifiable features in dependency order. Mark each feature's specification
   route `compact` or `explicit`: compact is allowed only when behavior,
   boundaries, tests, and interfaces are already unambiguous.
7. **Validate rather than ceremonialize.** Run reachability, durable-state,
   surface-continuity, dependency, risk, and session-fit checks. Record clean
   results. Ask only about unresolved material rows or a proposed exception.
8. **Shape without a redundant consent gate.** When a direction was selected,
   run `/core-engineering:ce-architecture shape:<draft-slug>` read-only. A clean
   convergence result is recorded; only a proposed plan delta, architecture
   change, evidence gap, or iteration cap needs a human decision.
9. **Validate before final approval.** Assemble the exact plan candidate in a
   collision-safe scratch directory, run `architecture-selection-lint.py` and
   `plan-lint.py`, and show their PASS receipts plus the file-hash manifest.
   Hard failure or could-not-run is non-waivable.
10. **One final approval and canonical publication.** Approval binds only the
    displayed linted bytes and registry delta. Publish them unchanged under
    `docs/plans/<slug>/`, update `docs/plans/plans.json` last, verify byte
    equality, and rerun both validators as a post-publication drift check.
11. **Revise by delta.** Existing plans use Stage R. Preserve unaffected feature
    and spec bytes, re-run only checks touched by the delta, bump
    `plan_revision`, and require approval only for changed material decisions
    plus the final write.
12. **Human authority is explicit.** Product scope, architecture selection,
    security/risk acceptance, destructive consequences, and final plan approval
    remain human-owned. Silence is never approval.

## Human-in-the-Loop — adaptive

Interactive gates correspond to decisions, not stages. Print
`Gate N of M — <name>` for every gate that actually fires and use the same
locator in telemetry.

Normal runs have:

1. **Intent and Scope** — only when repository evidence and supplied intent
   leave a consequential ambiguity.
2. **Architecture Direction Selection** — only when Stage 1A classifies architecture as
   recommended/required and an option decision is needed. This gate is an
   iterative workbench: questioning or adjustment loops under the same locator
   and does not count as selection.
3. **Material Exceptions** — only for unresolved boundary, security,
   dependency, ownership, reachability, or interface-foundation decisions.
4. **Final Plan Approval** — always; approves the rendered artifact and write.

Do not gate an unambiguous route, a bounded read-only analysis, a deterministic
PASS, a clean negative, or an auto-resolved row. Show those in the evidence
summary with an override path at Final Plan Approval.

For every material decision render:

```text
Decision owner: <role/expertise>
Authority: <why this person may decide>
Evidence: <repository sources and demonstrated/read/inferred status>
Assumptions and unknowns: <material gaps>
If wrong: <concrete consequence>
Recommendation: <option and reasoning>
Confidence: <high|medium|low and why>
```

If authority or evidence is missing, offer **Need evidence / route to owner** or
**Park — stop without a final write**. Do not infer authority from participation.

## Scope Lock

The approved outcome and non-goals are frozen for the run. Planning may re-slice
the same scope, narrow it with explicit deferral, or route a proposed expansion
to the owner. Architecture exploration may shape the cut but may not select a
direction for the human. Architecture shaping may propose a delta but only this
skill applies a human-approved re-cut.

## How to Run This Workflow

| Stage | Load | Purpose |
|---|---|---|
| 0–1 | `${CLAUDE_SKILL_DIR}/stage-0-1-understand.md` | Resolve plan/revision, inspect repository, ask only material intake questions |
| 1A | `${CLAUDE_SKILL_DIR}/stage-1a-architecture-direction.md` | Classify drivers and, when needed, run the interactive architecture workbench |
| 2–3 | `${CLAUDE_SKILL_DIR}/stage-2-3-decompose-score.md` | Decompose, order, size, risk-rank, and choose compact vs explicit specification |
| 4–7 | `${CLAUDE_SKILL_DIR}/stage-4-7-gates.md` | Validate reachability, lifecycle, continuity, dependencies, and session fit; ask only exceptions |
| 5A | `${CLAUDE_SKILL_DIR}/stage-5a-architecture-convergence.md` | Run read-only shaping and reconcile only material deltas |
| 8–9 | `${CLAUDE_SKILL_DIR}/stage-8-9-write.md` | Present decision delta, approve, write, and run hard lints |
| R | `${CLAUDE_SKILL_DIR}/stage-R-revision.md` | Apply an evidence-bound delta to an existing plan |

At write time load `${CLAUDE_SKILL_DIR}/artifact-template.md`. Do not reconstruct
the artifact contract from memory.

To begin, load `${CLAUDE_SKILL_DIR}/stage-0-1-understand.md`.

## Back-Edge Summary

When routing back, preserve:

```text
Back-Edge Summary
Owner layer: <plan|architecture|spec|implement>
Requested change: <one sentence>
Evidence: <paths, checks, and current revision>
Scope effect: <none|narrow|re-cut|widening proposed>
Decisions invalidated: <ids or none>
Resume at: <stage>
```

## Escalation

- Missing product/scope authority → route to the product or plan owner and park.
- Architecture evidence or option-set gap → return to the Stage 1A workbench.
- A selected direction requiring a different feature cut → Stage 5A proposes;
  this skill applies only the human-approved delta.
- Security acceptance without an authorized owner → park; do not infer a waiver.
- A feature that cannot be made independently verifiable → re-slice or record a
  human-approved exception before final approval.
- A written-plan defect discovered downstream → Stage R with the downstream
  Back-Edge Summary.

## Honest Limitations

- `plan-lint.py` proves structural integrity, not that the product choice or
  architecture recommendation is wise.
- Repository inspection can miss runtime behavior and undocumented external
  dependencies; record those as gaps with an owner and next check.
- Architecture scoring is decision support. It is sensitive to criteria,
  weights, evidence, and assumptions; the workbench must expose that sensitivity.
- Compact specification is appropriate only when the plan already contains a
  testable, bounded contract. Otherwise use `/core-engineering:ce-spec`.
- A plan is not implementation, security attestation, release approval, or
  deployment authority.
