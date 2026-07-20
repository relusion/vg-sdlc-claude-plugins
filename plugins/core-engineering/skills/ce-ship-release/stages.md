# ce-ship-release — Stages

Stage file for the `ce-ship-release` skill. The orchestrator is `SKILL.md` — read it first for the Runtime Inputs, the Execution Contract, the Scope Lock, the Release-Readiness Gate definition (Stage 4 runs it), the tiered HITL, the Escalation table, and the Honest Limitations. Load this file when you begin Stage 0.

---

## Stage 0 — Load and Scope the Release

Resolve the plan via `docs/plans/plans.json`. Read each feature's verified state from
the verification report's **Per-Feature Status** section — `verify` owns that
rule (`implemented` + every owned journey **Pass** + Criteria re-confirmation clean,
plus **Accepted** in a pre-handover report) and records the derived `Verified` cell
per feature, so do not re-derive it here. Treat a `partial` cell as **not** verified
for release, and scope these to the **release range** (below) — a feature outside the
range is not certified by this run even if its cell reads `Verified`.

**Re-check done-ness freshness** for each in-range feature — the verification report is
a point-in-time read, and code can be reverted or rebased between verify and release:

```
python3 "${CLAUDE_SKILL_DIR}/scripts/task-evidence.py" check specs/<id>/tasks.json --json
```

Invoke it by its `${CLAUDE_SKILL_DIR}` path (this skill bundles its own copy), never a
bare name. A feature with a `stale` task — its proving `commit_sha` is no longer in
HEAD's ancestry — is **release-blocking exactly like an unverified one**: the report it
trusts was cut against code this checkout no longer holds. Route a stale feature to
`/core-engineering:ce-implement` (re-derive the stale tasks), then `/core-engineering:ce-verify`, before certifying — do
not carry it into the range as `Verified` (Execution Contract rule 2).

Determine the **release range**. If `git tag` lists **no tags**, this is the
**initial release**: the range is the whole plan's shipped features, notated
`(initial)..<head>`. Otherwise the range is the features shipped since the last
release tag (`git tag` → newest; never call `git describe` without first confirming
a tag exists). Load the read-only inputs. Confirm the plan, range, and base with the
human  [material].

## Stage 1 — Version Decision  [material]

Propose a **semantic version**. For the **initial release** (no prior tag), default
to a human-set version-zero (e.g. `0.1.0` or `1.0.0`) — not a bump. Otherwise read
the last tag and propose a bump from the shipped features' nature:

- **major** — any feature is a breaking change (a removed / renamed public surface, an incompatible contract or schema change recorded in a spec / ADR);
- **minor** — any feature adds capability, none breaking;
- **patch** — only fixes / internal changes.

This is the **product / release version** — independent of the `plugin.json`
patch-bump the repo's pre-commit hook performs (a separate version authority; do not
conflate them). Present the proposal with its reasoning (which feature drove the
bump); the human confirms or overrides (`--version`). Semver inference is a
recommendation — see *Honest Limitations*.

## Stage 2 — Changelog

Derive a changelog for the range from the shipped features (ship order), grouped
**Added / Changed / Removed / Fixed**. Each entry: the user-facing change, traced to
its feature id (and spec). Pull known caveats from the verification report's Open
Issues and the accepted review findings into a **Known Issues** section — a release
changelog that hides them is dishonest. Evidence-bound: no entry without a shipped
feature behind it. This is the section Stage 5 appends to `CHANGELOG.md`.

## Stage 3 — Rollback-Readiness and Supply-Chain Evidence

Assemble the **rollback-readiness checklist** for the range — honestly:

- **Reversible?** For each destructive / irreversible change (schema / data
  migration, deletion, irreversible config), record its rollback path. If a spec
  recorded forward + rollback steps, cite them; if none exists, flag **"no recorded
  rollback — manual / unknown"** — never fake it.
- **Feature flags / kill-switches** present for risky features?
- **Data / config changes** that outlive a rollback (one-way)?
- **External effects** (third-party calls, published events) a rollback can't undo?

The output is a readiness table with `ready | manual | unknown` per item — the input
to the gate, not a guarantee the rollback was *tested* (see *Honest Limitations*).

Assemble **Supply-Chain Evidence** for the release range. Inventory the evidence
that exists and the evidence that is missing:

- **SBOM:** CycloneDX / SPDX files, package-lock-derived SBOMs, or org-standard
  SBOM artifacts. Record file paths, format, timestamp, and scope if knowable.
- **SLSA provenance:** build provenance or attestation files. Record producer,
  subject artifact, and digest if present.
- **Artifacts:** release artifact checksums and signatures. Record signer /
  key identity only if the artifact states it; otherwise say `unknown`.
- **OpenSSF Scorecard:** latest score/report path or CI URL if present.
- **CI security evidence:** secret-scan status, plugin validation, version-bump,
  and hardening-check status.

Absence is allowed only as an explicit release gap. Do not infer that the build is
SLSA-compliant, signed, or SBOM-covered from CI passing; those are separate facts.

## Stage 4 — Release-Readiness Gate  [material]

Run the **Release-Readiness Gate** (above). On **No-go**, name the blocker and route
(Escalation table). On **Go**, record the human's attestation.

## Stage 5 — Write the Decision and Hand Off

Write `docs/plans/<slug>/release/<date>-release.md` (the decision package).

**Compile the per-release evidence pack.** Alongside the decision artifact, compile
one dated, auditor-consumable evidence pack for the release — the same
`evidence-pack.py` `/core-engineering:ce-retro` exposes, bundled in this skill's own directory:

```
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence-pack.py" docs/plans/<slug> \
  --guard-log .claude/ce-guard-log.jsonl \
  --merge-verdict <release or CI gate_runner verdict, if one exists> \
  --out docs/plans/<slug>/evidence-pack/<date>
```

Invoke it by its `${CLAUDE_SKILL_DIR}` path (this skill bundles its own byte-identical
fork), never a bare name. Point `--merge-verdict` at the release's `gate_runner.py`
verdict when one exists (a **per-merge** pack comes free by pointing it at the CI
verdict instead); omit it when none does — the section is gap-listed, never faked.
The dated `evidence-pack/<date>/` directory is **never overwritten**, so the
release's evidence is frozen at cut time, and `--out` refuses a target that would
overwrite a source it reads. The pack is **evidence compilation, not a conformity
assessment** (see `docs/ENTERPRISE-HARDENING.md` § *Regulatory Mapping — EU AI Act*):
it does not change the go/no-go and renders no compliance verdict. Compiling it is
**best-effort** — a failure to compile is a release finding, never a block on the
decision.

**On explicit consent**, append the new version's section to the repo's `CHANGELOG.md`
(creating it if absent) — never rewriting prior sections — and write a release-notes
file; a local file write, never a commit, never a push. Then hand the **human** the
execution steps release does not perform:

```
git tag <version> -m "<release notes>"   # the human runs this
git push origin <version>                # the human pushes
# deploy via your pipeline               # release never deploys
```

**Metrics (best-effort, optional).** Append a `stage-complete` line (`stage: "release"`
— requires `release` in `retro`'s stage enum) plus a `gate` line
(`gate: pass|fail`) for the go/no-go. For each blocker the gate routes, append an
`escalation` line: an **enum** route (`/core-engineering:ce-spec`, `/core-engineering:ce-plan`) uses `escalation_type`; a
**lateral** route (`/core-engineering:ce-verify`, `/core-engineering:ce-review`) uses `escalation_type: null`
with `detail` prefixed `route:<cmd>` (e.g. `route:/core-engineering:ce-verify …`) so `/core-engineering:ce-retro` still
counts it. Derive from data already produced, label token figures estimates, and
**never** let metrics block the decision. Powers `/core-engineering:ce-retro`.

---

## Artifact Template — `release.md`

````markdown
# Release Decision: <slug> — <proposed-version>  (<date>)

> Generated by `/core-engineering:ce-ship-release`  ·  Gate: GO | NO-GO | pending
> Range: <initial> | <last-tag>..<head>  ·  Base: <base>

## Version
- Proposed: <version>  (initial, or bump major | minor | patch — driven by <feature>)
- Confirmed: <version | overridden by human>

## Changelog
### Added
- <change> — <feature id>
### Changed / Removed / Fixed
- …
### Known Issues
- <from verification Open Issues / accepted review findings>

## Rollback-Readiness
| Item | Reversible | Path / note |
|---|---|---|
| <schema migration X> | manual | no recorded rollback — manual |

## Supply-Chain Evidence
| Evidence | State | Path / note |
|---|---|---|
| SBOM | present | <CycloneDX/SPDX file> |
| SLSA provenance | missing | accepted gap? <yes/no> |
| Signatures / checksums | present | <artifact + digest/signature path> |
| OpenSSF Scorecard | missing | <note> |
| Secret scan / plugin validation | present | <CI run / local command> |

## Readiness Gate
- Verified: <N/N> · High-sev findings open: <0> · Rollback gaps accepted: <…> · Supply-chain gaps accepted: <…>
- Decision: GO | NO-GO — by human, <date>
- If NO-GO: blocker <…> → routed to <skill>

## Execution (the human's — not performed here)
- tag `<version>` · push · deploy
````

## Closing

```text
Release decision: <slug> — <version>  (GO | NO-GO)
Range:     <initial | last-tag..head>
Changelog: <N> entries · Known issues: <M>
Rollback:  <ready>/<manual>/<unknown>
Supply chain: SBOM <present|missing> · provenance <present|missing> · signatures/checksums <present|missing> · Scorecard <present|missing>
Package:   docs/plans/<slug>/release/<date>-release.md
Evidence pack: docs/plans/<slug>/evidence-pack/<date>/pack.json  (compilation, not a conformity assessment)
```

On **GO**, the human tags, pushes, and deploys — release never does. On **NO-GO**,
run the routed skill, then re-run release.
