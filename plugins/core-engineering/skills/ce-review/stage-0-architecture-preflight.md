# Review — Outbound Architecture and Provenance Preflight

Read `SKILL.md` first. Run this companion for every outbound feature, including
autonomous review. It is read-only and precedes findings.

## 1. Validate the plan and selected direction

Before trusting the spec, require the canonical plan authorities and run:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/plan-lint.py" \
  docs/plans/<slug> --json
python3 "${CLAUDE_SKILL_DIR}/scripts/architecture-selection-lint.py" \
  docs/plans/<slug>/architecture-selection.json \
  --json
```

Exit 1 routes plan/selection defects to `/core-engineering:ce-plan`. Exit 2
stops as an integrity/tooling gap. Load each validated
`architecture_disposition.convergence.decision_refs` path and require one
regular in-repository ADR with `Status: accepted`.

## 2. Validate publication state and package

Inventory direct `.architecture-publish-*` children without following
symlinks. Any lock, stage, backup, or rejected path stops review and routes to
`/core-engineering:ce-architecture <slug>` for human recovery.

If the canonical `architecture` namespace has any occupant, validate it:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/architecture-lint.py" \
  docs/plans/<slug>/architecture --repo-root . --consumer --json
```

Exit 0 permits consumption and surfaces package gaps/repository drift. Exit 1
or 2 stops review at `/core-engineering:ce-architecture <slug>`.

Only confirmed absence uses:

| Plan decision | Review disposition |
|---|---|
| `required` + `converged` | Stop; the governed package must exist. |
| `recommended` + selected direction + `converged` | Stop; the governed package must exist. |
| `recommended` + direction/convergence `deferred` | Continue with the typed `recommended-absent` gap visible. |
| `not-required` | Continue with typed N/A. |

## 3. Verify the spec binding

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/architecture_context.py" --repo-root . \
  check docs/plans/<slug>/specs/<id> \
  --plan-dir docs/plans/<slug> --feature <id> --json
```

Exit 0 proves tasks/Markdown parity and freshness against the current
consumer-linted package receipt/feature mapping or typed no-package state.
Exit 1 routes to `/core-engineering:ce-spec <slug>/<id>` before findings: a
review against a stale or unbound spec is not conformance evidence.
Exit 2 stops as a tooling/integrity gap.

## 4. Bind the review result

Immediately before writing `review-summary.json`, re-run the binding read:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/architecture_context.py" --repo-root . \
  review-binding docs/plans/<slug>/specs/<id> \
  --plan-dir docs/plans/<slug> --feature <id> --json
```

Copy the returned `binding` object exactly. It binds current plan, feature,
spec, tasks, architecture context, producer package receipt, and repository
commit digests, plus deterministic content records for every in-scope
`tasks[].files` path and the complete tracked/non-ignored repository state
(excluding only post-binding review/auto-build evidence). Exit 1/2 prevents
writing a current-state review summary. Never reuse a binding from an earlier
review pass. A task with no file scope is an integrity gap: review cannot claim
freshness for an unknown implementation surface.
