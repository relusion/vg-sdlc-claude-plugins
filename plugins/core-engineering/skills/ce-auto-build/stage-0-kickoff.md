# Auto Build — Stage 0: Kickoff

Read `SKILL.md` first. This stage validates the run and obtains the only approval
before the autonomous loop.

**Next:** after approval and state initialization, load
`${CLAUDE_SKILL_DIR}/stage-1-2-pipeline.md`.

## 1. Resolve and lint the plan

Resolve the slug through `docs/plans/plans.json`. Read `plan.json`,
`shared-context.md`, the selected feature files, their hard dependencies, the plan's
threat model and interaction contract when present, and relevant ADRs.

Run the structural gate before any spawn:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/plan-lint.py" docs/plans/<slug> --json
```

- `exit 0`: continue.
- `exit 1`: stop and route the reported planning defects to `/core-engineering:ce-plan`.
- `exit 2`: stop because auto-build cannot establish a trustworthy plan. A human
  may choose an interactive workflow instead.

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
Required checks: <commands/capabilities>
Coverage gaps: <none or exact gaps>
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
