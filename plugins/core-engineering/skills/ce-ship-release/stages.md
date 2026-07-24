# ce-ship-release — Stages

The orchestrator is `SKILL.md`. Keep all inspection read-only until the final
Release Decision authorizes the package write and, for GO, changelog append.

## Stage 0 — Resolve range and hard evidence

Resolve one registered plan and the requested/default base and HEAD. If no tags
exist, use `(initial)..<head>`; otherwise derive the range from the latest
applicable release tag. Ask only when multiple bases/tags plausibly define a
different release.

Resolve the exact full release `HEAD` commit once. Before interpreting plan
evidence, validate the resolved plan and architecture authority:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/architecture-selection-lint.py" \
  docs/plans/<slug> --repo-root . --json
python3 "${CLAUDE_SKILL_DIR}/scripts/plan-lint.py" \
  docs/plans/<slug> --json
```

Both commands must return valid JSON and exit 0. Exit 1 means the plan or
architecture direction is semantically invalid; exit 2 means current authority
could not be established. Both block release and route to
`/core-engineering:ce-plan`. Non-current or reportless architecture selections
cannot authorize release.

Identify in-range features from the validated plan evidence and git history.
For each in-range feature:

1. run strict task freshness:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/task-evidence.py" check \
     docs/plans/<slug>/specs/<id>/tasks.json --strict --json
   ```

2. run the current review receipt gate:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/review-gate.py" \
     docs/plans/<slug>/specs/<id> \
     --repo-root . --plan-dir docs/plans/<slug> --feature <id> \
     --git-repo . --evaluated-commit <full-head-sha> \
     --require-blocking-route --json
   ```

After the feature set is fixed, run one verification receipt check with one
`--feature` argument per exact in-range feature:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/verification-gate.py" check \
  docs/plans/<slug> --repo-root . --evaluated-commit <full-head-sha> \
  --feature <id-1> --feature <id-2> --json
```

For all three tools, require valid JSON and exit 0:

- task exit 1 means stale or unstamped task evidence; exit 2 means freshness
  could not be established. Route to implement, then verify;
- review exit 1 means a current confirmed-High correctness/security finding;
  exit 2 means review evidence is missing, malformed, unsafe, or stale. Route
  both to review or its recorded repair owner;
- verification exit 1 means current evidence records incomplete
  implementation, partial/failed verification, or rejected/deferred
  acceptance; exit 2 means its report/receipt/bindings are missing, malformed,
  unsafe, or stale. Route both to verify or the owning repair workflow.

Every exit 1/2, malformed/no result, or mismatched evaluated commit blocks
workflow GO. A human acknowledgement cannot replace a gate. A wrong checkout,
range, or head belongs to the human release owner.

Record the exact task, review, and verification commands; artifact paths;
evaluated commit; repository-state receipt; exits; and parsed results. Do not
re-derive behavior from prose or reuse a result after the candidate head
changes.

## Stage 1 — Documentation readiness

Classify the in-range change:

| Status | Evidence required |
|---|---|
| `not-required` | no changed user/operator journey, CLI/API/config surface, migration/upgrade step, runbook, or public compatibility promise |
| `required` | at least one such surface changed; a current ship-document manifest maps every affected feature/surface to a real doc and records example results |
| `audit-required` | required docs include executable onboarding/usage/API examples, privileged/production operations, destructive migration/rollback, or safety/compliance-sensitive instructions |

For `required`/`audit-required`, read the newest applicable
`docs/plans/<slug>/docs/<date>-docs-manifest.md` and confirm:

- it covers the current in-range feature/spec/verification revisions;
- referenced doc files and tested examples still match their recorded hashes or
  source state;
- no affected reader-facing surface is marked undocumented;
- failed examples or accuracy-gate failures are resolved or explicitly remain
  release blockers.

For `audit-required`, also read the newest applicable
`docs/doc-audits/<date>-<doc-slug>.md`; confirm the target doc, reader role, and
source state match, required steps ran or have an explicit coverage gap, and no
unaccepted blocking/high-severity finding remains.

Missing/stale required docs block GO and route to ship-document. Missing/stale
required audit blocks GO and routes to doc-audit. A clean `not-required`
classification is recorded evidence, not a human attestation question.

If ship-document or doc-audit changes any repository file, stop this release
run. The human first incorporates those changes into the candidate HEAD; then
rerun both `/core-engineering:ce-review` and `/core-engineering:ce-verify` and
restart at Stage 0. Their receipts intentionally bind the post-documentation
candidate. Do not reuse a pre-documentation receipt or continue directly to
version selection.

## Stage 2 — Version, changelog, and known issues

Propose semantic version:

- initial release: recommend an explicit `0.x` or `1.0.0` based on product
  maturity;
- major: an in-range incompatible public contract/schema/surface change;
- minor: new backward-compatible capability;
- patch: fixes/internal changes only.

An explicit `--version` is still reviewed at the final gate. Cite the feature or
compatibility evidence driving the proposal.

Draft Added/Changed/Removed/Fixed entries in ship order. Every entry cites a
feature/spec/verified behavior or git fact. Carry open verification issues and
accepted review/doc-audit findings into Known Issues. Do not hide accepted risk
or claim undocumented behavior.

## Stage 3 — Rollback and supply-chain evidence

For every destructive/irreversible data, schema, configuration, external-effect,
or public-surface change, record:

| Change | Forward evidence | Rollback/mitigation | Tested? | Residual risk | Owner |
|---|---|---|---|---|---|

Use `ready`, `manual`, or `unknown`; never imply rollback was tested when it was
only described.

Inventory available:

- SBOM and scope;
- build provenance;
- artifact checksum/signature and stated signer identity;
- OpenSSF Scorecard;
- secret/dependency/infrastructure scans;
- CI/plugin validation and release-policy evidence.

Mark missing items and governing policy. Passing CI does not imply that a
separate artifact exists.

## Stage 4 — Release Decision

Render the complete readiness summary from `SKILL.md`. If a hard prerequisite
fails, recommend NO-GO and omit the GO option.

At `Gate N of M — Release Decision`, the human may:

- approve GO and the exact version/package/changelog append;
- adjust version or package content and return to this same locator;
- approve a NO-GO decision package;
- park without a write.

An external decision to ship across a hard blocker is recorded only as
`NO-GO — external exception by <owner>`.

## Stage 5 — Write and hand off

Resolve the same-day `<release-key>`. Write:

```text
docs/plans/<slug>/release/<release-key>-release.md
```

Use:

```markdown
# Release Decision — <version>

> Plan/range: <slug> · <base>..<head>
> Decision: GO | NO-GO | NO-GO — external exception
> Approved by/reference: <human authority>

## Version and rationale
## Shipped features
## Changelog
### Added
### Changed
### Removed
### Fixed
### Known Issues
## Verification and Review Freshness
<task-evidence, review-gate, and verification-gate commands/exits; exact
evaluated commit; receipt paths; repository-state digest; per-feature result>
## Documentation Readiness
<impact classification, manifest/audit paths and freshness, gaps>
## Rollback Readiness
## Supply-Chain Evidence
## Accepted Risks and Blockers
## Execution Handoff
<human commands only; not executed>
## Evidence Index
```

For GO, append the approved version section to `CHANGELOG.md`; never alter
prior sections. For NO-GO, do not modify `CHANGELOG.md`.

Compile:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence-pack.py" \
  docs/plans/<slug> \
  --guard-log .claude/ce-guard-log.jsonl \
  --merge-verdict <release-or-CI-verdict-if-present> \
  --out docs/plans/<slug>/evidence-pack/<release-key>
```

The pack destination is never overwritten. Record a compile failure as a
release evidence gap; never call the pack a conformity assessment.

Close with the decision, version, range, decision path, evidence-pack path,
documentation/audit status, hard blockers/accepted risks, and the human-owned
tag/push/deploy commands. Do not execute those commands.
