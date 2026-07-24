# ce-verify — Stage 0–1: Load, Scope, and Automated System Check

Stage file for the `ce-verify` skill. The orchestrator is `SKILL.md` — read it first for the Runtime Inputs, Execution Contract, Human-in-the-Loop moments, and the Escalation table. Load this file when you begin Stage 0.

**Next:** when Stage 1 is complete, load `${CLAUDE_SKILL_DIR}/stage-2-2.6-walks.md`.

---

## Stage 0 — Load and Scope

### 0.1 Locate the Plan

Find the plan directory containing the target. If multiple
`docs/plans/*/` directories exist, ask the user. Load all read-only
inputs listed above.

### 0.2 Validate Current Plan Authority

Before interpreting feature state, run both validators against the resolved plan:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/architecture-selection-lint.py" \
  docs/plans/<slug> --repo-root . --json
python3 "${CLAUDE_SKILL_DIR}/scripts/plan-lint.py" \
  docs/plans/<slug> --json
```

Both commands must return valid JSON and exit 0. Exit 1 means the current plan
or architecture direction is semantically invalid; exit 2 means it could not be
validated safely. Stop either way and route to `/core-engineering:ce-plan`.
Non-current or reportless architecture authority, a selected direction without
its hash-bound comparison report, and an incomplete/malformed `plan.json` all
block verification.

### 0.3 Derive Feature State

For each feature in `plan.json`, derive its current state from the artifacts. A `done`
flag is trusted only after its evidence is re-verified against this checkout — run the
freshness check per feature (this skill bundles its own copy) and treat a **stale** task
(its `commit_sha` is no longer in HEAD's ancestry) as **not done**:

```
python3 "${CLAUDE_SKILL_DIR}/scripts/task-evidence.py" check specs/<id>/tasks.json --json
```

Invoke it by its `${CLAUDE_SKILL_DIR}` path, never a bare name (the same rule the
`dep-guard.py` invocation below carries). Exit 1 ⇒ at least one `done` task is stale.

| State | Condition |
|---|---|
| `implemented` | `specs/<id>/tasks.json` exists, every task `status` is `done` **and the freshness check finds none `stale`**, and `specs/<id>/verification.md` exists |
| `stale` | the implemented shape holds on disk, but `check` verdicts ≥1 `done` task `stale` — the recorded done-ness points at a commit this checkout doesn't contain (reverted / rebased away / a different branch). **Not** verifiable until re-derived: route to `/core-engineering:ce-implement` to re-run the stale tasks, then re-verify. |
| `specced` | `specs/<id>/ce-spec.md` exists but the implemented condition is not met |
| `planned` | otherwise |

Verify operates on the **implemented subset** at this moment in time — a `stale`
feature is excluded from it (reported, then routed to `/core-engineering:ce-implement`), never verified
over evidence this checkout can't stand behind.

### 0.4 Determine Scope

- **Milestone mode** (`<journey>` argument): the target journey. Every feature
  composing it must be `implemented` — else stop and report which are not.
- **Pre-handover mode** (no argument): the whole project. If any feature is not
  `implemented`, report them and ask the human: proceed in *partial* mode
  (verify what is there), or abort and finish them first.

When the selected journey or complete pre-handover scope resolves
unambiguously, announce it and continue. Ask only for multiple matching plans/
journeys or the material choice to accept partial coverage.

---

## Stage 1 — Automated System Check

Run the following against the implemented features in scope. Use the build /
test / lint commands recorded in `shared-context.md`'s codebase profile. Allow
generous time for full suites.

- **Whole-project test suite** — every `auto` test across in-scope features. A
  pass at implement time may have regressed since; this catches cross-feature
  regressions.
- **Project build, lint, and type-check** — must succeed.
- **Acceptance-criteria re-confirmation** — for each in-scope feature, every
  acceptance criterion must still trace AC → test cases → currently-passing
  tests. A criterion that held at ship time but fails now is a regression.
- **Bridge retirement** — for every bridge in `feature-plan.md` whose
  `replaced_by` feature is `implemented`, inspect the codebase for residual
  bridge code. A bridge that outlives its replacer is a defect.
- **Dependency-manifest integrity** — the cross-feature backstop for the
  per-task dependency gate: run this skill's bundled `dep-guard.py` over the
  in-scope features' manifest diff (using the package manager from
  `shared-context.md`'s codebase profile):
  ```
  python3 "${CLAUDE_SKILL_DIR}/scripts/dep-guard.py" --base <plan-start ref> --head HEAD --declared <verified dep names from the RPD ledger>
  ```
  `${CLAUDE_SKILL_DIR}` resolves to this skill's directory regardless of the
  current working directory — **never invoke it by bare name** (`dep-guard.py`), which
  in an installed plugin finds nothing and triggers a filesystem search (the same
  rule the artifact template carries below). A new direct dependency that traces to
  **no** verified-dependency entry in the Resolved Project Decisions ledger (the
  `RPD-N` rows in `shared-context.md`) is an **undeclared** dep — a dep
  that entered the codebase outside the spec, the slopsquatting smoking gun — and
  fails; a typosquat-near-popular advisory is surfaced for the human. Pass the
  ledger's verified dep names as `--declared`; the undeclared check is **ON by
  default**, so a plan with no recorded verified deps fails *every* new direct dep
  as undeclared — escalate each for the human to confirm-or-remove, **never a silent
  pass** (`--detect-only` only for an explicitly non-gating exploratory read). The
  *network* existence re-check was implement's job — verify detects-and-escalates,
  it does not re-query the registry.

Report each check `pass` / `fail` with evidence. Any failure routes to
escalation (below) — verify does not attempt a fix.
