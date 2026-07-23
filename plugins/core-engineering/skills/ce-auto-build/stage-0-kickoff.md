# Auto Build — Stage 0: Kickoff

Read `SKILL.md` first. This stage validates the run and obtains the only approval
before the autonomous loop.

**Next:** after approval and state initialization, load
`${CLAUDE_SKILL_DIR}/stage-1-2-pipeline.md`.

## 1. Resolve and lint the plan

Resolve the slug through `docs/plans/plans.json`. Read `plan.json`,
`shared-context.md`, the selected feature files, their hard dependencies, the plan's
threat model and interaction contract when present, the
`architecture_disposition`, its accepted-ADR `convergence.decision_refs`, and
other relevant ADRs.

Run the structural gate before any spawn:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/plan-lint.py" docs/plans/<slug> --require-architecture-direction --json
```

- `exit 0`: continue with the lint-validated manifest and human-bound direction.
- `exit 1`: stop and route the reported hard planning defects to
  `/core-engineering:ce-plan`. A malformed *present* disposition is one such
  defect; legacy `A12`/`A13` gaps are also blocking in this consumer mode.
- `exit 2`: stop because auto-build cannot establish a trustworthy plan. A human
  may choose an interactive workflow instead.

Before resolving the run baseline, run:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/architecture-selection-lint.py" \
  docs/plans/<slug>/architecture-selection.json \
  --require-current-schema --json
```

Exit 1 or 2 stops at `/core-engineering:ce-plan` Stage R. Never spawn from a
missing, malformed, hash-mismatched, hard-constraint-invalid, or unselected
direction artifact.

### 1.1 Enforce the architecture disposition

Do this after plan-lint and before resolving the run baseline, asking for kickoff
approval, initializing state, or spawning any worker. Apply it on both a fresh
run and `--resume`; durable run state never exempts the current plan/package
from this preflight. Read the lint-validated object exactly as written:

```text
architecture_disposition:
  decision: required | recommended | not-required
  triggers: [<stable trigger ids>]
  rationale: <non-empty>
  decided_by: human
  convergence:
    status: converged | deferred | not-applicable
    iteration_count: <non-negative integer>
    summary: <non-empty>
    decision_refs: [<repo-relative accepted ADR paths>]
```

Load each `decision_refs` ADR. A missing, unreadable, non-accepted, or
out-of-repository reference is a plan defect: stop and route to Stage R.
`decision: required` with any convergence status other than `converged` is also
a Stage-R stop; auto-build cannot finish architecture shaping inside an
unattended implementation run.
The only valid combinations are required with a selected direction and
`converged`; recommended with a selected direction and `converged`, or with
both direction and convergence explicitly `deferred`; and not-required with
both direction and convergence `not-applicable`.

Before classifying the canonical package as present or absent, inventory direct
children of the plan directory whose names start with
`.architecture-publish-`, without following symlinks. Any lock, stage, backup,
or rejected path means publication may be active or crashed. Stop, show every
exact path, and route to `/core-engineering:ce-architecture <slug>` for explicit
human recovery. Never delete a transaction path or call architecture absent
while one remains.

Use an lstat-style namespace check. If any entry named `architecture` occupies
the path — including a broken symlink, symlinked directory, non-directory, or
partial directory — validate that exact path before using it:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/architecture-lint.py" \
  docs/plans/<slug>/architecture --repo-root . --consumer --json
```

- `exit 0`: record the package status and architecture/source-plan revisions,
  load its feature mappings and gaps for the selected features, and surface
  repository-evidence drift advisories.
  `accepted-for-specification-with-gaps` adds the relevant gaps to kickoff
  coverage.
- `exit 1`: stop and route to `/core-engineering:ce-architecture <slug>`; the
  package is invalid or stale and cannot gate an unattended run.
- `exit 2`: stop with the exact error and the same architecture recovery route.
  Presence is never reinterpreted as absence.

Only lstat-confirmed namespace absence uses this matrix:

| Plan decision | Auto-build disposition |
|---|---|
| `required` + convergence `converged` | Stop and route to `/core-engineering:ce-architecture <slug>`; the required governed package has not been published. |
| `recommended` + selected direction + convergence `converged` | Stop and route to `/core-engineering:ce-architecture <slug>`; the selected direction requires its governed package. |
| `recommended` + direction/convergence `deferred` | Continue, but add `recommended architecture package explicitly deferred` plus triggers, rationale, convergence summary, and decision refs to kickoff coverage and the final report. |
| `not-required` | Record `Architecture: N/A — plan disposition not-required` and its rationale. |

An unknown decision/status combination is a plan defect to Stage R. Product,
security-acceptance, architecture, and boundary decisions discovered later still
park under the normal worker contract; a recommendation gap does not widen
worker authority.

Resolve the optional feature range to an explicit ship-ordered list. Reject unknown,
duplicate, non-contiguous, or dependency-invalid ranges.

## 2. Check the execution baseline

Require a clean working tree, including untracked files. Record the current commit as
the run baseline. If the tree is dirty, show the paths and stop so the human can
commit, stash, or remove them before retrying. Auto-build does not create a branch,
checkpoint existing changes, or mix them into its measured diff.

Confirm that required build, test, and lint commands are discoverable and runnable.
Check capabilities explicitly required by the selected features. A missing required
capability stops the run. A missing optional capability may proceed only when the
affected verification is clearly identified for the final human review; record the
coverage gap in the ledger.

No credentials are loaded. No destructive operation or external write is
pre-authorized by this workflow; any feature needing one will park.

## 3. Kickoff approval

Present one decision-ready prompt:

```text
Gate 1 of 2 — Auto-Build Kickoff
Plan: <slug>
Features: <explicit ids in ship order>
Baseline: <commit>
Architecture: <decision + convergence status + package status/revision, explicit deferral, or N/A>
Required checks: <commands/capabilities>
Coverage gaps: <none or exact gaps, including explicitly deferred recommended architecture>
Token/compute budget: <positive estimate>
Per-feature failure-attempt cap (`--retry-cap`): <positive integer; recommend 3>
Consecutive-park cap: <positive integer; recommend 3>
Writes: repository working tree and plan evidence only
Version control/external actions: none

Proceed / Adjust bounds or scope / Abort
```

Do not start workers until the human chooses **Proceed**. This approval authorizes
only the displayed repository scope and bounded local writes.

## 4. Initialize durable state

On Proceed:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/run-state.py" init \
  --plan-dir "docs/plans/<slug>" \
  --baseline <full-commit-id> \
  --feature <first-id> [--feature <next-id> ...] \
  --budget <approved-positive-budget> \
  --retry-cap <approved-positive-cap> \
  --park-cap <approved-positive-cap>
```

Exit `0` starts the run. Exit `2` means initialization was refused; if a same-day
state exists, use `--resume` and reconcile disk rather than overwriting it.

For `--resume`, do not run `init` and do not repeat completed work. Reload the exact
`baseline`, ordered `selected_features`, and approved bounds from state. Confirm that
the baseline still resolves in this repository and the working tree contains only
changes attributable to this run, then apply the disk-wins checks in `SKILL.md`. Never
accept a new range on resume. Reconstruct the cumulative verified dependency set from
the durable run ledger and verification evidence; if a dependency addition cannot be
attributed to that evidence, park as `tooling-gap` before starting another worker. If
provenance is ambiguous, stop for human review.

Regenerate the initial status board:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/status-board.py" \
  "docs/plans/<slug>" --write
```

A board-generation failure is recorded but does not replace any pipeline gate.
