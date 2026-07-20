# Auto Build — Stage 3: Human End-Review

Load this file when the sequential pipeline finishes or stops at a bound. Load
`${CLAUDE_SKILL_DIR}/run-report-template.md` before writing the report.

## Gate 2 of 2 — End-Review

Lead with the decisions the human must make:

```text
Needs a decision:
- parked features and blocked dependents
- failed features or integration failures
- provisional product assumptions
- confirmed unresolved or suspected-high review findings
- manual:judgment criteria and explicit verification coverage gaps

Acknowledge:
- completed feature and verification index
- routine engineering decisions
- medium/low review findings
- budget used versus approved cap
```

Then provide the evidence in this order:

1. **Run boundary:** approved scope, baseline, budget/caps, and why the run ended.
2. **Parked, failed, and blocked work:** exact decision or failure, evidence, affected
   dependents, and owning follow-up (`/ce-plan`, `/ce-spec`, `/ce-implement`,
   `/ce-debug`, or `/ce-verify`).
3. **Decisions and assumptions:** provisional decisions first. The human accepts or
   overrides each material assumption. An override does not silently patch the
   result; it routes the affected feature and dependents back through the fixed
   pipeline in a new approved run.
4. **Verification:** link every per-feature `verification.md`, summarize integration
   evidence, and gather human verdicts for `manual:judgment` criteria.
5. **Independent review:** show confirmed, suspected, then lower-severity findings
   with their evidence and disposition.
6. **Coverage gaps:** unavailable tools, checks that could not run, and areas outside
   the selected scope. Do not describe the evidence bundle as a compliance or release
   attestation.
7. **Working-tree diff:** show the complete changed-file list and diff summary. The
   human owns acceptance, cleanup, commits, pull requests, and release actions.

Offer these final dispositions:

- **Accept the run output for later manual landing.** This is not permission to
  commit, push, open a PR, merge, or deploy.
- **Request repair.** Name the owning skill and affected features; the current run
  remains incomplete.
- **Leave parked.** Preserve evidence and stop.

Write `docs/plans/<slug>/ce-auto-build/<date>-run.md` from the bundled template and
record the human disposition. Nothing is automatically landed or discarded.

Close with:

```text
Auto-Build: <slug> — <date>
Completed: <N> · Parked: <P> · Failed: <F> · Blocked: <B>
Budget: <spent>/<approved estimate>
End-review: accepted for manual landing | repair requested | parked
Report: docs/plans/<slug>/ce-auto-build/<date>-run.md
Next: <one concrete human-owned action>
```
