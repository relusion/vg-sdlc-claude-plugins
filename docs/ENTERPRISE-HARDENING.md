# Enterprise Hardening

This document is the repository's control map for enterprise use of the
`core-engineering` SDLC automation framework. It names the controls that are
already structural in this repo, the evidence an adopter can inspect, and the
gaps that remain human-owned or organization-owned.

It is intentionally practical: the framework is not a compliance product and it
does not attest a regulated control environment. It provides repository-aware
workflow controls, deterministic gates, and audit artifacts that a team can fold
into its own SDLC, security, and release-management system.

Primary references used for vocabulary and alignment:

- OWASP LLM Top 10:
  https://owasp.org/www-project-top-10-for-large-language-model-applications/
- OWASP Agentic AI threats and mitigations:
  https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- SLSA:
  https://slsa.dev/
- OpenSSF Scorecard:
  https://scorecard.dev/
- CycloneDX SBOM:
  https://cyclonedx.org/capabilities/sbom/
- SPDX:
  https://spdx.dev/

## Control Map

| Risk area | Relevant external vocabulary | Framework control | Evidence in this repo | Residual owner |
|---|---|---|---|---|
| Prompt injection and malicious repository text | OWASP LLM Top 10: prompt injection; OWASP Agentic: malicious task/tool instructions | Read-only skills must cite repository facts and ignore instructions embedded in analyzed files. Adversarial evals cover malicious fixture docs that ask the model to override policy or exfiltrate data. | `evals/scenarios.json` (`EVAL-011`, `EVAL-012`), `evals/fixtures/adversarial-instructions/`, `/ce-ask`, `/ce-impact` citation contracts | Skill author and reviewer |
| Excessive agency | OWASP LLM Top 10: excessive agency; OWASP Agentic: tool misuse and unsafe delegation | Skills separate decision, implementation, verification, review, and release. Release never deploys; plugin agents are leaf agents without nested `Task`. The write-scope guard enforces session leases for read-only skills over a `/ce-init`-seeded deny-only baseline; git-guard tiers are env-hardenable to deny and fail closed on malformed Bash payloads. | `plugins/core-engineering/skills/ce-ship-release/SKILL.md`, `scripts/check.py` agent leaf check, `plugins/core-engineering/hooks/git-guard.py`, `plugins/core-engineering/hooks/write-scope-guard.py` | Human release owner |
| Sensitive information disclosure | OWASP LLM Top 10: sensitive information disclosure | `env-guard` blocks high-risk dotenv and `/proc/.../environ` reads on the Claude Code surface (read side); `net-guard` is the send side — over a `/ce-init`-seeded egress allowlist it confirms non-allowlisted outbound calls and hard-denies a guarded-secret upload payload; the merge bar's `secrets-guard` advisory gate scans the credentials a change ADDS (base..head, values redacted) and renders a machine verdict on any CI substrate — the first-party producer of the release package's secret-scan evidence row; CI additionally runs gitleaks with redaction and full history; security probes redact secrets in outputs. | `plugins/core-engineering/hooks/env-guard.py`, `plugins/core-engineering/hooks/net-guard.py`, `plugins/core-engineering/skills/ce-probe-infra/scripts/secrets-guard.py`, `.github/workflows/secret-scan.yml`, `/ce-probe-infra` and `/ce-probe-sec` docs | Repository owner; secrets manager owner |
| Supply-chain dependency drift | OWASP LLM Top 10: supply-chain risk | `dep-guard.py` detects undeclared or typo-suspicious dependencies in implementation flows; byte-identical copies are enforced across callers from the machine-readable fork registry (`fork_sync.py --write` re-syncs). | `plugins/core-engineering/fork-manifest.json`, `ce-implement/scripts/dep-guard.py`, `ce-auto-build/scripts/dep-guard.py`, `ce-verify/scripts/dep-guard.py`, `scripts/check.py`, `scripts/fork_sync.py`, `scripts/supply_chain_check.py` | Implementer and reviewer |
| CI and tool supply chain | SLSA, OpenSSF Scorecard | GitHub Actions references are pinned to commit SHAs; downloaded gitleaks tarball is checksum-verified; strict plugin validation and offline gates run in CI. | `.github/workflows/*.yml`, `scripts/supply_chain_check.py`, `scripts/portability_check.py` | Maintainer updating CI actions |
| SBOM and provenance evidence | SLSA provenance; CycloneDX/SPDX SBOM | The release skill inventories SBOM, provenance, signature, checksum, and OpenSSF Scorecard evidence and makes absence a release finding. `scripts/enterprise_evidence.py` can inventory local evidence and optionally run installed local SBOM/vulnerability generators. It does not fabricate attestations. | `ce-ship-release/SKILL.md`, `scripts/enterprise_evidence.py` | Build/release engineering |
| Tool and plugin integrity | OWASP Agentic: unsafe plugin/tool design | Strict manifest validation, corpus lint, model-policy validation, known slash surface, and no stale aliases. | `scripts/check.py`, `scripts/corpus_lint.py`, `.github/workflows/plugin-validate.yml`, `plugins/core-engineering/model-policy.json` | Plugin maintainer |
| In-session subversion of a guard hook | OWASP Agentic: unsafe tool/plugin design; supply-chain (self-modifying tooling) | The PreToolUse guards cannot detect their own subversion — an in-session `sed -i` on `env-guard.py` disarms it silently. `hooks/hook-integrity.py` runs at **SessionStart**, recomputes the sha256 of every `hooks/*.py` + `hooks.json`, and warns loudly (never blocks) on any drift from the shipped `integrity-manifest.json`. `scripts/hook_manifest.py --check`, run by `scripts/check.py` §5d, makes a hook edit that skipped a manifest refresh CI-red. Tamper-*evidence*, not tamper-proofing: an agent with Bash can rewrite the manifest too, but the *committed* manifest is CI-verified, so any drift is auditable in the reviewable diff (the same claim class as the merge bar's `sha256sum -c` step). | `plugins/core-engineering/hooks/hook-integrity.py`, `plugins/core-engineering/hooks/integrity-manifest.json`, `scripts/hook_manifest.py`, `scripts/check.py`, `tests/test_hook_manifest.py` | Plugin maintainer refreshing the manifest on an intentional hook change |
| AI-authored changes merging on green checks alone | Segregation of duties; SLSA source/build platform controls; OWASP Agentic: unsafe delegation | `merge-policy.json` encodes a two-conjunct merge bar (machine integrity gates AND a human/two-human validity attestation, with no `none` value); `scripts/gate_runner.py` executes the integrity conjunct as one machine verdict per PR; adopters install the composite action `action/merge-bar` pinned at a full 40-hex commit SHA (the preferred path — the action refuses a movable ref at run time, and the one pin fetches runner, policy, and gate scripts atomically) or copy in `templates/adopter-ci/gates.yml` (the documented air-gapped fallback), which refuses a non-SHA `TOOLKIT_REF`, fetches the toolkit at that pinned commit, and verifies all five decision-making files (runner, policy, spec-lint, test-guard, dep-guard) via `sha256sum -c` before running; both surfaces read any policy override from the base ref only, while they union the declared-deps list from base and head, so a same-PR declaration remains governed by the unchanged base policy and its review escalation; every verdict records the policy path + sha256 and the resolved base/head commit SHAs. The bar proves integrity, not function — it never builds the project or runs its test suite (see "What the merge bar does not prove" below). | `plugins/core-engineering/merge-policy.json`, `scripts/gate_runner.py`, `templates/adopter-ci/gates.yml`, `merge-verdict.json` in CI logs, `tests/test_gate_runner.py` | Adopter branch-protection config (required status check + required review count), a CODEOWNERS/ruleset review requirement on `.github/**`, and the adopter's own build/test job kept as a second required check |
| Tampering with the merge check itself (the workflow that grades the PR) | SLSA provenance (workflow-signed attestation); EU AI Act Art 12 (record-keeping / automatic event logging); OWASP Agentic: unsafe delegation | On `pull_request` the calling workflow runs from the PR merge ref, so a green `merge-bar` status is only as trustworthy as the workflow file a PR can edit. The opt-in `attest: 'true'` input adds the **detection** control CODEOWNERS prevention cannot: after a green verdict, `scripts/verdict_predicate.py` projects the verdict to a whitelisted predicate (recorded `base_sha`/`head_sha`, policy sha256, status, change class, per-gate disposition — nothing model-derived, no filesystem path) and GitHub's keyless OIDC attestation (`actions/attest`, SHA-pinned) sigstore-signs it under the workflow's OIDC identity — **no stored secret, no signing key** — producing a transparency-logged event record binding repo + workflow path + trigger SHA. A second required check runs `gh attestation verify` plus a `jq` assert that the signed predicate's base/head equal the PR's real merge-base/head, so a green bar is provable to have judged *these* commits under *this* policy hash independently of the workflow. Default OFF preserves the 3-line adoption and GHES/air-gapped compatibility (`contents: read` only); the air-gapped `gates.yml` has no attestation path — stated honestly, not implied as parity. | `action/merge-bar/action.yml` (`attest` input, pinned `actions/attest` uses), `scripts/verdict_predicate.py`, `tests/test_verdict_predicate.py`, the attestation in GitHub's public transparency log, `.github/workflows/action-selftest.yml` (attest self-test — verifies a real verdict and proves a byte-tampered copy fails) | Adopter branch-protection config (the second `gh attestation verify` required check) and GitHub-hosted-runner OIDC availability |
| Stale published pin checksums | SLSA provenance (release integrity) | Every `v*` tag push triggers `.github/workflows/release-pin-block.yml`, which regenerates the adopter pin block from committed state at the tagged commit (`scripts/print-pin-block.sh` hashes `git show` blobs, so working-tree dirt can never leak into a published pin) and publishes it into the GitHub Release notes — created if the tag has no Release, notes replaced if one exists — so published checksums are generated, never hand-typed; `--verify-tag` refuses to create a Release for a tag the remote does not have, and `scripts/supply_chain_check.py` holds needles on the workflow so the release chain cannot be silently deregistered. | `.github/workflows/release-pin-block.yml`, `scripts/print-pin-block.sh`, `tests/test_print_pin_block.py`, `scripts/supply_chain_check.py` | Human release owner reviewing the release commit and managing any tag-signature policy |
| Auditability and traceability | Enterprise SDLC governance | Plans/specs/reviews/verifications/release decisions are durable markdown/JSON under `docs/`; metrics are append-only; retro exports evidence rather than attestation. `scripts/metrics_report.py` projects repo-level metrics and gaps for dashboards. | `docs/HOW-IT-WORKS.md`, skill artifact templates, `/ce-retro` audit export, `scripts/metrics_report.py` | Project owner |
| Post-merge artifact drift on `main` (continuous monitoring) | EU AI Act Art 72 (post-market monitoring); SLSA source integrity over the branch's life | The merge bar judges a PR *before* it lands; nothing re-judges `main` *after* merge, so a retired surface, a broken traceability link, or a silently-disarmed security gate can rot unseen. `scripts/drift_scan.py` re-projects the committed `HEAD` against every registered plan directory and reports drift in the **same unified Scope Lock vocabulary** the skills use (plan-layer scope → `/ce-plan`, spec-layer scope → `/ce-spec`), with a `0/1/2` exit contract and `--advisory-only` first-run rollout. Adopters install the scheduled + post-merge workflow `templates/adopter-ci/drift.yml`, which pins the toolkit at a 40-hex commit SHA and checksum-verifies the scanner plus the two lints it uses as its integrity oracle before running. Integrity, not function — it re-judges committed artifacts, never builds or runs the suite. | `scripts/drift_scan.py`, `templates/adopter-ci/drift.yml`, `drift-verdict.json` in CI logs, `tests/test_drift_scan.py`, `scripts/supply_chain_check.py` | Adopter CI owner (schedule + failure/issue notification wiring) |

## Enforcement Surfaces

These controls are deterministic and CI-checkable:

- `scripts/check.py` validates manifests, frontmatter, byte-identical gate copies,
  model policy, README catalog drift, corpus hygiene,
  and now enterprise hardening drift through `scripts/supply_chain_check.py`.
- `scripts/supply_chain_check.py` validates pinned GitHub Actions, checksum
  verified secret scanning, supply-chain release/delivery prompts, adversarial
  eval fixtures, dependency-gate copies, optional evidence/reporting utilities,
  and this control map.
- `scripts/gate_runner.py` executes a change class's required integrity gates
  from `plugins/core-engineering/merge-policy.json` against any repository and
  emits one machine verdict (exit 0 only when every required gate passes;
  gate errors and timeouts fail closed). `scripts/check.py` section 14 lints
  the policy structurally, and `scripts/supply_chain_check.py` keeps the
  policy, the runner, the composite-action delivery surface
  (`action/merge-bar/` — the preferred adoption path, pinned by one 40-hex
  commit SHA and proven continuously by
  `.github/workflows/action-selftest.yml`), and the SHA-verified air-gapped
  fallback template (`templates/adopter-ci/gates.yml`) from being silently
  unshipped.
- `scripts/drift_scan.py` is the **post-merge complement** to the merge bar: it
  re-projects a repo's committed `HEAD` against every registered plan directory
  and reports drift in lock vocabulary (`0/1/2` exit contract). Adopters run it
  on `main` via the scheduled + post-merge template `templates/adopter-ci/drift.yml`,
  which `scripts/supply_chain_check.py` keeps SHA-pinned, checksum-covering its
  decision files (the scanner + `plan-lint.py` + `spec-lint.py`), and unremovable.
- `scripts/portability_check.py` proves shipped hook/gate scripts are stdlib-only
  and run without Claude Code.
- `scripts/eval_check.py` validates behavior-eval scenarios, fixtures, and golden
  gates; adversarial prompt-injection scenarios are part of the smoke profile.
- `scripts/metrics_report.py` compiles a repo-level dashboard input from plan
  metrics, reviews, verification artifacts, auto-build reports, and eval run
  metadata without re-judging markdown content.
- `scripts/enterprise_evidence.py` inventories SBOM, provenance, signature,
  checksum, Scorecard, and scan evidence; with `--execute`, it can run installed
  local `syft` and `osv-scanner` generators.
- `.github/workflows/plugin-validate.yml` runs the offline gates, eval smoke dry
  run, unit tests, and strict Claude plugin validation.
- `.github/workflows/secret-scan.yml` runs gitleaks over full git history with
  redaction and checksum-verifies the downloaded binary archive.
- `.github/workflows/version-bump.yml` enforces plugin version bump discipline on
  PRs.
- `.github/workflows/release-pin-block.yml` regenerates the gates.yml adopter
  pin block at every `v*` tag push (`scripts/print-pin-block.sh` at the tagged
  commit) and publishes it into the GitHub Release notes — create-or-update,
  `--verify-tag` — so a published pin block can never be stale.

These controls are workflow contracts enforced by skill design and review:

- `/ce-ship-release` records SBOM, SLSA provenance, signatures, checksums, and
  OpenSSF Scorecard evidence as readiness inputs. Missing evidence becomes a
  finding at the Release-Readiness Gate.
- `/ce-ask` and `/ce-impact` are read-only, citation-bound, and tested against
  malicious repository instructions.
- `write-scope-guard.py` enforces a repo/session write lease when
  `.claude/ce-write-scope.json` is present: read-only-on-code skills set a
  lease at Stage 0 and clear it at exit, over the deny-only baseline
  `/ce-init` seeds (`.git/**` and the lease file itself are never
  agent-writable). It is shell-aware: its `Bash` matcher reuses `git-guard`'s
  tokenizer to screen recognized literal write vectors (redirections, `tee`,
  `sed -i`, `cp`/`mv`, `rm`, `dd of=`, `install`, `ln`, and literal-operand
  `xargs`) through the same policy, while out-of-workspace scratch remains
  permissive and recognized Bash mutation of the lease file is hard-denied.
  Lease-mode policies carry a `lease_id` and `created_at` and bind to the host
  session on first use. A lease orphaned by a different session, or past the
  TTL with no live owner, self-heals with one logged `ask` and replacement by
  the deny-only baseline; a live owner is never degraded, and ambiguous state
  fails safe to normal enforcement. Denies and stale-lease replacements log to
  the shared tamper-evident guard ledger (below). Without a policy file the
  guard is intentionally inert, and interpreter writes, variable-indirected
  targets, and other documented tokenizer gaps remain outside this cooperative
  backstop.
- `net-guard.py` is the **egress checkpoint** — the send-side complement to
  `env-guard`'s read-side confinement, closing the exfil half the review noted was
  guarded on read but not on send. When `.claude/ce-net-policy.json` is present
  (seeded by `/ce-init`), it screens outbound network on `Bash`/`WebFetch`/
  `WebSearch` against a host allowlist: a non-allowlisted host or an upload flag
  to one is `ask` (upload escalatable to deny via `CE_NET_GUARD_UPLOAD`), and a
  guarded-secret upload payload or a credential-store read co-occurring with a
  network verb is a hard `deny`. It reuses `env-guard`'s guarded-secrets corpus
  and `git-guard`'s tokenizer by path, is inert without a policy, and documents
  DNS-tunnel / interpreter-socket / MCP egress as out of scope — a checkpoint, not
  a network sandbox.
- `hook-integrity.py` is the **hook self-integrity** control: the PreToolUse guards
  cannot detect their own subversion, so this SessionStart hook recomputes the
  sha256 of every `hooks/*.py` + `hooks.json` and warns loudly (never blocks) on
  any drift from the shipped `integrity-manifest.json`. The commit-time half,
  `scripts/hook_manifest.py --check` (run by `scripts/check.py` §5d), makes a hook
  edit without a manifest refresh CI-red. Tamper-evidence, not tamper-proofing:
  an agent with Bash can rewrite the manifest, but the committed manifest is
  CI-verified so any drift is auditable in the diff — the merge bar's checksum
  claim class, not a guarantee a guard cannot be edited.
- The **guard ledger** `.claude/ce-guard-log.jsonl` is a tamper-evident evidence
  artifact: all four PreToolUse guards (`git-guard`, `env-guard`,
  `write-scope-guard`, `net-guard`) route every ask/deny through one shared writer
  (`hooks/guard_log.py`) that records the session id, actor (tool + hook event),
  a `payload_sha256` binding the decision to the exact tool call, and a sha256
  hash chain over the prior line. `python3 hooks/guard_log.py --verify
  <file>` re-derives the chain (exit 0 valid / 1 broken / 2 could-not-run),
  making an after-the-fact edit, deletion, or reorder of a logged decision
  detectable. Honest bound: pure tail-truncation is only detectable against an
  externally recorded chain head, and writes are best-effort (a logging failure
  never changes a permission decision).
- `/ce-probe-sec` requires twice-attested consent before dynamic security probing.
- `/ce-probe-infra` is static, redacts secrets, and routes dynamic confirmation to
  the human or the appropriate probe.

## Evidence and Attestation

Enterprise adopters should treat these as evidence artifacts, not as blanket
attestations:

- Validation output from:

  ```bash
  python3 scripts/check.py --no-install-hooks
  python3 scripts/supply_chain_check.py
  python3 scripts/eval_check.py
  python3 scripts/eval_run.py --profile smoke --out-dir /tmp/vg-eval-smoke-dry-run
  python3 scripts/eval_run.py --profile benchmark --out-dir /tmp/vg-eval-benchmark-dry-run
  python3 scripts/metrics_report.py --json
  python3 scripts/enterprise_evidence.py --json
  python3 scripts/portability_check.py
  python3 -m unittest discover -s tests -v
  ```

- Release decision packages under `docs/plans/<slug>/release/`.
- Delivery manifests under `docs/plans/<slug>/delivery/`.
- Security, infra, UX, performance, review, verification, and retro artifacts under
  the generated plan/review/probe directories documented in `docs/HOW-IT-WORKS.md`.
- CI logs for pinned actions, secret scanning, plugin validation, and version-bump
  enforcement.
- The hash-chained guard ledger `.claude/ce-guard-log.jsonl`, verified with
  `python3 plugins/core-engineering/hooks/guard_log.py --verify <file>`.

When an external governance process needs a formal attestation, a human control
owner must sign it. The framework can compile evidence; it does not sign for the
organization.

## Regulatory Mapping — EU AI Act

The EU AI Act obliges providers and deployers of high-risk AI systems to keep
records, maintain technical documentation, and retain both. This framework does
**not** determine whether a system is high-risk, and it renders **no conformity
assessment** — that is a legal and organizational judgment a notified body or the
provider's own compliance function owns. What it does is **compile, hash, and
retain** the SDLC evidence those record-keeping and documentation obligations draw
on, so a human control owner has a dated, tamper-evident bundle to reason over. The
mapping below is a vocabulary bridge, not a compliance claim.

The evidence-pack bundle (`plugins/core-engineering/skills/ce-retro/scripts/evidence-pack.py`,
byte-identical fork bundled in `ce-ship-release`) — compiled by `/ce-retro`'s export
mode and by `/ce-ship-release` per release, written under the dated, never-overwritten
`docs/plans/<slug>/evidence-pack/<date>/` convention — carries the artifacts each row
cites. Every section is populated or gap-listed; an absent source is recorded in
`gaps[]`, never silently zeroed.

| Regulatory vocabulary | Pack section / framework control | Evidence artifact in this repo |
|---|---|---|
| **EU AI Act Art 12 — record-keeping / automatic logging** of events over the system's lifetime | The hash-chained guard log (all four decision-making PreToolUse guards through `guard_log.py`), the append-only `.metrics.jsonl` event stream, and the pack's compiled `event_log` + `guard_decisions` sections (with the `guard_log.py --verify` result and out-of-band chain head) | `.claude/ce-guard-log.jsonl` (verified via `guard_log.py --verify`), `docs/plans/<slug>/.metrics.jsonl`, `docs/plans/<slug>/evidence-pack/<date>/pack.json` |
| **EU AI Act Art 11 / Annex IV — technical documentation** of the system and its development | The plan / spec / verification / review artifacts the pack compiles verbatim with their sha256 — the `human_attestations`, `dismissal_records`, and `model_identity` sections plus the copied `artifacts/` tree | `docs/plans/<slug>/` (`plan.json`, `specs/`, `verification-report.md`, `code-review.md`), the pack's verbatim `artifacts/` copies |
| **EU AI Act Art 9 — risk management** (residual risk knowingly accepted) · **ISO 27001 risk acceptance** | The pack's `finding_dispositions` section: the merge bar's accepted-risk register. An advisory gate (`secrets-guard`, `sca-guard`) *suppresses* a finding a named human accepted with a reason and a dated expiry, instead of re-alarming on every PR — and the pack renders every entry, **split active vs expired**, so a suppression is never invisible to whoever reads it. An **expired** entry suppresses nothing (its finding re-alarms), is listed in the pack, and fails `disposition-lint` in CI: a disposition defers, it never forgets. An **absent** ledger means nothing was accepted (`present: false`, not a gap); an **unreadable** one is a gap, because the pack must not confuse "nothing accepted" with "the register is broken". Reported as found and never re-judged — the pack does not verify that the named `accepted_by` approved the entry | `.merge-bar/dispositions.json`, `plugins/core-engineering/skills/ce-probe-infra/scripts/disposition-lint.py` (CI lint), `docs/plans/<slug>/evidence-pack/<date>/pack.json` (`sections.finding_dispositions` + the verbatim sha256-stamped ledger copy) |
| **EU AI Act Art 18 — retention** of documentation for the required period | The dated, never-overwritten `evidence-pack/<date>/` convention — one immutable pack per day per plan, frozen at cut time; the pack refuses an `--out` that would overwrite a source it reads | `docs/plans/<slug>/evidence-pack/<date>/` (retention duration is the adopter's storage policy; the framework produces the immutable dated bundles to retain) |
| **SLSA provenance** — build/source integrity of the change under judgment | The `gate_runner.py` merge verdict the pack binds in its `gate_verdicts` section: recorded policy sha256, pinned base/head commit SHAs, and change class | `merge-verdict.json` (recorded in CI logs; bound via `--merge-verdict`), `docs/plans/<slug>/evidence-pack/<date>/pack.json` |
| **EU AI Act Art 12 — event record** of an automated merge decision + **SLSA provenance** (workflow-signed attestation) | The opt-in *signed verdict*: with `merge-bar`'s `attest: 'true'`, `actions/attest` sigstore-signs the whitelisted verdict predicate under the workflow's OIDC identity — a keyless, transparency-logged, independently-verifiable record of which commits a green bar judged under which policy hash, tamper-evident even when the workflow file itself is not. Unsigned by default (GHES/air-gapped has no OIDC); a monitoring/gate signal a human wires as a second required `gh attestation verify` check, not a pack section. | `action/merge-bar/action.yml` (`attest` input), `scripts/verdict_predicate.py`, the attestation in GitHub's public transparency log |
| **SLSA provenance** — workflow-signed attestation of eval evidence | Not implemented. A future CI-attested eval `summary.json` could carry a resolvable `ci_run_url` plus a build-provenance attestation digest referenced by the pack. | *(current gap — this document does not cite a control that does not exist; see Gaps and Roadmap)* |
| **EU AI Act Art 72 — post-market monitoring** of the system after it is in use | `scripts/drift_scan.py` re-judges `main` on a schedule and after every merge, re-projecting committed `HEAD` against every registered plan directory and emitting a dated machine verdict in lock vocabulary — the ongoing monitoring surface that catches a retired surface, a broken traceability link, or a disarmed security-coverage gate the pre-merge bar can no longer see. Adopters run it via `templates/adopter-ci/drift.yml`. This is a monitoring signal, not a pack section: the verdict lives in CI, and a human routes each finding to its owning skill. | `scripts/drift_scan.py`, `templates/adopter-ci/drift.yml`, `drift-verdict.json` (recorded in CI logs) |

**What the pack is NOT.** It is **evidence compilation, not attestation and not a
conformity assessment**: it gathers and hashes what the pipeline recorded and
renders no compliance or conformity judgment (its own `honest_limitations` field
says so machine-readably). It is **tamper-evident, not tamper-proof** — the guard
log's hash chain detects any edit, deletion, or reorder except wholesale
tail-truncation against a prior recorded chain head. Model identity is best-effort:
a hook-less run records `model=null`, never a guessed tier. A
populated pack proves which artifacts exist and what was recorded; it does not prove
the system is compliant, safe, or fit for a regulated deployment — a human control
owner reads it and signs, or does not.

## Gaps and Roadmap

Current gaps are explicit:

- The framework records SBOM, SLSA provenance, signatures, checksums, and OpenSSF
  Scorecard presence. The optional evidence helper can generate local SBOM and
  vulnerability-scan artifacts only when `syft` or `osv-scanner` is installed;
  it does not issue provenance, sign artifacts, or run Scorecard automatically.
- There is no SLSA-compliant build pipeline in this repository. Adopters must
  wire their own builder, provenance issuer, artifact registry, and signer.
- `env-guard` protects high-risk local read vectors on the Claude Code surface,
  but it is not a complete DLP system and does not cover every execution surface.
- `net-guard` is an egress **checkpoint**, not a network sandbox: it screens the
  common `curl`/`wget`/`WebFetch` egress and upload vectors but does not cover DNS
  tunneling, interpreter/shell sockets, MCP-mediated egress, `$VAR` host
  indirection, or execution surfaces that do not load plugin hooks. Its
  guarded-secret upload deny is a co-occurrence signal, so a public `.pem`/`.key`
  can be a false deny.
- Adversarial evals are a floor, not a red-team program. Add fixtures when a real
  failure mode is found.
- Pinned GitHub Actions improve reviewability but require an intentional update
  process for upstream action security fixes.
- What the merge bar does not prove — integrity, not function: a green
  `scripts/gate_runner.py` verdict proves traceability held, tests were not
  weakened, and no undeclared dependency entered a manifest. It never proves
  test sufficiency (a weak-but-unweakened suite passes), never proves a
  dependency exists on a registry (dep-guard's offline half only), never
  builds the project, and never runs its test suite. An adopter that wires
  `merge-bar` as its only required status check can merge code that does not
  compile behind a green bar — the adopter's own build/test job must remain a
  second required check.
- The merge bar's validity conjunct (human / two-human) is declared by
  `merge-policy.json` and reported in every `gate_runner.py` verdict, but it is
  enforced only by the host platform's required-review configuration — the
  runner cannot verify that a human actually approved. An adopter who skips
  the branch-protection mapping silently degrades the bar to integrity-only.
- On `pull_request` the adopter's `gates.yml` workflow itself executes from the
  PR merge ref, so the PR under judgment can edit the workflow that gates it.
  The policy override is read from the base ref only; `declared-deps.txt` is
  instead the union of base and head so a same-PR declaration can proceed under
  the base policy's review escalation. Neither input rule protects the calling
  workflow file: only a CODEOWNERS or repository-ruleset review requirement on
  `.github/**` (docs/TEAM-ROLLOUT.md, "Wire it to branch protection" step 6)
  does that. The toolkit cannot enforce this host-side configuration; an
  adopter who skips it leaves the bar rewritable by the PRs it gates.

Default next improvements:

1. Add an optional Scorecard CI workflow with pinned actions and reviewed
   permissions.
2. Add sample CycloneDX and SPDX SBOM paths to release/delivery fixture repos.
3. Add provenance/signature fixture checks to full-profile release evals once a
   release eval exists.
4. Extend `scripts/supply_chain_check.py` with organization-specific policy
   hooks only after the current portable floor stays stable.
