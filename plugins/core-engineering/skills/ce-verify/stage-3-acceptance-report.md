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

### 3.4 Derive the Current Verification Receipt

After the report bytes are final, derive—not hand-author—the compact release
receipt:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/verification-gate.py" create \
  docs/plans/<slug> --repo-root . --evaluated-commit HEAD --json
```

The script writes `docs/plans/<slug>/verification-summary.json`. It binds the
exact report hash, evaluated commit and reviewable repository state, plan
revision/hash, every reported feature authority/spec/tasks/implementation
verification file, task-declared implementation files, and the per-feature
verification/acceptance roll-up. The repository-state digest excludes only
peer review and workflow evidence expected to be written after verification;
those artifacts have their own receipts.

Exit 0 means the receipt was written and re-read successfully. Exit 2, malformed
output, or a missing command is a coverage failure: retain the report, stop the
verified handoff, and report the exact error. A failed behavioral verdict may
still have a valid receipt—the receipt proves what was evaluated, not that it
passed. Never edit JSON to convert a failed or partial verdict.

**Metrics (best-effort, optional).** After writing, append a `stage-complete` line
(`stage: "verify"`), one `attestation` line for each interactive gate that
actually fired, and any `escalation` lines to
`docs/plans/<slug>/.metrics.jsonl` using `/core-engineering:ce-retro`'s current
event schema. Close the invocation with exactly one best-effort `run-terminal`
line: `outcome: "completed"` when this workflow reached its documented handoff
(findings do not change that execution outcome), or the matching v2 terminal
outcome when a known failure, abort, park, escalation, or could-not-run path ends
the invocation. Reuse one `run_id` when available; include measured duration and
resolved model, Claude CLI, and plugin versions only when observable. Derive
values from evidence already produced, label token figures as estimates, and
never let telemetry block or fail verification. If the stream cannot be written,
report the coverage gap in the closing handoff. It powers
`/core-engineering:ce-retro`.
