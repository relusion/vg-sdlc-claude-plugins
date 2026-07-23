---
name: ce-auto-build
description: |
  Build a plan through a bounded, sequential spec-to-implementation pipeline with independent review, deterministic gates, and one final human review.
  Triggers: auto-build/autopilot/batch spec and implement a plan in ship order.
argument-hint: "[plan-slug] [range e.g. 01..05] [--resume]"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion, Task
disable-model-invocation: true
---

# Auto Build

**Invocation input:** plan, optional feature range, and optional `--resume`: $ARGUMENTS

Build the selected features of an existing plan in ship order. For each feature,
create the specification, validate it, implement it, verify it, and run an
independent review before moving on. The workflow is deliberately sequential and
has one operating profile.

Use this skill when a plan is already approved and the human wants a bounded batch
run. Stage 0 enforces the plan's human-owned architecture disposition before any
worker starts. Use `/core-engineering:ce-plan` when the scope or architecture
convergence is still unsettled, `/core-engineering:ce-architecture` when a
required governed baseline is missing or stale, and `/core-engineering:ce-spec`
or `/core-engineering:ce-implement` when the human wants to drive one feature
directly.

## Execution Contract

Auto-build provides supervised autonomy, not release authority.

- The human approves the exact scope, token/compute budget, failure-attempt cap,
  and park cap
  at kickoff.
- Features run one at a time in `ship_order`. There is no parallel or worktree
  mode.
- A fresh spec worker and implementation worker preserve the spec-to-code boundary.
  An independent review worker examines the result.
- On-disk artifacts and deterministic scripts gate progress; worker claims do not.
- A full plan must pass `plan-lint.py` and carry a valid
  `architecture_disposition`. Every present architecture package is consumer-linted.
  A `required` + `converged` disposition needs a current published
  `accepted-for-specification` package before kickoff; explicitly deferred
  recommended absence is kickoff coverage, never a silent default.
- Product, security-acceptance, destructive, architectural, and scope decisions are
  parked for the human. They are never guessed to keep the batch moving.
- The run never creates branches or commits, pushes, opens or merges pull requests,
  deploys, or writes to external systems.
- The final result is not "done" until a human reviews the report and working-tree
  diff.

## Fixed workflow

```text
Stage 0 — kickoff
  resolve and lint plan → enforce architecture disposition/package
  → confirm clean tree and capabilities
  → human approves scope + budget + failure-attempt/park caps

Stage 1+2 — sequential feature loop
  for each feature in ship order:
    spec worker → spec artifacts + spec-lint
    → implementation worker → tests + verification artifacts + external gates
    → independent review → done, repair, or park
  then one integration verification over the combined result

Stage 3 — human end-review
  inspect decisions, parks, verification, review findings, integration result,
  and the complete working-tree diff → accept for later landing or request repair
```

There are no build presets, challenge/diagnose/enrichment modes, checkpoint
branches, or alternate orchestration profiles. If this fixed workflow does not fit,
stop and route the work to the relevant interactive skill.

## Runtime Inputs

- **Plan slug:** required. If omitted, read `docs/plans/plans.json` and ask the
  human to choose an active plan.
- **Feature range:** optional. It must be a contiguous subset of the plan's ship
  order. Default: all unfinished features.
- **`--resume`:** optional. Resume the newest state file after reconciling it with
  artifacts on disk.
- **Budget:** a required positive token/compute estimate for the whole run.
- **Failure-attempt cap (`--retry-cap`):** a required positive per-feature limit that
  counts the first failed gate attempt. A cap of `2` permits one fresh repair; the
  default recommendation is `3`.
- **Park cap:** a required positive consecutive-park cap. Default recommendation:
  `3`.

The plan must exist, pass `plan-lint.py`, carry a valid human-recorded
`architecture_disposition`, satisfy its blocking architecture prerequisite, and
name discoverable build/test/lint commands. A missing legacy disposition routes
to `/core-engineering:ce-plan` Stage R rather than silently inheriting the old
optional behavior. The working tree must be clean at kickoff so each feature's
diff and dependency changes have an unambiguous baseline. A dirty tree is a stop
condition, not an alternate mode.

## Escalation

| Decision | Disposition |
|---|---|
| Existing-pattern engineering detail | Decide, record, continue |
| Reversible product assumption explicitly allowed by the approved spec | Use the conservative default, flag it in the ledger |
| Product behavior not settled by the plan/spec | Park |
| Security or compliance acceptance | Park |
| Destructive operation, migration, credential use, or external write | Park |
| Architecture-significant or cross-feature structural change | Park |
| Spec/repository conflict that changes scope or a public contract | Park |

Every non-routine decision is appended through `run-state.py ledger-append` and
appears in the final report. A parked feature blocks its hard dependents. Independent
later features may continue until the budget or consecutive-park bound stops the run.

## Worker selection

The `Task` tool is required. Prefer the plugin-shipped `spec-author` worker for the
specification pass and `spec-impl` for implementation. Use a fresh generic Task
worker only when a named worker is unavailable, with the same role, inputs, output
artifacts, and no-question contract. Use another fresh Task worker for review.

Do not collapse the work into the orchestrator context when Task is unavailable.
Stop, record the capability gap, and route the remaining features to `/core-engineering:ce-spec` and
`/core-engineering:ce-implement`. This keeps loss of the spec/implementation boundary explicit.

Each worker receives only the minimum repository context needed for its role. The
implementation worker receives `ce-spec.md` and `tasks.json` as its specification
inputs; it must stop if either is missing. Workers cannot ask the human mid-run.
They return a structured result or park.

## State, resume, and bounds

`scripts/run-state.py` owns the state file, counters, ledger, and metrics:

```text
docs/plans/<slug>/ce-auto-build/<date>-state.json
docs/plans/<slug>/ce-auto-build/<date>-ledger.jsonl
docs/plans/<slug>/.metrics.jsonl
```

The state file is a cache; disk artifacts remain authoritative. On `--resume`,
reload its immutable `baseline` and ordered `selected_features`, then re-check each
cached terminal feature in that ship order:

```text
ce-spec.md exists
tasks.json exists and every task is done
verification.md exists
review-summary.json exists and has no blocking confirmed-high finding
```

Validate `review-summary.json` with the existing sibling `ce-review` contract and
the synchronized local `review-gate.py`; never infer its blocking state from review
prose or an ad-hoc JSON shape.

If cache and disk disagree, disk wins and the feature returns to the first missing
gate. An unreadable or unsupported state schema stops the resume; do not invent
state or overwrite the old run.

Estimate each worker exchange as `(prompt characters + result characters) / 4` and
book it through `--tokens` or `budget-add`. Label this as an estimate, not billing
data. Run `breaker-check` after each feature: exit `0` continues, exit `1` stops at
the bound, and exit `2` stops because the state could not be trusted. Never shorten
verification or review to fit the remaining budget.

## Stages

Load the stage file only when it is needed. Resolve every path through
`${CLAUDE_SKILL_DIR}`; never search for a companion by bare filename.

| Stage | File | Outcome |
|---|---|---|
| Kickoff | `${CLAUDE_SKILL_DIR}/stage-0-kickoff.md` | Validated plan and approved bounds |
| Pipeline | `${CLAUDE_SKILL_DIR}/stage-1-2-pipeline.md` | Sequentially built, verified, and reviewed features plus integration evidence |
| End-review | `${CLAUDE_SKILL_DIR}/stage-3-endreview.md` | Human disposition and run report |

Begin by loading `${CLAUDE_SKILL_DIR}/stage-0-kickoff.md`.

## Outputs

- Per feature: `specs/<id>/ce-spec.md`, `tasks.json`, `verification.md`,
  `code-review.md`, and `review-summary.json`.
- Run supervision: `STATUS.md`, state, decision ledger, and metrics.
- Plan-level integration evidence: `verification-report.md`.
- Final report: `docs/plans/<slug>/ce-auto-build/<date>-run.md`.

The report and evidence are review inputs. They are not a compliance attestation,
release approval, or proof that every defect was found.

## Honest Limitations

- Sequential execution favors predictable state and reviewability over speed.
- Deterministic gates prove their named conditions, not overall correctness or
  product fit.
- The cumulative scope gate proves that the run's diff stays within the union of
  selected specs. It cannot prove which sequential worker changed an earlier
  feature's already-approved file; the independent review must check each worker's
  returned file list against its own spec.
- Worker independence reduces shared-context bias but does not make model review
  equivalent to accountable human review.
- A capability gap, dirty baseline, exhausted bound, or unresolved human decision
  leaves the run partial by design.
