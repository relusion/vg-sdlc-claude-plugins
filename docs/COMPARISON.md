# Choosing a Spec-Driven Toolchain

A date-stamped comparison of `core-engineering` against alternatives an
engineering lead would evaluate in mid-2026: **GitHub spec-kit**, **AWS
Kiro**, **aider**, and **plain Claude Code** (CLAUDE.md conventions, plan
mode, subagents — no plugin). All competitor facts below were verified
against primary sources (repos, official docs, changelogs, pricing pages)
**as of 2026-07-11**; this space moves fast, so re-verify anything
load-bearing before deciding. Where this framework is weaker, that's stated
too.

Prices shown below are in US dollars (USD).

## The short version

The spec-driven options here put structured intent before code and retain
artifacts; aider and plain Claude Code are lighter alternatives where planning
may remain conversational or tool-managed. The practical differences are how
much of the lifecycle is covered, how artifacts are validated, and which
runtime or product the workflow depends on.

## Side by side

| Dimension | core-engineering (this repo) | GitHub spec-kit | AWS Kiro | aider | Plain Claude Code |
|---|---|---|---|---|---|
| Unit of work & artifacts | optional brief → adaptive canonical plan (conditional evidence-rich architecture selection/baseline) → plan-routed compact or explicit specification, both producing linted `ce-spec.md`/`tasks.json` → implementation → independent verification/review → verified docs and conditional doc audit → final release package | per-feature `specs/<nnn-name>/spec.md` + `plan.md` + `tasks.md`, project `.specify/memory/constitution.md` | `.kiro/specs`: `requirements.md` + `design.md` + `tasks.md` per feature | conversational planning (`/ask`, architect mode); no prescribed plan artifact | Plan Mode writes tool-managed Markdown plan files (default `~/.claude/plans`, configurable); no prescribed project artifact schema |
| Requirements format | EARS, each criterion traced to tagged test cases and tasks | free-form in core; a community EARS author/lint/convert extension is available through the official catalog | EARS by default | n/a | n/a |
| Artifact validation | **deterministic linters over generated artifacts** — `architecture-selection-lint.py` (constraints, weighted score vectors, option and selection hashes), `spec-lint.py` (EARS→test→task traceability and architecture-provenance hard gates), `architecture-lint.py` (strict schema-v2 structure, source/selection closure, conditional coverage, deterministic projections, and approval receipts), `patch-lint`, `decide-lint`, `scan-lint`, `infra-lint`, byte-identity-guarded across consumers | core helpers validate prerequisites/paths; core semantic checks are agent-executed (`/speckit.analyze`, `/speckit.checklist`); extensions can add validators | agent-based Analyze Requirements; optional property-based tests generated from EARS and run against the implementation; shell-command hooks can enforce custom deterministic checks | linters/tests run on **code** after edits (auto-lint on, auto-test opt-in); nothing validates a prescribed plan artifact | no artifact validator shipped |
| Human gates | Actual decisions only: evidence-rich material choices are located, consequence-rendered, and human-owned; deterministic PASS, read-only work, projections, and clean negatives continue without re-attestation | agent-executed checklist checkpoint; `/speckit.implement` stops on incomplete checklists and asks whether to proceed; extension hooks can be mandatory | approval gates between phases by default, **optional** (Quick Plan skips them); blocking hooks available | git auto-commit per edit + `/undo`; no artifact gates | permission modes + hooks (deterministic but bring-your-own policy) |
| Lifecycle breadth | idea/market specialists → optional brief → adaptive plan with conditional architecture → compact/explicit spec route → implement → independent verify/review/debug → probes and UX audit → verified docs + conditional doc audit → final release decision → retro/onboarding (32 skills across 2 plugins) | core specify → plan → tasks → implement (+ converge, tasks-to-issues); the official catalog offers independently maintained extensions for review, security, release, and docs | spec → implement, with optional property-based testing and hooks; Web can open PRs and monitor CI | implementation-focused pair programming | explore → plan → code → commit (best-practices workflow) |
| Harness / agent support | **Claude Code only** (plugin) | 30+ agents/CLIs — the broadest listed integration catalog | Kiro IDE + CLI; Web is Preview; iOS is limited Preview | many hosted/local models and providers; terminal-based | Claude Code |
| Artifact portability | plain markdown/JSON in your repo; gate scripts are stdlib-only Python **proven in CI to run with zero Claude Code installed** | plain markdown in your repo | markdown in `.kiro/`, committed to repo | git history | plain files |
| Public validation evidence | deterministic repository, authoring, portability, supply-chain, and unit-test gates run in CI; historical live-eval assertions and configured caps are published with provenance limits, while current scenarios are labeled design-verified pending rerun ([BENCHMARKS](./BENCHMARKS.md)) | public OSS CI/test suite; core artifact semantics are agent-executed, with third-party validation extensions available | vendor-managed product | public OSS test suite | vendor-managed product |
| License & price | Apache-2.0; free; model usage extra. Historical tiny-fixture runs used configured caps of $1–$4; actual spend was not retained. See BENCHMARKS for coverage and recency caveats | MIT; free; agent/model usage may be extra | proprietary; $0–$200/user/month credit tiers; paid individual add-on credits and team overage currently $0.04/credit; model multipliers | Apache-2.0; free; model/provider usage may be extra | all rights reserved; available through Claude subscriptions, API usage, and supported cloud platforms |
| Backing & maintenance | single-maintainer | GitHub-maintained; frequent tagged releases through 2026-07-10 | AWS-managed; GA 2025-11-17; enterprise SSO | community OSS; latest PyPI release 0.86.2 (2026-02-12), with upstream source changes through 2026-05 | Anthropic-maintained |

## Key differentiators

Three practical differences:

1. **The artifacts have linters.** This repo ships deterministic artifact gates
   as part of the core distribution: a spec is rejected when an acceptance
   criterion has no test case, a test case has no task, or a patch exceeds its
   declared boundary. They run offline in CI. Spec-kit core's semantic checks
   are agent-executed; Kiro combines agent-based requirements analysis with
   optional executable property tests against code and user-defined hooks.
2. **The lifecycle doesn't end at `implement`.** Independent code review and
   behavior verification, four probe genres, verified docs with conditional
   reader audit, a final release decision, retros, and onboarding — with an escalation
   seam between every layer. That is broader out-of-the-box coverage than the
   competitors' core workflows; spec-kit extensions and Kiro hooks/services can
   add later phases, so compare the exact configuration you would adopt.
3. **An agent-agnostic merge bar.** Your engineers can use any coding agent —
   Cursor, Copilot, Codex, anything — the merge bar is ours: a stdlib,
   CI-side gate runner (`scripts/gate_runner.py` +
   `plugins/core-engineering/merge-policy.json` + a copy-in, SHA-verified
   workflow template in `templates/adopter-ci/`) that red-flags
   spec-traceability breaks, recognized test-weakening patterns, and undeclared
   dependencies according to the configured checks —
   wire the template to branch protection and it gates every PR regardless of
   what authored it. Those CI gates run independently of whichever agent or
   human authored the change. One important boundary: the bar's inputs are
   PR-tamper-hardened (base-ref reads, five-file checksums, SHA-pinned
   toolkit), but the adopter's workflow file itself needs a
   CODEOWNERS/ruleset review requirement on `.github/**` — documented as a
   required companion control in TEAM-ROLLOUT and as an explicit gap in
   ENTERPRISE-HARDENING.

## When to choose something else

- **You're not standardized on Claude Code** → **spec-kit**. Its 30+-agent
  portability is the widest by far, it's MIT, and GitHub is iterating fast.
  This framework is Claude-Code-native; that's a real constraint.
- **You want an IDE-shaped product with team billing, SSO, and a hosted
  autonomous agent** → **Kiro**. It's a managed product with enterprise
  controls; this repo is a framework you own and operate.
- **You want a lightweight pair-programmer, not a process** → **aider** or
  **plain Claude Code** with a good CLAUDE.md. A five-line fix doesn't need a
  spec pipeline (that's also why `/core-engineering:ce-patch` exists here).
- **You require multi-maintainer governance or vendor support** → use a project
  or product with that structure. This framework's artifact formats remain
  usable without the plugin, and the stdlib gate scripts do not require Claude
  Code. Full removal also means unwiring any CI action, MCP server, workflow, or
  repository rule you adopted.

## Sources

Primary sources checked 2026-07-11:

- spec-kit [repository](https://github.com/github/spec-kit),
  [v0.12.11 release](https://github.com/github/spec-kit/releases/tag/v0.12.11),
  [implement checkpoint](https://github.com/github/spec-kit/blob/main/templates/commands/implement.md),
  and [extension catalog](https://github.com/github/spec-kit/blob/main/extensions/catalog.community.json);
- Kiro [feature specs](https://kiro.dev/docs/specs/feature-specs/),
  [correctness/property tests](https://kiro.dev/docs/specs/correctness/),
  [hooks](https://kiro.dev/docs/hooks/), [Web](https://kiro.dev/docs/web/),
  [mobile](https://kiro.dev/mobile/), and [pricing](https://kiro.dev/pricing/);
- aider [modes](https://aider.chat/docs/usage/modes.html),
  [lint/test behavior](https://aider.chat/docs/usage/lint-test.html),
  [git integration](https://aider.chat/docs/git.html),
  [upstream commits](https://github.com/Aider-AI/aider/commits/main/), and
  [PyPI releases](https://pypi.org/project/aider-chat/);
- Claude Code [configuration](https://code.claude.com/docs/en/configuration),
  [plan-file behavior](https://code.claude.com/docs/en/claude-directory),
  [permission modes](https://code.claude.com/docs/en/permission-modes), and
  [best practices](https://code.claude.com/docs/en/best-practices).

Claims about this framework are enforced by this repo's CI or measured in
[BENCHMARKS.md](./BENCHMARKS.md). Third-party product names are used only for
identification and comparison; no affiliation or endorsement is implied.
