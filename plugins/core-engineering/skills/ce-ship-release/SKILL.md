---
name: ce-ship-release
description: |
  Cut a gated release decision for a verified plan — derive the semver bump + changelog from shipped features, assemble rollback-readiness, propose the tag and notes. Owns CHANGELOG.md; refuses GO over unverified work; never pushes, tags a remote, or deploys.
  Triggers: cut a release, decide a version bump, draft a changelog or release notes. Writes the CHANGELOG; /core-engineering:ce-ship-document writes user-facing docs.
argument-hint: "[plan-slug] [--version <v>] [--base <branch>]"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion, Skill
disable-model-invocation: true
---

# Ship Release

**Invocation input:** Plan to release (and optional --version / --base): $ARGUMENTS


Prepare and gate the decision to ship a verified plan — **decide, don't deploy**.

`/core-engineering:ce-ship-release` is the downstream-most pipeline tool. It reads what the pipeline has
already proven — the verification report, the code review, and the selected git range —
and turns it into a **ship-release package**: a proposed version bump, a
changelog derived from the shipped features, rollback-readiness plus
**Supply-Chain Evidence**, and a proposed tag + release notes, all gated on a
go/no-go the human owns. It writes one
decision artifact and (only on consent) the versioned `CHANGELOG.md`. It **never**
pushes, creates or moves a remote tag, deploys, or commits to a protected branch.

It sits at the end of the chain, after the work is built and verified:

```
plan → spec → implement → { verify · review } → release
```

Distinct from its neighbors:

- **vs `/core-engineering:ce-verify`** — verify proves the software *behaves*; release decides whether
  that proven state *ships*, and at what version. Release never re-tests — it reads
  verify's report and **refuses GO over unverified work**.
- **vs `/core-engineering:ce-ship-document`** — release owns the versioned `CHANGELOG.md` (it holds the
  version number); `/core-engineering:ce-ship-document` writes user-facing usage docs and never writes the
  changelog. The two never write the same file.
- **It is a gate, not a deployer.** Tagging, pushing, and deploying are the
  human's; release prepares the decision and stops at the go/no-go.

## Runtime Inputs

- **Plan slug (required):** resolve via `docs/plans/plans.json`; if missing, ask. Do not guess.
- **`--version` (optional):** an explicit target version, overriding the derived proposal.
- **`--base` (optional):** the base branch / ref the release is cut against (default: the release profile's `base_branch`, else the repo default — confirmed at Stage 0).
- **Loaded (read-only):** `docs/plans/<slug>/verification-report.md` (the proof); the code review — **both** the plan-level `code-review.md` **and** any per-feature `specs/<id>/code-review.md` (auto-build writes per-feature) for features in range; `plan.json` + `feature-plan.md` (shipped features, ship order); `docs/plans/vc-policy.md` (release profile); available SBOM files (CycloneDX / SPDX), SLSA provenance, artifact signatures, checksums, OpenSSF Scorecard output, and CI secret-scan / plugin-validation evidence; and the repo's git tags + history.

Writes `docs/plans/<slug>/release/<date>-release.md` (the decision package) and, in the same Stage 5 step, one dated per-release evidence pack under `docs/plans/<slug>/evidence-pack/<date>/` (`evidence-pack.py`, this skill's bundled copy — a compilation of the pipeline's recorded evidence, never overwritten) — and, only on explicit consent (Stage 5), the versioned `CHANGELOG.md` / release notes in the repo.

## Execution Contract

*Gate locator (HITL R5):* print `Gate N of M — <name>` at every interactive gate; compute M from the gates that actually fire this run, never a hardcoded constant.

1. **Decide, don't deploy.** Prepare the release decision; never push, deploy, or commit to a protected branch — the `git-guard` hook backstops that push / PR / protected-commit boundary. It **never creates or moves a tag**; tagging is held by the Stage-4 go/no-go gate and the human — and git-guard now backstops that too (`git tag <name>` → confirm; listing stays silent; hardenable via `CE_GIT_GUARD_TAG=deny` — see *Honest Limitations* for the surface this covers).
2. **No GO over unverified *or stale* work.** A release is gated on the verification report: every feature in the range must be `verified` (Stage 0's predicate) **and its recorded done-ness fresh** — `task-evidence.py check` (this skill's bundled copy, Stage 0) finds no `stale` task, i.e. every `done` task's proving commit is still in HEAD's ancestry — or its gap explicitly accepted by the human. Unverified → `/core-engineering:ce-verify`; **stale** (the verified report was cut against code this checkout no longer holds) → `/core-engineering:ce-implement` to re-derive, then `/core-engineering:ce-verify`. Do not certify over either.
3. **Evidence-bound.** Every changelog entry and readiness signal traces to a shipped feature, a verification result, a review finding, or a git fact (commit / tag / file). No claim without a source.
4. **Version is a proposal, not a verdict.** Derive a semver bump from the shipped features' nature; the human owns the final number (a material decision).
5. **Rollback-readiness is honest.** The checklist reports what *is* and *is not* reversible, and flags every unknown — it never fakes readiness for a destructive change with no recorded rollback.
6. **Supply-chain evidence is explicit.** Record whether SBOM, SLSA provenance, artifact signatures, checksums, OpenSSF Scorecard output, secret-scan status, and plugin-validation status exist for the release. Missing evidence is a release finding or accepted gap, never a silent pass.
7. **Read-only on code, specs, and git history — and owns the changelog.** Writes its decision artifact, and on consent the versioned `CHANGELOG.md`: it **appends** a new version section, **never rewriting prior sections**. `/core-engineering:ce-ship-document` never writes `CHANGELOG.md`.
8. **Never commit, push, tag a remote, or deploy.**

## Scope Lock — the release decision  [decide, don't deploy]

Release holds no authority to ship. It assembles the decision and gates it; the
human executes `git tag`, the push, and the deploy. If the readiness check is red —
unverified work, an unaccepted high-severity finding, a destructive change with no
rollback — release **withholds GO** and routes to the layer that fixes it
(`/core-engineering:ce-verify`, `/core-engineering:ce-review` triage, or the human release owner), rather than shipping anyway. A release
cut over a red gate is exactly the silent degradation the toolset forbids.

## Release-Readiness Gate  [material]

The go/no-go, presented after the version, changelog, and rollback-readiness are
assembled. GO requires, and the human attests:

- every feature in the range is `verified` **and its done-ness `fresh`** — no `stale` task whose proving commit left HEAD's ancestry — (or its gap explicitly accepted);
- no unresolved high-severity `code-review.md` finding (or each accepted);
- every destructive / irreversible change in the range has a recorded rollback path, or its absence is explicitly accepted;
- SBOM / SLSA provenance / signatures / checksums / OpenSSF Scorecard / secret-scan evidence is present, or each missing item is explicitly accepted as a release gap;
- the proposed version + changelog are approved.

`Go / Adjust / No-go`. A No-go names the blocker and routes to the fixing skill.

## Human-in-the-Loop — tiered

- **Stage 0 (material)** — confirm the plan, the release range, and the base.
- **Stage 1 (material)** — the version number (release proposes; the human owns).
- **Stage 4 (material)** — the Release-Readiness Gate (go/no-go).
- **Stage 5 (material)** — consent before writing `CHANGELOG.md` to the repo.
- Routine — changelog wording and grouping.

---

## How to Run This Workflow

This skill is **staged**. `SKILL.md` (this file) is the orchestrator: it holds the
Runtime Inputs, the Execution Contract, the Scope Lock, the
Release-Readiness Gate, the tiered HITL, the Escalation table, and the Honest
Limitations. The stage bodies — the run flow, the `release.md` artifact template,
and the Closing — load on demand.

**The stage file named below is bundled in this skill's own directory.** Read it at `${CLAUDE_SKILL_DIR}/stages.md` — `${CLAUDE_SKILL_DIR}` is the environment variable that resolves to this skill's directory regardless of the current working directory. Resolve it once if needed (`ls "${CLAUDE_SKILL_DIR}"`) and read the file by its resulting absolute path; **never load a companion file by bare name** — in an installed plugin the working directory is the user's project, so a bare name finds nothing and triggers a filesystem search.

| Stage | Name (in `${CLAUDE_SKILL_DIR}/stages.md`) |
|---|---|
| 0 | Load and Scope the Release |
| 1 | Version Decision  [material] |
| 2 | Changelog |
| 3 | Rollback-Readiness and Supply-Chain Evidence |
| 4 | Release-Readiness Gate  [material] |
| 5 | Write the Decision and Hand Off |

`${CLAUDE_SKILL_DIR}/stages.md` also holds the `release.md` artifact template and the Closing.

To begin: load `${CLAUDE_SKILL_DIR}/stages.md` and start Stage 0.

---

## Escalation

Release decides; when readiness is red it withholds GO and routes:

| Blocker | Route |
|---|---|
| A feature in range is not `verified` | `/core-engineering:ce-verify` — prove it first |
| A feature in range is `stale` (a `done` task's commit left HEAD's ancestry) | `/core-engineering:ce-implement` — re-derive the stale tasks, then `/core-engineering:ce-verify` |
| Unresolved high-severity review finding | `/core-engineering:ce-review` triage → `/core-engineering:ce-implement` or `/core-engineering:ce-spec` |
| Destructive change with no rollback the human won't accept | `/core-engineering:ce-spec <id>` — specify the rollback **requirement** as acceptance criteria (forward + reverse steps) that `/core-engineering:ce-implement` builds and `/core-engineering:ce-verify` proves |
| Missing SBOM / provenance / signature / checksum / OpenSSF Scorecard evidence the human won't accept | Release engineering / CI hardening owns generation; use `/core-engineering:ce-review` if missing evidence changes release risk |
| The selected base/head range or release branch is stale / wrong | Human release owner corrects the branch or ref, then reruns `/core-engineering:ce-ship-release` |
| Scope / boundary is wrong | `/core-engineering:ce-plan` |

*Rehearsing or executing a rollback remains the human's — no skill in this toolset
runs or tests a production rollback (there is deliberately no `/migrate`).* Release
never resolves these itself; it gates on them.

---

## Honest Limitations

- **Decides, does not deploy.** Prepares the release decision; tagging, pushing,
  CI/CD, infra provisioning, and deploy orchestration are the human's — out of scope.
- **Tag backstop is Claude Code-surface only.** `git-guard` now guards `git tag
  <name>` (create / move / delete → confirm; listing stays silent; `CE_GIT_GUARD_TAG=deny`
  to hard-block) alongside push / PR / protected-branch commits — the no-tag
  discipline is structural on the Claude Code surface. Actions taken through
  other clients are outside these hooks; host protections and the human release
  owner remain the boundary there.
- **Semver is inferred, not proven.** A breaking change the specs / ADRs didn't
  record as breaking can slip the bump; the human owns the final number.
- **Rollback-readiness is a checklist, not a tested rollback.** It records whether a
  rollback *path exists*, not that it *works* — rehearsing it is the human's.
- **Supply-chain evidence records presence; it does not generate SBOMs, SLSA
  provenance, signatures, checksums, or OpenSSF Scorecard results.** Build and
  release engineering own those artifacts and any formal attestation.
- **Reads verification, doesn't re-run it — but stale done-ness is now caught.** A
  release is only as sound as the verification report it trusts, and it never re-runs
  the tests. It **does** re-verify freshness: `task-evidence.py check` (Stage 0)
  confirms each in-range feature's `done` commits are still in HEAD's ancestry, so a
  report cut against work that was since reverted or rebased away is downgraded to
  `stale` and **blocks GO** rather than certifying silently. Residual: a report stale
  for a reason freshness can't see — a semantic regression over unchanged commits —
  still needs a fresh `/core-engineering:ce-verify` run; the freshness check is commit-deep, not
  behaviour-deep.
- **Changelog is derived from the plan's shipped features**, not from every commit —
  work outside the plan isn't seen.
- **The per-release evidence pack is compilation, not attestation.** Stage 5
  compiles one dated `evidence-pack/<date>/` bundle (`evidence-pack.py`) of what the
  pipeline recorded — guard log, metrics, gate verdicts, attestations, model
  identity, and the accepted-risk register — each section populated or gap-listed; it
  is **not a conformity assessment** and renders no compliance verdict (see
  `docs/ENTERPRISE-HARDENING.md` § *Regulatory Mapping — EU AI Act*). It does not
  change the go/no-go, and compiling it is best-effort — a failure is a release
  finding, never a block on the decision.
- **A release ships with its accepted risk stated, not hidden.** The pack's
  `finding_dispositions` section renders every entry in `.merge-bar/dispositions.json`
  — the gate findings a human consciously accepted, with who accepted them and when
  the acceptance lapses — split active vs expired. An **expired** entry is a gap in
  the pack (its finding is already re-alarming through its gate). The register is
  reported as found and never re-judged: this skill does not verify that the named
  `accepted_by` approved it. What constrains it is out of band — `.merge-bar/**` sits
  in the merge policy's `class_rules`, so editing the ledger escalates to two-human
  review.
