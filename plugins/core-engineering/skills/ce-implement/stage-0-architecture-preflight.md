# Implement — Stage 0 Architecture and Spec-Binding Preflight

Read `SKILL.md` first. Run sections 1–2 before trusting or compact-composing a
spec. Run section 3 after canonical `ce-spec.md` and `tasks.json` exist, before
changing `.gitignore` or code. Apply this on direct, auto-build, and resume
paths; upstream validation is not freshness evidence.

## 1. Validate the canonical plan

Require regular, non-symlink `plan.json`, `architecture-selection.json`,
`shared-context.md`, `feature-plan.md`, and `features/<id>.md`, then run:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/plan-lint.py" \
  docs/plans/<slug> --json
python3 "${CLAUDE_SKILL_DIR}/scripts/architecture-selection-lint.py" \
  docs/plans/<slug>/architecture-selection.json \
  --json
```

Exit 1 routes every hard or malformed-plan defect to Stage R. Exit 2 routes to
Stage R because no trustworthy contract was established. Missing current plan
authority or architecture disposition/direction is a hard stop.

From the lint-validated disposition, load every
`convergence.decision_refs` entry. It must be repository-relative, remain
inside the repository, and resolve to a readable regular ADR recorded as
`Status: accepted`. Any failure routes to Stage R.

## 2. Validate package publication state

Inventory direct children named `.architecture-publish-*` without following
symlinks. Any lock, stage, backup, or rejected transaction path may be live or
interrupted: stop, show every exact path, and route to
`/core-engineering:ce-architecture <slug>` for explicit human recovery.

Lstat the canonical `architecture` namespace. If anything occupies it,
including a partial directory, non-directory, symlinked directory, or broken
symlink, validate that exact path:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/architecture-lint.py" \
  docs/plans/<slug>/architecture --repo-root . --consumer --json
```

- Exit 0: record package status/revisions, relevant gaps, and repository drift.
- Exit 1: stop at `/core-engineering:ce-architecture <slug>`; the package is
  invalid or stale.
- Exit 2: stop with the exact error and the same recovery route.

Only a clean transaction scan plus lstat-confirmed namespace absence uses:

| Plan decision | Missing-package implementation disposition |
|---|---|
| `required` + convergence `converged` | Stop at `/core-engineering:ce-architecture <slug>` before trusting the spec or changing code. |
| `recommended` + selected direction + convergence `converged` | Stop at `/core-engineering:ce-architecture <slug>` before trusting the spec or changing code. |
| `recommended` + direction/convergence `deferred` | Continue with `Architecture: coverage gap — recommended package explicitly deferred`, exact triggers, rationale, convergence evidence, and decision refs. |
| `not-required` | Record `Architecture: N/A — plan disposition not-required` and its rationale. |

Any other pairing is a Stage-R defect.

## 3. Require the spec's exact current binding

After the plan/package preflight passes, but before treating the spec as
implementation authority, run:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/architecture_context.py" --repo-root . \
  check docs/plans/<slug>/specs/<id> \
  --plan-dir docs/plans/<slug> --feature <id> --json
```

- Exit 0: the tasks/Markdown contexts agree and match the current
  consumer-linted package receipt, revisions, and feature mapping, or the exact
  typed no-package state (`not-required` or `recommended-absent`).
- Exit 1: refuse implementation and route to
  `/core-engineering:ce-spec <slug>/<id>`; the specification is stale,
  mismatched, or unbound.
- Exit 2: stop as a tooling/integrity gap. Never reinterpret a missing helper,
  unreadable artifact, or un-runnable package validator as a match.

The architecture context cannot widen Scope Lock. Accepted ADRs remain binding.
