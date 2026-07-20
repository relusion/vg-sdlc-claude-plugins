# Changelog

All notable changes to `vg-coding` are recorded here. The plugin version in
`plugins/core-engineering/.claude-plugin/plugin.json` controls update delivery
for already-installed users, so user-visible plugin changes should update both
that version and this file.

## Unreleased

- **Simplified supported product surface (`core-engineering` 0.10.0).** Removed
  enforcement-count publishing, duplicate CI validator runs, the built-in MCP
  gate wrapper, and `/ce-ship-deliver`. The Managed Agent beta cookbooks and
  their deploy/orchestration tooling now live in an unsupported experimental
  archive and are excluded from mandatory validation and product navigation.
  `/ce-auto-build` now has one bounded sequential spec → implement → verify →
  independent-review profile with no worktrees, checkpoint branches, diagnose
  enrichment, or advanced modes. `/ce-patch` is now always the conservative
  two-file express lane; any failed or uncertain admission check routes directly
  to `/ce-plan`, and no patch plan/spec/task bundle is created. `/ce-go`, the
  usage matrix, and workflow recipes remain as the supported routing layer and
  now describe the smaller surface.
- **Domain onboarding.** Added `/ce-domain` to teach the business domain encoded
  by a repository with cited actors, nouns, lifecycles, rules, and known
  unknowns, distinct from `/ce-onboard`'s implementation walkthrough.
- **Team operating recipes.** Added verified recipes for knowledge handover,
  business-domain onboarding, and other composed team workflows already
  supported by the skill set.
- **Public-release documentation cleanup.** Added an audience-based
  `docs/README.md`; consolidated evaluation guidance into `evals/README.md`;
  colocated contributor standards under `docs/contributing/` and experimental
  orchestration under `experimental/managed-agent-cookbooks/`; removed the
  stale internal implementation plan, decision log, and duplicate workflow catalog. Runtime
  model-attestation state is now gitignored instead of tracked. Public claims,
  release-pin guidance, security-control descriptions, eval counts, links, and
  validation checks were updated to match the shipped behavior.
- **Licensing and commercial policy clarified.** `COMMERCIAL.md`, the README,
  and `CONTRIBUTING.md` now distinguish the durable Apache-2.0 grants for
  published versions from the project's current policy and any separate future
  commercial offerings. The docs accurately describe DCO sign-off, contributor
  copyright, and the current no-CLA policy; remove an unnecessary comparison
  to another open-source project; and add independent-project, trademark, and
  compliance disclaimers. Apache-2.0 license files now travel with both plugin
  packages, and the generated package-name corpus carries its required MIT and
  CC BY 4.0 notices. The security policy and pull-request checklist now state
  the private-reporting fallback, response target, and DCO requirement.
- **Merged: `/ce-probe-ux` → `/ce-ux-audit`.** The plan-free adversarial UX probe
  `/ce-probe-ux` is retired; its capability folds into `/ce-ux-audit` behind an
  auto-detected **mode probe**. `/ce-ux-audit` now resolves whether a plan owns the
  running surface (via `docs/plans/plans.json`) and picks its mode with a one-line
  announcement — no question, plan-existence is internal state:
  - **journey-walk mode** (a plan owns the surface) — the existing flow that walks
    the plan's traced journeys against the running app and reports mechanical UX
    findings (`docs/plans/<slug>/ux-findings.md`);
  - **adversarial-discovery mode** (no plan, or a plain running app) — chaos-test /
    fuzz / adversarially probe the app to *discover* unknown UX problems (dead-ends,
    validation gaps, state loss, layout breakage, a11y) on any repo, writing a dated
    `docs/ux-audits/<date>-<slug>.md`, exactly as `/ce-probe-ux` did.

  This is a **description-level redirect, no tombstone skill**: `/ce-ux-audit`'s
  description absorbs the retired trigger vocabulary ("chaos-test/fuzz/
  adversarially-probe a running app"), so intent that used to route to
  `/ce-probe-ux` now auto-routes to `/ce-ux-audit`. Users who type `/ce-probe-ux`
  should switch to `/ce-ux-audit` (same probe, adversarial-discovery mode). The
  skill count drops by one; `ce-probe-ux`'s model-policy entry, coverage waiver,
  and write-lease fork copy are removed, and the `("ce-probe-ux","ce-ux-audit")`
  router-cluster is dropped (one skill, no contrastive pair to maintain).

- **Merged: `/ce-troubleshoot` → `/ce-debug`.** The plan-free investigator
  `/ce-troubleshoot` is retired; its capability folds into `/ce-debug` behind an
  auto-detected **mode probe**. `/ce-debug` now resolves whether a plan/spec owns
  the failing target (via `docs/plans/plans.json`) and picks its mode with a
  one-line announcement — no question, plan-existence is internal state:
  - **planned mode** (a spec owns it) — the existing reproduce → `file:line` →
    classify → route flow (`diagnosis.md`);
  - **plan-free mode** (no plan/spec — a stuck consumer, silent worker, or job that
    stopped) — ranked, evidence-bound root-cause hypotheses + a discrimination plan
    (`docs/investigations/<date>.md`), exactly as `/ce-troubleshoot` did.

  This is a **description-level redirect, no tombstone skill**: `/ce-debug`'s
  description absorbs the retired trigger vocabulary ("investigate/troubleshoot a
  stuck service/worker/queue"), so intent that used to route to `/ce-troubleshoot`
  now auto-routes to `/ce-debug`. Users who type `/ce-troubleshoot` should switch
  to `/ce-debug` (same investigation, plan-free mode). The skill count drops by
  one; `ce-troubleshoot`'s model-policy entry, coverage waiver, and write-lease
  fork copy are removed.

- **One lock brand: "Scope Lock".** The five separately-named per-layer locks are
  consolidated into a single **Scope Lock** brand — one name, one glossary gloss,
  a different *scope* at each stage. The per-layer meaning is unchanged; only the
  name is unified. Formerly known as:

  | Old brand (retired) | Now | Scope it locks |
  |---|---|---|
  | Boundary Lock (`/ce-spec`) | Scope Lock | the planned feature boundary |
  | Spec Lock (`/ce-implement`) | Scope Lock | the approved spec |
  | Patch Lock (`/ce-patch`) | Scope Lock | the frozen file set |
  | Frame Lock (`/ce-market-scan`, `/ce-idea-score`) | Scope Lock | the framed decision space (the tool frames, the human decides) |
  | the Decide-Don't-Deploy lock (`/ce-ship-release`) | Scope Lock | the release decision — decide, never deploy |

  The term now carries one gloss in the shared consequence-glossary (both A9
  homes), and `authoring_check.py` A4 forbids reintroducing any old brand in
  skill/doc markdown. `drift_scan.py` findings keep the plan-vs-spec layer
  distinction via their route (`/ce-plan` vs `/ce-spec`), not a second brand.

## [0.9.0] — 2026-07-05

Repository release for the first control-plane milestone. The plugin manifests
at this tag were `core-engineering` 0.8.16 and `product-discovery` 0.1.1; plugin
manifest versions remain the update-delivery versions shown by Claude Code.

- **Extracted the idea/market trio into a new `product-discovery` plugin.**
  `/ce-idea-scout`, `/ce-idea-score`, and `/ce-market-scan` now ship in a
  separate companion plugin (`plugins/product-discovery/`) in the same
  `vg-coding` marketplace — install it with
  `claude plugin install product-discovery@vg-coding`. **Nothing was renamed:**
  the invocation names are unchanged, so existing muscle memory and docs keep
  working once the companion plugin is installed. A `core-engineering`-only
  install no longer carries the product-discovery front-end, dropping the core
  catalog from 31 to 28 skills. The move is a clean relocation (no tombstone
  skills); reverse it with a single `git mv` back plus the registry sweep.
  Registered end-to-end: `marketplace.json`, the new plugin's `plugin.json` +
  `model-policy.json`, README (new `product-discovery` section + install line),
  USAGE-MATRIX / WORKFLOW-RECIPES annotations, HOW-IT-WORKS,
  GETTING-STARTED, CLAUDE.md, and in-corpus routing pointers from `/ce-brief`,
  `/ce-decide`, `/ce-review`, `/ce-probe-perf`, `/ce-probe-sec`, and `/ce-go`
  that now name the companion plugin so a core-only session says where the trio
  went.
- New skill `ce-probe-deps` — the SCA gate: scans exactly-pinned dependency
  manifests (requirements.txt, npm lockfiles/exact pins) against the OSV.dev
  advisory database via the stdlib `sca-guard.py` floor. Loud offline/network
  degradation (exit 2 — never a silent pass), unpinned ranges listed rather
  than implied clean, only package coordinates ever leave the machine.
  Registered end-to-end: model-policy, README/USAGE-MATRIX/RECIPES catalogs,
  router cluster vs `/ce-probe-infra`, write-lease fork, merge-policy
  advisory gate (`sca-guard`), and eval scenario EVAL-016 with the
  `vulnerable-deps` fixture (satisfying the coverage ratchet).
- Proportionality Gate: `/ce-plan` checks request shape *before* the codebase
  profile spend, and `/ce-spec` / `/ce-implement` check ad-hoc invocations —
  each offers the `/ce-patch` lane (cost difference stated) when a request is
  patch-shaped; routing is consented and recorded in both directions, planned
  features are never silently re-routed, and WORKFLOW-RECIPES documents the
  thin-spine default. Model-tier down-route widening is explicitly deferred
  until live-eval evidence exists.
- Trust-layer lints — four contributor disciplines become machine-enforced:
  `authoring_check.py` A9 keeps the consequence-glossary's two copies in sync
  (term parity + anchor phrases in the contributor mirror and the runtime
  Legend) and A10 requires every skill with `[material` gates to state the R5
  gate-locator discipline (10 skills gained the missing locator instruction);
  `eval_check.py` gains the eval-coverage ratchet (every skill needs a
  scenario or a dated, reasoned waiver in `evals/coverage-allowlist.json` —
  expired or stale waivers are CI-red); `product_layer_check.py` now parses
  COMPARISON's "as of" date against a 90-day max age and asserts the
  README/BENCHMARKS/COMPARISON enforcement-count claims agree.
- Session write leases + fail-closed git-guard: every read-only-on-code skill
  (ask, impact, review, debug, troubleshoot, plan-audit, retro, onboard, the
  four probes, ux-audit) now sets a write-scope lease at Stage 0 and restores
  the deny-only baseline at exit, enforced by `write-scope-guard.py` (new
  `deny-only` mode; `/ce-init` seeds the baseline; denies carry the scoped
  opt-out and log to `.claude/ce-guard-log.jsonl`). The lease helper is a
  forked script (`write-lease.py`, 13 byte-identical copies registered in
  `fork-manifest.json`). `git-guard.py` now fails closed on
  recognized-but-malformed Bash payloads, asks on unrecognized shapes, and
  gains env tiers (`CE_GIT_GUARD_PUSH|PR|COMMIT=deny`) plus a documented kill
  switch (`CE_GIT_GUARD=off`).
- Live-eval CI path: `.github/workflows/eval-live.yml` runs the smoke profile
  against real models (manual dispatch + weekly schedule) with a hard
  per-scenario budget cap, skips explicitly when the `ANTHROPIC_API_KEY`
  secret is absent, and persists run records as CI artifacts.
  `evals/results/` is the committed home for curated run summaries; a
  supply-chain needle guards the workflow's safety properties
  (dispatch/schedule-only triggers, budget cap, skip notice); and
  BENCHMARKS now labels every scenario without a citable live run
  "design-verified, not live-run".

## [0.8.1] — 2026-07-02

### The agent-agnostic merge bar

- New `plugins/core-engineering/merge-policy.json`: the machine-readable merge
  bar — change classes mapped to required/advisory integrity gates, validated
  by `check.py` §14.
- New `scripts/gate_runner.py` (stdlib-only): executes a change class's gates
  against a repo's **committed** state and emits one verdict JSON with policy
  provenance (path, SHA256, shipped-default vs local override). Fail-closed on
  malformed policy, missing required gate scripts, duplicate policy keys, and
  gate exit-code/JSON contradictions.
- New `templates/adopter-ci/gates.yml`: copy-in PR gate for adopter repos.
  A PR cannot grade itself — policy and declared-deps are read from the base
  ref, and all five decision-making files are SHA256-verified at a pinned
  toolkit commit. Requires a CODEOWNERS/ruleset review on `.github/**` as a
  companion control (documented in TEAM-ROLLOUT and ENTERPRISE-HARDENING).
- 33 new tests (191 total); merge-bar docs in HOW-IT-WORKS,
  ENTERPRISE-HARDENING, TEAM-ROLLOUT, and COMPARISON.

## [0.8.0] — 2026-07-02

Initial release baseline; `0.8.0` is the baseline installed users update from.

### Corpus convergence

- Register the deliberately forked gate scripts (`spec-lint.py`,
  `test-guard.py`, `dep-guard.py`, `popular-packages.json`) in a
  machine-readable `fork-manifest.json`; `scripts/fork_sync.py` verifies or
  re-syncs every copy, and both `check.py` and `supply_chain_check.py` assert
  byte-identity from the same manifest.
- Externalize the four largest skills to staged progressive disclosure
  (`/ce-auto-build` 554→205 lines, `/ce-verify` 414→145,
  `/ce-troubleshoot` 412→217, `/ce-ship-release` 297→162) — stage bodies now
  load lazily, cutting per-invocation context cost.
- Add `scripts/authoring_check.py` (run by `check.py`) enforcing the
  `docs/contributing/SKILL-AUTHORING.md` standard: closed HITL heading vocabulary,
  `Gate N of M` sanity, one `<date>` placeholder convention, one name per
  concept, cross-cutting-rule invariant cores, router-cluster contrastive
  clauses, a 400-line `SKILL.md` cap, and the 1536-char description cap —
  and normalize ~50 accumulated drifts across the corpus to it.

### Product layer

- Add prerequisites and a measured "What It Costs" section to
  `docs/GETTING-STARTED.md`; move the contributor validation battery to
  `CONTRIBUTING.md`; add `SECURITY.md`, issue templates, and a PR template.
- Publish `docs/BENCHMARKS.md` (live eval results + per-skill measured cost
  floors), `docs/EXAMPLES.md` (real captured outputs), `docs/COMPARISON.md`
  (positioning vs. spec-kit / Kiro / aider / plain Claude Code), and
  `docs/TEAM-ROLLOUT.md` (pilot guide for team leads).
- State the Managed-Agents beta entitlement, `jq`/`pyyaml` prerequisites, and
  single-process (`callable_agents: []`) status up front in the README and
  `managed-agent-cookbooks/ORCHESTRATION.md`.
- Retire the stale internal session-handoff doc from `docs/`.

### Skills, agents, and evals (since the 0.8.0 baseline)

- Drop the legacy `commands/` dispatcher layer: `core-engineering` exposes its
  public slash surface directly from `skills/<name>/SKILL.md`.
- Add plugin-shipped Claude Code custom agents `spec-author` and `spec-impl`,
  plus validation so plugin agents keep matching frontmatter, scoped toolsets,
  and leaf-agent boundaries; `/ce-auto-build` prefers them when spawning
  per-feature spec and implementation workers.
- Add the `/ce-impact` and `/ce-init` skills and four Managed Agent cookbooks
  (`spec-author`, `spec-impl`, `quality-gate`, `release-coordinator`) with
  deploy and validation tooling.
- Add the behavior-eval platform: scenario catalog, fixture repos, golden
  `spec-lint` artifact, offline `eval_check.py`, and the dry-run/execute
  `eval_run.py` with smoke/full profiles, per-scenario budget
  recommendations, and under-budget fail-fast. Live runs of `EVAL-001`
  through `EVAL-010` pass and their outputs were converted into
  deterministic output/artifact checks (observed budgets recorded in
  `docs/BENCHMARKS.md`); an explicit `--bare` option supports deterministic
  CI-style runs, and Claude login failures classify as `auth-error`.
- Add supply-chain evidence handling to the release/delivery skills, CI and
  evidence collection scripts (`metrics_report.py`, `enterprise_evidence.py`),
  and the enterprise control map.
