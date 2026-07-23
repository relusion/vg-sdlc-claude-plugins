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
| Prompt injection and malicious repository text | OWASP LLM Top 10: prompt injection; OWASP Agentic: malicious task/tool instructions | Read-only skills must cite repository facts and ignore instructions embedded in analyzed files. Adversarial evals cover malicious fixture docs that ask the model to override policy or exfiltrate data. | `evals/scenarios.json` (`EVAL-011`, `EVAL-012`), `evals/fixtures/adversarial-instructions/`, `/core-engineering:ce-ask`, `/core-engineering:ce-impact` citation contracts | Skill author and reviewer |
| Excessive agency | OWASP LLM Top 10: excessive agency; OWASP Agentic: tool misuse and unsafe delegation | Skills separate planning, implementation, independent verification/review, verified documentation, conditional reader audit, and the final release decision. Only actual human decisions gate progress; deterministic PASS and clean read-only results do not request authority. Release never deploys; plugin agents are leaf agents without nested `Task`. The write-scope guard enforces session leases for read-only skills over a `/core-engineering:ce-init`-seeded deny-only baseline; git-guard tiers are env-hardenable to deny and fail closed on malformed Bash payloads. | `plugins/core-engineering/skills/ce-ship-release/SKILL.md`, `scripts/check.py` agent leaf check, `plugins/core-engineering/hooks/git-guard.py`, `plugins/core-engineering/hooks/write-scope-guard.py` | Human release owner |
| Sensitive information disclosure | OWASP LLM Top 10: sensitive information disclosure | `env-guard` blocks high-risk dotenv and `/proc/.../environ` reads on the Claude Code surface (read side); `net-guard` is the send side — over a `/core-engineering:ce-init`-seeded egress allowlist it confirms non-allowlisted outbound calls and hard-denies a guarded-secret upload payload; the merge bar's `secrets-guard` advisory gate scans the credentials a change ADDS (base..head, values redacted) and renders a machine verdict on any CI substrate — the first-party producer of the release package's secret-scan evidence row; CI additionally runs gitleaks with redaction and full history; security probes redact secrets in outputs. | `plugins/core-engineering/hooks/env-guard.py`, `plugins/core-engineering/hooks/net-guard.py`, `plugins/core-engineering/skills/ce-probe-infra/scripts/secrets-guard.py`, `.github/workflows/secret-scan.yml`, `/core-engineering:ce-probe-infra` and `/core-engineering:ce-probe-sec` docs | Repository owner; secrets manager owner |
| Supply-chain dependency drift | OWASP LLM Top 10: supply-chain risk | `dep-guard.py` detects undeclared or typo-suspicious dependencies in implementation flows; byte-identical copies are enforced across callers from the machine-readable fork registry (`fork_sync.py --write` re-syncs). | `plugins/core-engineering/fork-manifest.json`, `ce-implement/scripts/dep-guard.py`, `ce-auto-build/scripts/dep-guard.py`, `ce-verify/scripts/dep-guard.py`, `scripts/check.py`, `scripts/fork_sync.py`, `scripts/supply_chain_check.py` | Implementer and reviewer |
| CI and tool supply chain | SLSA, OpenSSF Scorecard | GitHub Actions references are pinned to commit SHAs; downloaded gitleaks tarball is checksum-verified; strict plugin validation and offline gates run in CI. | `.github/workflows/*.yml`, `scripts/supply_chain_check.py`, `scripts/portability_check.py` | Maintainer updating CI actions |
| SBOM and provenance evidence | SLSA provenance; CycloneDX/SPDX SBOM | The release skill inventories SBOM, provenance, signature, checksum, and OpenSSF Scorecard evidence and makes absence a release finding. `scripts/enterprise_evidence.py` can inventory local evidence and optionally run installed local SBOM/vulnerability generators. It does not fabricate attestations. | `ce-ship-release/SKILL.md`, `scripts/enterprise_evidence.py` | Build/release engineering |
| Tool and plugin integrity | OWASP Agentic: unsafe plugin/tool design | Strict manifest validation, corpus lint, model-policy validation, known slash surface, and no stale aliases. | `scripts/check.py`, `scripts/corpus_lint.py`, `.github/workflows/plugin-validate.yml`, `plugins/core-engineering/model-policy.json` | Plugin maintainer |
| In-session subversion of a guard hook | OWASP Agentic: unsafe tool/plugin design; supply-chain (self-modifying tooling) | The PreToolUse guards cannot detect their own subversion — an in-session `sed -i` on `env-guard.py` disarms it silently. `hooks/hook-integrity.py` runs at **SessionStart**, recomputes the sha256 of every `hooks/*.py` + `hooks.json`, and warns loudly (never blocks) on any drift from the shipped `integrity-manifest.json`. `scripts/hook_manifest.py --check`, run by `scripts/check.py` §5d, makes a hook edit that skipped a manifest refresh CI-red. Tamper-*evidence*, not tamper-proofing: an agent with Bash can rewrite the manifest too, but the *committed* manifest is CI-verified, so any drift is auditable in the reviewable diff (the same claim class as the merge bar's `sha256sum -c` step). | `plugins/core-engineering/hooks/hook-integrity.py`, `plugins/core-engineering/hooks/integrity-manifest.json`, `scripts/hook_manifest.py`, `scripts/check.py`, `tests/test_hook_manifest.py` | Plugin maintainer refreshing the manifest on an intentional hook change |
| AI-authored changes merging on green checks alone | Segregation of duties; SLSA source/build platform controls; OWASP Agentic: unsafe delegation | `merge-policy.json` encodes a two-conjunct merge bar (machine integrity gates AND a human/two-human validity attestation, with no `none` value); `scripts/gate_runner.py` executes the integrity conjunct as one machine verdict per PR; adopters install the composite action `action/merge-bar` pinned at a full 40-hex commit SHA (the preferred path — the action refuses a movable ref at run time, and the one pin fetches runner, policy, and gate scripts atomically) or copy in `templates/adopter-ci/gates.yml` (the checksum-pinned copy-in fallback), which refuses a non-SHA `TOOLKIT_REF`, fetches the toolkit at that pinned commit, and verifies all five decision-making files (runner, policy, spec-lint, test-guard, dep-guard) via `sha256sum -c` before running; it is not offline unless the checkout is pointed at an approved internal mirror. Both surfaces read any policy override from the base ref only, while they union the declared-deps list from base and head, so a same-PR declaration remains governed by the unchanged base policy and its review escalation; every verdict records the policy path + sha256 and the resolved base/head commit SHAs. The bar proves integrity, not function — it never builds the project or runs its test suite (see "What the merge bar does not prove" below). | `plugins/core-engineering/merge-policy.json`, `scripts/gate_runner.py`, `templates/adopter-ci/gates.yml`, `merge-verdict.json` in CI logs, `tests/test_gate_runner.py` | Adopter branch-protection config (required status check + required review count), a CODEOWNERS/ruleset review requirement on `.github/**`, and the adopter's own build/test job kept as a second required check |
| Tampering with stored merge-verdict bytes | Signed source-integrity evidence; OWASP Agentic: unsafe delegation | With `attest: 'true'`, `scripts/verdict_predicate.py` projects the green verdict to a whitelisted custom predicate and GitHub's keyless OIDC attestation signs those bytes under the workflow identity. A verifier pins the expected signer workflow and checks the predicate's commits. This detects later byte tampering; it does not prove that a PR-editable calling workflow ran the expected policy honestly. CODEOWNERS/ruleset protection or a trusted reusable signer workflow remains required. The custom predicate is not SLSA build provenance. | `action/merge-bar/action.yml`, `scripts/verdict_predicate.py`, `tests/test_verdict_predicate.py`, GitHub's attestation service (public transparency log for public repositories; private GitHub Sigstore service for supported private repositories) | Adopter workflow/ruleset owner and verifier policy |
| Stale published pin checksums | SLSA provenance (release integrity) | Every `v*` tag push triggers `.github/workflows/release-pin-block.yml`, which regenerates the adopter pin block from committed state at the tagged commit (`scripts/print-pin-block.sh` hashes `git show` blobs, so working-tree dirt can never leak into a published pin) and publishes it into the GitHub Release notes — created if the tag has no Release, notes replaced if one exists — so published checksums are generated, never hand-typed; `--verify-tag` refuses to create a Release for a tag the remote does not have, and `scripts/supply_chain_check.py` holds needles on the workflow so the release chain cannot be silently deregistered. | `.github/workflows/release-pin-block.yml`, `scripts/print-pin-block.sh`, `tests/test_print_pin_block.py`, `scripts/supply_chain_check.py` | Human release owner reviewing the release commit and managing any tag-signature policy |
| Auditability and traceability | Enterprise SDLC governance | Plans/specs/reviews/verifications/release decisions are durable markdown/JSON under `docs/`; metrics are append-only; retro exports evidence rather than attestation. `scripts/metrics_report.py` projects repo-level metrics and gaps for dashboards. | `docs/HOW-IT-WORKS.md`, skill artifact templates, `/core-engineering:ce-retro` audit export, `scripts/metrics_report.py` | Project owner |
| Post-merge artifact drift on `main` | SDLC/QMS monitoring evidence; source integrity over the branch's life | `scripts/drift_scan.py` re-projects committed `HEAD` against registered plan directories and reports broken traceability or retired-surface residue. This is a repository-artifact signal, not the active performance-data collection, analysis, lifetime monitoring system, or documented monitoring plan required by EU AI Act Article 72. | `scripts/drift_scan.py`, `templates/adopter-ci/drift.yml`, `drift-verdict.json`, `tests/test_drift_scan.py` | Adopter CI owner; any regulated-system monitoring owner |

## Enforcement Surfaces

These controls are deterministic and CI-checkable:

- `scripts/check.py` validates manifests, frontmatter, byte-identical gate copies,
  model policy, README catalog drift, corpus hygiene,
  and now enterprise hardening drift through `scripts/supply_chain_check.py`.
- `scripts/supply_chain_check.py` validates pinned GitHub Actions, checksum
  verified secret scanning, supply-chain release prompts, adversarial
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
  `.github/workflows/action-selftest.yml`), and the SHA-verified copy-in
  checksum-pinned copy-in template (`templates/adopter-ci/gates.yml`) from being silently
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

- `/core-engineering:ce-ship-release` records SBOM, SLSA provenance, signatures, checksums, and
  OpenSSF Scorecard evidence as readiness inputs. Missing evidence becomes a
  finding at the Release-Readiness Gate.
- `/core-engineering:ce-ask` and `/core-engineering:ce-impact` are read-only, citation-bound, and tested against
  malicious repository instructions.
- `write-scope-guard.py` enforces a repo/session write lease when
  `.claude/ce-write-scope.json` is present: read-only-on-code skills set a
  lease at Stage 0 and clear it at exit, over the deny-only baseline
  `/core-engineering:ce-init` seeds (`.git/**` and the lease file itself are never
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
  (seeded by `/core-engineering:ce-init`), it screens outbound network on `Bash`/`WebFetch`/
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
- `/core-engineering:ce-probe-sec` requires twice-attested consent before dynamic security probing.
- `/core-engineering:ce-probe-infra` is static, redacts secrets, and routes dynamic confirmation to
  the human or the appropriate probe.

## Evidence and Attestation

Enterprise adopters should treat these as evidence artifacts, not as blanket
attestations:

- Validation output from:

  ```bash
  python3 scripts/check.py --no-install-hooks
  python3 scripts/eval_check.py
  python3 scripts/eval_run.py --profile smoke --out-dir /tmp/vg-eval-smoke-dry-run
  python3 scripts/eval_run.py --profile benchmark --out-dir /tmp/vg-eval-benchmark-dry-run
  python3 scripts/metrics_report.py --json
  python3 scripts/enterprise_evidence.py --json
  python3 scripts/portability_check.py
  python3 -m unittest discover -s tests -v
  ```

- Release decision packages under `docs/plans/<slug>/release/`.
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

The EU AI Act defines obligations for providers and deployers of high-risk AI
systems, including system logging and a documented post-market monitoring
system. This framework does **not** determine whether a system is high-risk,
implement those product-lifecycle controls, set a retention policy, or render a
conformity assessment. It can compile and hash selected **SDLC records** that a
human control owner may use inside a broader QMS. The mapping below is a
vocabulary bridge and gap inventory, not a compliance claim.

Reference the authoritative [EU AI Act text](https://eur-lex.europa.eu/eli/reg/2024/1689/oj?locale=en),
[GitHub artifact-attestation documentation](https://docs.github.com/en/actions/concepts/security/artifact-attestations),
and [SLSA build-provenance specification](https://slsa.dev/spec/v1.2/build-provenance)
when designing the surrounding controls.

The evidence-pack bundle (`plugins/core-engineering/skills/ce-retro/scripts/evidence-pack.py`,
byte-identical fork bundled in `ce-ship-release`) — compiled by `/core-engineering:ce-retro`'s export
mode and by `/core-engineering:ce-ship-release` per release, written under a dated
`docs/plans/<slug>/evidence-pack/<date>/` convention — carries the artifacts each row
cites. Every section is populated or gap-listed; an absent source is recorded in
`gaps[]`, never silently zeroed.

| Regulatory vocabulary | Pack section / framework control | Evidence artifact in this repo |
|---|---|---|
| **Potential supporting SDLC evidence for Art 12 analysis** | The guard log and `.metrics.jsonl` record selected coding-workflow events. They are not automatic logs of a high-risk AI system's operation throughout its lifecycle and do not implement Article 12. | `.claude/ce-guard-log.jsonl`, `docs/plans/<slug>/.metrics.jsonl`, `docs/plans/<slug>/evidence-pack/<date>/pack.json` |
| **EU AI Act Art 11 / Annex IV — technical documentation** of the system and its development | The plan / spec / verification / review artifacts the pack compiles verbatim with their sha256 — the `human_attestations`, `dismissal_records`, and `model_identity` sections plus the copied `artifacts/` tree | `docs/plans/<slug>/` (`plan.json`, `specs/`, `verification-report.md`, `specs/<id>/code-review.md`), the pack's verbatim `artifacts/` copies |
| **EU AI Act Art 9 — risk management** (residual risk knowingly accepted) · **ISO 27001 risk acceptance** | The pack's `finding_dispositions` section: the merge bar's accepted-risk register. An advisory gate (`secrets-guard`, `sca-guard`) *suppresses* a finding a named human accepted with a reason and a dated expiry, instead of re-alarming on every PR — and the pack renders every entry, **split active vs expired**, so a suppression is never invisible to whoever reads it. An **expired** entry suppresses nothing (its finding re-alarms), is listed in the pack, and fails `disposition-lint` in CI: a disposition defers, it never forgets. An **absent** ledger means nothing was accepted (`present: false`, not a gap); an **unreadable** one is a gap, because the pack must not confuse "nothing accepted" with "the register is broken". Reported as found and never re-judged — the pack does not verify that the named `accepted_by` approved the entry | `.merge-bar/dispositions.json`, `plugins/core-engineering/skills/ce-probe-infra/scripts/disposition-lint.py` (CI lint), `docs/plans/<slug>/evidence-pack/<date>/pack.json` (`sections.finding_dispositions` + the verbatim sha256-stamped ledger copy) |
| **Potential supporting evidence for Art 18 retention processes** | The framework creates dated pack directories, but it does not enforce immutability, the statutory retention period, availability to authorities, backup, or deletion controls. Those remain adopter storage-policy responsibilities. | `docs/plans/<slug>/evidence-pack/<date>/` |
| **Custom source-integrity evidence (not SLSA build provenance)** | The merge verdict records policy sha256, base/head commits, and change class. It does not use the SLSA provenance predicate or provide the required build definition and run details. | `merge-verdict.json`, `docs/plans/<slug>/evidence-pack/<date>/pack.json` |
| **Signed custom merge-verdict record** | `attest: 'true'` signs the custom predicate bytes under a GitHub workflow identity. Verification must constrain the signer workflow and commits. The signature does not make PR-controlled predicate fields trustworthy and does not implement Article 12 or SLSA build provenance. | `action/merge-bar/action.yml`, `scripts/verdict_predicate.py`, GitHub artifact attestation |
| **SLSA provenance** — workflow-signed attestation of eval evidence | Not implemented. A future CI-attested eval `summary.json` could carry a resolvable `ci_run_url` plus a build-provenance attestation digest referenced by the pack. | *(current gap — this document does not cite a control that does not exist; see Gaps and Roadmap)* |
| **Potential input to an Art 72 monitoring process** | `scripts/drift_scan.py` detects repository artifact drift. Article 72 additionally requires a documented system that actively and systematically collects and analyses relevant performance data throughout the high-risk AI system's lifetime; this repository check is not that system or plan. | `scripts/drift_scan.py`, `templates/adopter-ci/drift.yml`, `drift-verdict.json` |

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
  runner cannot verify that a human actually approved. GitHub cannot vary the
  approval count per PR from that runtime class, so the supported conservative
  mapping is two approvals globally; `human` is a reported minimum. An adopter
  who skips that branch-protection rule silently degrades the bar to
  integrity-only.
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

1. Produce a fresh, receipt-backed live baseline for the lean workflow and
   compare it with the previous contract on the same model and fixtures.
2. Track input/context proxy, human review time, first-pass verification,
   seeded-defect recall, false positives, and park/retry/could-not-run rates.
3. Add focused evals for architecture adjustment, compact/explicit
   specification routing, independent review-plus-verify, and
   documentation/audit-before-release.
4. Only after that evidence is stable, consider optional Scorecard, sample
   SBOM, and provenance/signature workflows with pinned actions and reviewed
   permissions.
