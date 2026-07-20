# ce-verify — Stage 3: Acceptance and Report

Stage file for the `ce-verify` skill (orchestrator: `SKILL.md`). Covers presenting the result, stakeholder acceptance, and writing `verification-report.md`. Load this file after Stage 2.6 is complete or recorded N/A.

**Next:** Stage 3 closes the workflow — return to `SKILL.md` for the Escalation table and the Closing block. At the write step, also read `${CLAUDE_SKILL_DIR}/artifact-template.md` for the Report Template.

---

## Stage 3 — Acceptance and Report

### 3.1 Present the Result

Summarize:

- Stage 1: whole-suite, build, lint/type-check, criteria re-confirmation, bridges, and dependency-manifest integrity (dep-guard).
- Stage 2: per-journey walk, verdict, and evidence.
- Stage 2.5 (when fired): the durable-noun revisit / switch / amend verdict, and the data-class-keyed governance-reciprocal (retain / export / erase) verdict — N/A where the stage recorded N/A.
- Stage 2.6 (when fired): the surface-removal continuity verdict — N/A where the stage recorded N/A.
- Open issues: failures, blockers, deferred items, escalations raised.

### 3.2 Stakeholder Acceptance  [material — pre-handover only]

In **pre-handover** mode, present each verified journey as a walkable scenario
to the stakeholder; capture sign-off via `AskUserQuestion`:
`Accept` / `Reject` / `Defer`. Milestone mode skips this — the journey verdicts
from Stage 2 are the result.

### 3.3 Write the Report

Write `verification-report.md` to the plan directory, per the Report Template in
`${CLAUDE_SKILL_DIR}/artifact-template.md` (do not reconstruct it from memory). The file is
**cumulative**:

**The artifact template is bundled in this skill's own directory.** Read it at
`${CLAUDE_SKILL_DIR}/artifact-template.md` — `${CLAUDE_SKILL_DIR}` is the
environment variable that resolves to this skill's directory regardless of the
current working directory. Resolve it once if needed (`ls "${CLAUDE_SKILL_DIR}"`)
and read the file by its resulting absolute path; **never load the template by
bare name** — in an installed plugin the working directory is the user's project,
so a bare name finds nothing and triggers a filesystem search.

- Milestone runs add or update their journey's section.
- The pre-handover pass completes the whole-system sections and stakeholder
  sign-off.

**The report's Per-Feature Status is a derived roll-up, not a new verdict** — each
cell traces to the sections above and `Verified` is their AND. In **milestone** mode
a feature whose owned journeys are not all walked yet reads `partial (n-of-m
journeys)`, never an unqualified `Verified`; only the **pre-handover** pass asserts a
whole-feature `Verified`. This report is the **single owner of the per-feature
verified rule**: `/core-engineering:ce-ship-release` and `/core-engineering:ce-ship-document` read its `Verified` column (scoped to
their own range / audience) instead of re-deriving feature state — so write it to be
read that way.

**Metrics (best-effort, optional).** After writing, append a `stage-complete` line (`stage: "verify"`) — plus a `gate` line per check and any `escalation` — to `docs/plans/<slug>/.metrics.jsonl` per the `retro` skill's schema. Derive from data already produced, label token figures estimates, and **never** let this block or fail verification. It powers `/core-engineering:ce-retro`.
