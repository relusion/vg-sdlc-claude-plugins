---
name: ce-probe-deps
description: |
  Statically scan a repository's pinned dependency manifests against the OSV.dev advisory database — known-vulnerable versions (CVE/GHSA advisories) per exactly-pinned package, with loud offline degradation, never a silent pass. Deterministic stdlib floor (sca-guard.py over requirements.txt / npm lockfiles) enriched by model triage; only package name+version coordinates ever leave the machine (disclosed; --offline honored). Read-only on code; findings, not verdicts.
  Triggers: scan/audit/check dependencies for known CVEs or vulnerable versions, SCA, software composition analysis. For manifest *misconfiguration* (IaC/k8s/Dockerfile) use /ce-probe-infra; undeclared/typosquat NEW dependencies in a change are dep-guard's job inside the implement lane.
argument-hint: "[path (default: repo root)] [--offline]"
allowed-tools: Read, Write, Glob, Grep, Bash, AskUserQuestion, Skill
---

# Probe Deps

**Invocation input:** scan scope and flags: $ARGUMENTS

Statically audit the repository's dependency pins for **known vulnerabilities**:
every exactly-pinned package the deterministic floor can parse is checked
against the OSV.dev advisory database, and each hit is triaged into an
evidence-bound finding. This is the SCA probe — the standard automated
security control a serious team expects to exist.

It complements, never duplicates, the neighbors: `/ce-probe-infra` audits
manifest *misconfiguration*; `dep-guard.py` (inside the implement lane) gates
*new undeclared* dependencies entering a change. This probe asks a third
question: **are the versions already pinned here publicly known-bad?**

## Runtime Inputs

- **Scope path** (optional): subtree to scan; default repo root.
- **`--offline`** (optional): never touch the network — the floor degrades
  loudly and the report is explicitly labeled not-scanned.
- **Repository manifests:** `requirements*.txt`, `requirements/*.txt`,
  `package-lock.json`, `package.json` (exact pins only).

## Execution Contract

0. **Session write lease (structural, first act).** `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --set --skill ce-probe-deps --allow 'docs/dep-audits/**'` — only the dated report + evidence are writable, and the write guard now enforces that. Last act: `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --restore-baseline`. A denied write mid-session means this contract and the action disagree — reconcile; never edit or delete the lease to proceed.
1. **Static and read-only.** Never edits a manifest, never upgrades a package, never installs anything. Routes fixes; does not apply them.
2. **Deterministic floor always runs.** `sca-guard.py` (stdlib-only) parses the pins and queries OSV; the model *enriches* its output — usage context, blast radius, upgrade routing — and never replaces or re-derives it. A floor failure is reported as a degradation, never papered over.
3. **Network disclosure, up front.** The only data that leaves the machine is package coordinates (ecosystem + name + version) sent to OSV.dev — state this in the opening output. `--offline` is honored absolutely; offline or any network failure degrades **loudly** (exit 2): a not-scanned package is never reported as clean.
4. **Grounded & evidence-bound.** Every finding cites the manifest `file:line` of the pin plus the OSV advisory id(s). No advisory id → no finding.

## Cross-cutting rule — Findings, Not Verdicts

The probe reports advisories and their local context; the human triages every
finding (fix now via the routed lane / accept with reason / defer). It never
declares the dependency tree "safe" — OSV coverage is a floor, not an
absence proof.

## Workflow

### Stage 1 — Scope & floor

Set the write lease (contract item 0). Print the network disclosure line.
Then run the floor:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/sca-guard.py" --repo <scope> --json
```

Honor `--offline` by passing it through. Exit meanings: `0` clean scan,
`1` findings, `2` **degraded — could not scan** (offline/network/parse
failure). On `2`, the run continues but every downstream statement carries
the degradation label; there is no silent pass.

### Stage 2 — Enrich each finding

For every finding: locate the pin (`grep -n` the manifest → `file:line`),
check whether the package is actually imported/used in the code (a pinned
but unused dependency is still a finding, labeled `unused?`), and note the
advisory ids verbatim. Do not fetch or paraphrase full advisory content —
cite ids; the human follows them.

### Stage 3 — Report

Write `docs/dep-audits/<date>-<slug>.md`:

- **Disclosure & scope:** what was scanned, what left the machine, degradations.
- **Findings table:** package == version · manifest `file:line` · advisory ids · usage note.
- **Skipped (unpinned):** every range-specified dependency the floor could not
  check, listed — an unchecked dependency is visible, never implied clean.
- **Routing per finding:** version bump that stays API-compatible → `/ce-patch`
  (one bounded change); a breaking upgrade or cascade → `/ce-plan`; unclear
  exploitability in this codebase → note for `/ce-probe-sec` if a live target
  exists.

Restore the lease baseline (contract item 0, last act).

## Escalation

- A finding's fix is a **single bounded version bump** → route to `/ce-patch`.
- The upgrade **breaks APIs or cascades** across the tree → route to `/ce-plan`.
- The floor exits `2` and the human needs a clean verdict → re-run with
  network, or record the degradation as an accepted gap — never report clean.
- Manifest formats outside the parsed set (poetry.lock, go.sum, *.csproj…)
  detected → say so explicitly and record them as unscanned surfaces.

## Honest Limitations

- **Exact pins only.** Range specifiers (`^`, `~`, `>=`…) are skipped and
  listed, not resolved — resolving ranges requires the ecosystem's resolver.
- **Ecosystem scope (v1):** PyPI (`requirements*.txt`) and npm
  (`package-lock.json` v1–v3, `package.json` exact pins). Other ecosystems
  are reported as unscanned, never silently ignored.
- **OSV is the source of truth and its coverage is a floor** — an empty
  result means "no known advisory in OSV", not "safe".
- **No exploitability analysis.** A hit means the version is advisory-listed;
  whether this codebase's usage is exploitable is `/ce-probe-sec`'s question.
- **No license audit, no SBOM generation** — evidence presence for those
  lives in the ship lane.

## Closing

End with:

- `Scanned:` package count, ecosystems, scope path.
- `Findings:` count with advisory ids (or `none`).
- `Skipped:` unpinned/unscanned surfaces count.
- `Degradations:` offline/network/parse gaps (or `none`).
- `Next:` the routed fix lane per finding, or `no action`.
