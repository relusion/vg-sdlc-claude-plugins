---
name: ce-ship-release
description: |
  Prepare the final human-owned release decision for a verified, reviewed, documented plan range. Derives version and changelog, checks fresh implementation evidence, documentation/doc-audit readiness, rollback, and supply-chain evidence, then writes a decision package on approval. Never tags, pushes, deploys, or claims compliance.
  Triggers: cut a release, decide a version, draft release notes, or make a release go/no-go decision. /core-engineering:ce-ship-document owns product docs; /core-engineering:ce-doc-audit validates reader workflows.
argument-hint: "[plan-slug] [--version <v>] [--base <ref>]"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion, Skill
disable-model-invocation: true
---

# Ship Release

**Invocation input:** $ARGUMENTS

Prepare the evidence-backed decision to ship. This is the final workflow after
review, verification, required documentation, and any required documentation
audit. It decides and records; it never tags, pushes, deploys, or commits.

```text
plan → architecture? → spec → implement → {review + verify}
     → ship-document? → doc-audit?
     → {refresh review + verify when docs/audit changed state}
     → ship-release
```

## Runtime Inputs

- Plan slug, resolved through `docs/plans/plans.json`.
- Optional explicit `--version` and `--base`.
- Current `plan.json`, feature plan, git range/tags, verification report and
  `verification-summary.json`, in-range `review-summary.json` artifacts, and
  strict task evidence.
- Documentation impact evidence, latest applicable
  `docs/plans/<slug>/docs/<date>-docs-manifest.md`, and applicable
  `docs/doc-audits/<date>-<slug>.md`.
- Rollback/forward plans and available SBOM, provenance, checksums, signatures,
  Scorecard, secret-scan, CI, and plugin-validation evidence.

Writes:

- `docs/plans/<slug>/release/<release-key>-release.md`;
- `docs/plans/<slug>/evidence-pack/<release-key>/`;
- an appended version section in `CHANGELOG.md` only as part of an approved GO.

**Same-day collision rule:** use `<date>` first; if either release artifact or
evidence-pack destination exists, use `<date>-2`, then `<date>-3`. Never
overwrite or split one release across keys.

## Execution Contract

1. Validate state before recommendation. Every in-range feature must pass three
   independent deterministic checks: `task-evidence.py check --strict`,
   `review-gate.py`, and the plan-level `verification-gate.py` selection for the
   exact release head. Missing, failing, malformed, or stale evidence blocks GO.
2. Review and verification are separate evidence. `review-gate.py` re-derives
   each feature's plan/spec/tasks/implementation/repository binding;
   `verification-gate.py` independently binds the cumulative behavior report,
   plan revision, in-range implementation state, per-feature verdict, and
   acceptance. Never infer either result from Markdown prose.
3. Classify documentation impact from shipped public, operational,
   configuration, migration, and interface changes:
   - `not-required` only with concrete evidence that no reader-facing behavior
     changed;
   - `required` needs a current ship-document manifest covering the release
     range;
   - `audit-required` additionally needs a current doc-audit when a
     getting-started/runbook/API example, destructive/migration procedure,
     privileged operation, or safety-critical instruction changed.
4. Missing required documentation routes to
   `/core-engineering:ce-ship-document`. Missing/failed required audit routes to
   `/core-engineering:ce-doc-audit`. Neither is converted to a human checkbox.
   After either workflow changes repository state, the human incorporates those
   changes into the candidate HEAD, reruns both review and verification, and
   restarts release Stage 0. Pre-documentation receipts are stale by design.
5. Every changelog claim traces to a shipped feature, verified behavior, accepted
   review finding, or git fact.
6. Version is a recommendation; the human owns the release number.
7. Record rollback and supply-chain gaps honestly. An evidence pack is a
   compilation, not compliance attestation.
8. A workflow GO cannot waive failed/stale task, review, or verification gates,
   missing required product documentation, or missing required doc audit. An
   external release owner may ship anyway, but this package remains
   `NO-GO — external exception`.
9. Final GO approves the version, release content, accepted risks, decision
   artifact, and changelog append in one gate.
10. Never tag, push, deploy, rewrite prior changelog sections, or modify code,
    specs, reviews, verification, documentation, or git history.

## Release-readiness decision

GO requires:

- exact plan, base/head range, and release content are resolved;
- every in-range feature has current passing task, review, and verification
  gate results for the exact evaluated head;
- documentation impact is evidenced and every required doc/manifest/audit is
  current with no unaccepted blocking finding;
- destructive/irreversible change has a rollback path or an explicitly accepted
  release risk where workflow policy allows acceptance;
- supply-chain evidence is inventoried and each allowed gap is explicit;
- version, changelog, known issues, and execution handoff are approved.

The task/review/verification freshness gates and required-doc/audit predicates
are non-waivable inside this workflow. Organizational policy may make
additional predicates non-waivable.

## Human-in-the-Loop — adaptive

Do not confirm a plan/range/base that resolves unambiguously from invocation and
git evidence. Ask only when several plausible release ranges or version
authorities exist.

The normal run has one material gate:

```text
Gate N of M — Release Decision
Plan/range: <slug and base..head>
Version: <proposal + reason>
Documentation: <not-required|required complete|audit complete|blocked>
Verification/review: <gate exits, evaluated head, receipt paths, current binding summary>
Rollback/supply-chain: <ready, accepted gaps, blockers>
Known issues: <items>
Recommendation: GO|NO-GO
```

When eligible, offer **Approve GO and write**, **Adjust version/package**,
**NO-GO**, and **Park**. When a hard prerequisite fails, omit GO and offer the
owning repair route, write a NO-GO package, or park. Silence is never release
approval.

## Scope Lock

The release range and decision are frozen for the run. This workflow may
describe or reject the candidate release; it cannot fix code, change the plan,
rewrite documentation, waive hard evidence, or execute release operations.

## How to run

Load `${CLAUDE_SKILL_DIR}/stages.md` and execute:

| Stage | Outcome |
|---|---|
| 0 | Resolve range and validate fresh verify/review/task evidence |
| 1 | Classify and validate documentation/doc-audit readiness |
| 2 | Propose version, changelog, and known issues |
| 3 | Assemble rollback and supply-chain evidence |
| 4 | Human Release Decision |
| 5 | Write decision/evidence pack and append changelog on GO |

## Escalation

| Gap | Owner/route |
|---|---|
| unverified behavior | `/core-engineering:ce-verify` |
| stale/unstamped task evidence | `/core-engineering:ce-implement`, then verify |
| missing/stale/failed verification receipt | `/core-engineering:ce-verify` |
| missing/stale review or blocking review finding | `/core-engineering:ce-review` |
| missing/outdated required docs | `/core-engineering:ce-ship-document <slug>` |
| missing/outdated required reader validation | `/core-engineering:ce-doc-audit <doc> --role <reader>` |
| plan/spec contradiction | `/core-engineering:ce-plan` Stage R or `/core-engineering:ce-spec` |
| missing rollback implementation/evidence | owning spec/implement/verify layer |
| wrong base/head or release branch | human release owner |
| missing supply-chain artifact | release engineering/CI owner |

## Honest Limitations

- Verification and review artifacts are point-in-time evidence. Their gates
  bind exact repository state and reject observable drift; they still cannot
  prove behavior outside the evidence and environment that were exercised.
- Semver inference cannot know every external compatibility promise.
- **Supply-Chain Evidence:** the workflow records presence; it does not generate SBOMs,
  SLSA provenance, signatures, or OpenSSF Scorecard reports, and it never
  represents the inventory as an assurance attestation.
- It cannot enforce actions performed outside repository hooks or host
  protections.
- A GO package is decision evidence, not proof that deployment succeeded.
