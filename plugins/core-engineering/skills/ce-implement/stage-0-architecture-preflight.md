# Implement — Stage 0 Architecture and Spec-Binding Preflight

Read `SKILL.md` first. Complete this companion before trusting `ce-spec.md` or
`tasks.json`, changing `.gitignore`, or mutating code. Run it on direct,
auto-build, and resume paths; upstream validation and saved state are not
freshness evidence.

## 1. Classify the plan shape

For minimal mode, `feature-plan.md` is context while `ce-spec.md` +
`tasks.json` remain implementation authority. Any full-plan authority or
`architecture` namespace makes the shape mixed: stop and route the exact path
to `/core-engineering:ce-plan`, or to
`/core-engineering:ce-architecture <slug>` for obsolete-package human
disposition. Otherwise record
`Architecture: N/A — single-feature minimal plan`.

For a full plan, run:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/plan-lint.py" \
  docs/plans/<slug> --require-architecture-direction --json
python3 "${CLAUDE_SKILL_DIR}/scripts/architecture-selection-lint.py" \
  docs/plans/<slug>/architecture-selection.json --json
```

Exit 1 routes every hard or malformed-plan defect to Stage R. Exit 2 routes to
Stage R because no trustworthy contract was established. A legacy missing
disposition/direction (`A12`/`A13`) is a hard stop in this consumer path.

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
| `recommended` | Continue with `Architecture: coverage gap — recommended package absent`, exact triggers, rationale, convergence evidence, and decision refs. |
| `not-required` | Record `Architecture: N/A — plan disposition not-required` and its rationale. |
| `waived` | Continue with `Architecture: waived by human`, exact rationale, triggers, convergence evidence, decision refs, and residual risk. |

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
  typed minimal/not-required/recommended-absent/waived state.
- Exit 1: refuse implementation and route to
  `/core-engineering:ce-spec <slug>/<id>`; the specification is stale,
  mismatched, or legacy-unbound.
- Exit 2: stop as a tooling/integrity gap. Never reinterpret a missing helper,
  unreadable artifact, or un-runnable package validator as a match.

The architecture context cannot widen Scope Lock. Accepted ADRs remain binding.
