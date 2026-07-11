# vg-coding

> ## Any agent writes the code. Your bar decides what merges.

Let your engineers use whatever coding agent they like — Cursor, Copilot,
Codex, Claude Code, or a human at a keyboard. **vg-coding emits a
repository-resident integrity verdict for your merge policy; your Git host's
branch protection and required human review remain the merge authority.** Its
core is an agent-agnostic, offline **merge bar**: a stdlib-only gate runner
(`scripts/gate_runner.py` over a committed
[`plugins/core-engineering/merge-policy.json`](./plugins/core-engineering/merge-policy.json))
that judges *committed state* against configured deterministic checks — spec
traceability, recognized test-weakening patterns, and undeclared dependency
changes — with **zero Claude Code installed**, and emits one SHA-anchored
machine verdict an auditor can read. It wires into any PR in three workflow
lines via the [`action/merge-bar`](./action/merge-bar/README.md) composite
action, or a copy-in [`templates/adopter-ci/gates.yml`](./templates/adopter-ci/gates.yml)
for air-gapped orgs. A prompt cannot override a deterministic failure without
changing its committed inputs or the protected policy/workflow. The
[architecture guide](./docs/HOW-IT-WORKS.md) explains the full control model,
and the [comparison](./docs/COMPARISON.md) places it alongside alternative
approaches.

> [!IMPORTANT]
> These tools generate code, specifications, and review feedback. They do not push to production, merge PRs, deploy services, or rotate credentials on their own — every output is staged for human review. You are responsible for verifying outputs and for the security and correctness of code that ships from your repos.

## Install

```bash
# Add the marketplace, then install the plugin
claude plugin marketplace add relusion/vg-sdlc-claude-plugins
claude plugin install core-engineering@vg-coding
```

Skills then fire automatically when relevant or run directly by their `ce-`-prefixed name (`/ce-plan`, `/ce-review`, …). The merge bar needs no install — it runs in CI from the pinned [`action/merge-bar`](./action/merge-bar/README.md) or the copy-in template. The upstream idea/market skills ship as a separate [`product-discovery`](#the-product-discovery-plugin) plugin; add it only if you want the discovery front-end.

## Week one — eight verbs

Most of the first-week value comes from eight skills. The cost floors below are
measured in USD per invocation ([full results & costs](./docs/BENCHMARKS.md));
everything else routes through [`docs/USAGE-MATRIX.md`](./docs/USAGE-MATRIX.md).

| Verb | Use when | Cost floor (USD) |
|---|---|---|
| `/ce-init` | First-run repo bootstrap: profile commands, CI, surfaces; write starter policy | local, no model call |
| `/ce-ask` | Grounded, `file:line`-cited answer to a codebase question | ~$1 |
| `/ce-impact` | Blast-radius read of a proposed change or work item before building | ~$1 |
| `/ce-patch` | One genuinely-small bounded change through the folded patch lane | ~$4 |
| `/ce-plan` | Decompose a project into an ordered, dependency-aware feature plan | ~$3 |
| `/ce-spec` | Detail one planned feature into EARS criteria + `tasks.json` | ~$4 |
| `/ce-implement` | Build one specified feature test-first, task by task | ~$3 |
| `/ce-review` | Independently code-review a built feature across six lenses | ~$2 |

**Measured, with dates:** a 2026-06-27 live batch passed ten scenarios — including grounded Q&A for ~$1, an implementation-ready lint-clean spec for ~$4, and a seeded IDOR caught by review for ~$2. The skills have changed since that batch, so the recency ratchet now labels every current row **design-verified, not live-run** until it is rerun ([results, costs, and caveats](./docs/BENCHMARKS.md); [historical outputs and current goldens](./docs/EXAMPLES.md)). Structural claims are CI-enforced by 138 repo checks, 368 authoring-conformance checks, and 968 tests. Evaluating options? See [the comparison vs. spec-kit / Kiro / aider](./docs/COMPARISON.md); rolling it out to a team, see [the pilot guide](./docs/TEAM-ROLLOUT.md).

## The `core-engineering` plugin

The core plugin carries the whole engineering framework: **29 skills** and **2 plugin-shipped custom agents**, organized as one spec-driven spine plus a set of discovery, probe, and delivery utilities (the upstream idea/market trio now ships as the companion `product-discovery` plugin, described [below](#the-product-discovery-plugin)). The skills hold the workflows and are the public slash-invocation surface. The **[documentation index](./docs/README.md)** routes by audience; start with **[Getting Started](./docs/GETTING-STARTED.md)** for the first session, use the **[Usage Matrix](./docs/USAGE-MATRIX.md)** to pick a skill, and follow **[Workflow Recipes](./docs/WORKFLOW-RECIPES.md)** for complete paths.

The production spine — each skill escalates conflicts *up* a layer, never expands its own scope:

```
brief → plan → spec → implement
                       gated by verify · review · debug
       auto-build  orchestrates the whole chain unattended
       patch       folds the spine for one genuinely-small change
       ux-audit    walks the plan's journeys against the running app (or, plan-free, adversarially probes it)
       then the delivery tail:  deliver → release → document
```

Plugin skills are invoked directly with `ce-`-prefixed names, e.g. `/ce-plan`, `/ce-probe-sec`, and `/ce-ship-release`.

### Skill map

<!-- skill-catalog:start -->
| Family | Skills | Use when |
|---|---|---|
| Front door | `/ce-go` | Not sure which skill runs your request: inspect repo state and route to the one right skill (it routes, never executes). |
| Repository setup | `/ce-init` | First-run repo bootstrap: profile commands, CI, surfaces, and write starter SDLC policy artifacts. |
| Production spine | `/ce-brief`, `/ce-plan`, `/ce-spec`, `/ce-implement` | Turn an idea into a plan, specs, tasks, and working code under the Scope Lock (planned boundary, then approved spec). |
| Spine gates | `/ce-verify`, `/ce-review`, `/ce-debug`, `/ce-ux-audit` | Check behavior, code quality, and UX journeys (planned, or adversarially probed plan-free), and diagnose any failure — a planned feature or a plan-free component (a stuck service/worker) — without widening scope. |
| Autonomous / small change | `/ce-auto-build`, `/ce-patch` | Run the spine end-to-end, or handle one genuinely small change through the folded patch lane. |
| Codebase bridging | `/ce-ask`, `/ce-impact`, `/ce-onboard`, `/ce-domain`, `/ce-decide`, `/ce-plan-audit`, `/ce-retro` | Ask grounded questions, analyze change impact, teach the implementation (or the business domain the code encodes), choose technical options, audit plans, and review pipeline signals. |
| Probes | `/ce-probe-sec`, `/ce-probe-perf`, `/ce-probe-infra`, `/ce-probe-deps` | Probe security, performance, infrastructure, and dependency advisories from the appropriate static or dynamic surface (adversarial UX probing now lives in the ce-ux-audit plan-free mode above). |
| Delivery | `/ce-ship-backlog`, `/ce-ship-deliver`, `/ce-ship-release`, `/ce-ship-document`, `/ce-humanize`, `/ce-doc-audit` | Convert specs into work items, prepare delivery, decide release readiness, produce docs, rewrite generated prose to read naturally, and validate that a reader can follow existing docs (findings only, never edits). |

**Companion `product-discovery` plugin** (installed separately — see [below](#the-product-discovery-plugin)). Invocation names are unchanged, so these still fire once it is installed:

| Family | Skills | Use when |
|---|---|---|
| Idea and market | `/ce-idea-scout`, `/ce-idea-score`, `/ce-market-scan` | Generate, score, and evidence-check product directions before planning. |
<!-- skill-catalog:end -->

### Practical starting paths

- First run in an existing repo: `/ce-init --write`, then `/ce-ask` or `/ce-impact`.
- New product or feature: `/ce-brief` → `/ce-plan` → `/ce-spec` → `/ce-implement`.
- Small bounded fix: `/ce-patch`; it graduates to `/ce-plan` if the change proves structural.
- Existing code question: `/ce-ask` for one answer, `/ce-onboard` when a maintainer needs a paced walkthrough, or `/ce-domain` to learn the business domain the code encodes.
- Work-item refinement: `/ce-impact` for a grounded, file-cited blast-radius read before planning or estimating.
- Risk discovery: `/ce-probe-infra` for static manifests, `/ce-probe-deps` for known-vulnerable dependency pins, `/ce-probe-sec` for a live target, `/ce-probe-perf` for measured performance, `/ce-ux-audit` for adversarial UX exploration (plan-free) or a plan's traced-journey walk.
- Pre-implementation confidence: `/ce-plan-audit` for a written plan, then `/ce-review` and `/ce-verify` after implementation.

## The `product-discovery` plugin

The three upstream idea/market skills — `/ce-idea-scout`, `/ce-idea-score`, `/ce-market-scan` — ship as a small **companion plugin** in this same marketplace. They score *product* directions before any engineering starts, so they live one plugin over from the core engineering spine; install core alone and you never carry them, add this plugin when you want the discovery front-end.

```bash
claude plugin install product-discovery@vg-coding
```

**Moved, not renamed.** These skills used to live in `core-engineering`; the invocation names are unchanged (`/ce-idea-score`, `/ce-idea-scout`, `/ce-market-scan`), so any muscle memory or doc that names them still works once the companion plugin is installed. The [Usage Matrix](./docs/USAGE-MATRIX.md) shows when to use each one and how the selected direction flows into `/ce-brief`.

## Plugin-shipped custom agents

The Claude Code plugin also ships two custom agents under
[`plugins/core-engineering/agents/`](./plugins/core-engineering/agents/). They are
leaf wrappers around the same skills:

| Agent | Skills | Use when |
|---|---|---|
| `spec-author` | `ce-plan` + `ce-spec` | You want a focused agent to turn an idea or planned feature into `docs/plans/<slug>/` artifacts and `ce-spec.md` / `tasks.json`. |
| `spec-impl` | `ce-implement` | You want a focused agent to implement an approved `ce-spec.md` / `tasks.json` test-first, update the task ledger, and write `verification.md`. |

They are intentionally leaf agents: no nested `Task` fanout, no git push/PR/merge
authority, and no production deployment authority. Use them directly from Claude
Code's agent picker or as the named workers an orchestrating skill delegates to.

## Managed-agent cookbooks (experimental)

The Claude Code plugin is the primary surface. The same skills are additionally
packaged as four named managed-agent cookbooks for headless deployment via
`/v1/agents` — an **experimental**, secondary surface, not co-equal with the
plugin. Plugin hooks (write leases, `git-guard`, deterministic gate enforcement)
**do not load on the managed-agent surface**, so use this path only when the
host supplies equivalent sandboxing, approvals, and policy enforcement. The
reference host-owned flow is documented in
**[managed-agent-cookbooks/ORCHESTRATION.md](./managed-agent-cookbooks/ORCHESTRATION.md)**:
`spec-author -> spec-impl -> quality-gate -> release-coordinator`.

| Function | Agent | Bundles | What it does |
|---|---|---|---|
| **Specification** | **[Spec Author](./managed-agent-cookbooks/spec-author)** | `ce-plan` + `ce-spec` | Raw idea → feature plan → `ce-spec.md` / `tasks.json` with full traceability |
| **Implementation** | **[Spec Impl](./managed-agent-cookbooks/spec-impl)** | `ce-implement` | Approved spec → test-first execution loop → working code + a verification report |
| **Quality Gate** | **[Quality Gate](./managed-agent-cookbooks/quality-gate)** | `ce-review` + `ce-verify` + `ce-debug` | Implemented work → review findings, verification report, and routed diagnosis |
| **Release Handoff** | **[Release Coordinator](./managed-agent-cookbooks/release-coordinator)** | `ce-ship-deliver` + `ce-ship-release` + `ce-ship-document` | Verified plan → delivery manifest, release decision, and user-facing docs handoff |

Each cookbook's `agent.yaml` references the plugin's skills directly (`../../plugins/core-engineering/skills/...`) — the same skill corpus, repackaged for this experimental surface. See **[managed-agent-cookbooks/](./managed-agent-cookbooks)** for `agent.yaml`, the system prompt, steering-event examples, and per-agent security notes.

## Repository Layout

```
plugins/
  core-engineering/              # primary plugin
    agents/                      # 2 Claude Code custom agents: spec-author · spec-impl
    skills/<name>/               # the workflows; SKILL.md + optional stage files + scripts/
    hooks/                       # git-guard.py + env-guard.py + write-scope-guard.py + hooks.json
    model-policy.json            # machine-readable model-tier policy (validated by check.py)
    mcp/                         # gate-runner MCP server — the merge bar + gates as MCP tools for any MCP-capable runtime
    .mcp.json                    # registers the gate-runner MCP server; extend with your own
  product-discovery/             # companion plugin: idea-scout · idea-score · market-scan
    skills/<name>/               # discovery workflows and their lint helpers
    model-policy.json            # companion plugin's model-tier policy
.claude-plugin/marketplace.json  # marketplace manifest — registers both plugins
managed-agent-cookbooks/         # Claude Managed Agent cookbooks — spec-author · spec-impl
                                 #   · quality-gate · release-coordinator
  ORCHESTRATION.md               # experimental handoff path and required host gates
action/
  merge-bar/                     # composite GitHub Action — the merge bar as a 3-line CI adoption
  test-integrity/                # composite GitHub Action — the standalone test-integrity gate (genie-catcher)
templates/
  adopter-ci/                    # copy-in air-gapped fallback workflow for adopter repos (gates.yml)
scripts/                         # check.py · corpus_lint.py · portability_check.py · product_layer_check.py · validate.py
                                 #   · deploy-managed-agent.sh · test-cookbooks.sh · orchestrate.py
                                 #   · eval_check.py · eval_run.py · supply_chain_check.py · version_bump.py
tests/                           # offline unittest suite for the repo + gate scripts (CI-run)
evals/                           # behavior eval scenarios, fixtures, goldens, and eval guide
docs/README.md                   # audience-based documentation index
docs/GETTING-STARTED.md          # first-session path and local validation commands
docs/USAGE-MATRIX.md             # canonical skill-selection router
docs/WORKFLOW-RECIPES.md         # end-to-end operating recipes with stop conditions
docs/HOW-IT-WORKS.md             # canonical framework overview
docs/contributing/               # skill-authoring and human-gate standards
```

Everything is file-based — markdown, JSON, and a little Python. No build step.

## Getting Started

### Claude Code

Install the plugin as shown under [Install](#install) above. Once installed, skills fire automatically when relevant or can be invoked directly — e.g. `/ce-init`, `/ce-plan`, `/ce-spec`, `/ce-implement`, `/ce-review` (spine), `/ce-ask`, `/ce-probe-infra`, `/ce-ship-release`.
The plugin-shipped `spec-author` and `spec-impl` custom agents are available from
Claude Code's agent picker after installation.

### Claude Managed Agents

```bash
export ANTHROPIC_API_KEY=sk-ant-...
scripts/deploy-managed-agent.sh spec-author
scripts/deploy-managed-agent.sh spec-impl
scripts/deploy-managed-agent.sh quality-gate
scripts/deploy-managed-agent.sh release-coordinator
```

Each cookbook references the same skills as the plugin. The deploy script resolves file references, uploads the skills, wires any subagents, and POSTs the agent to `/v1/agents`. See [`scripts/orchestrate.py`](./scripts/orchestrate.py) for a reference event loop that routes `handoff_request` events between agents via your own orchestration layer.

> **Status — beta surface.** `/v1/agents` requires **Managed Agents beta access** (the deploy script sends `anthropic-beta: managed-agents-2026-04-01`); without the entitlement, deployment fails. The deploy script additionally needs `jq` and Python `pyyaml`. The four cookbooks ship as **single-process agents** (`callable_agents: []` — subagent delegation is a preview capability, not yet wired), and `scripts/orchestrate.py` is a **reference loop you run and own**, not a hosted workflow engine. The Claude Code plugin path has none of these constraints. See per-agent READMEs for security and handoff guidance.

### The merge bar in CI (any repo — no plugin required)

The same integrity gates the skills enforce also ship as a composite GitHub Action: an agent-agnostic, offline, stdlib-only merge bar that gates every PR identically no matter what wrote the code. Adoption is three workflow lines:

```yaml
- uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
  with: { fetch-depth: 0 } # the diff gates need the base ref, not a shallow tip
- uses: relusion/vg-sdlc-claude-plugins/action/merge-bar@<PIN-ME-40-HEX-COMMIT-SHA>
```

Pin the full 40-hex commit SHA of the release commit you trust — the action refuses movable refs, and that one pin fetches the runner, policy, and gate scripts atomically. A green verdict proves **integrity, not function** (traceability held, tests not weakened, no undeclared dependency — never that the code compiles or its tests pass), so keep your own build/test job as a second required check. Details and threat model: [action/merge-bar/README.md](./action/merge-bar/README.md); air-gapped orgs copy [templates/adopter-ci/gates.yml](./templates/adopter-ci/gates.yml) instead; branch-protection wiring: [docs/TEAM-ROLLOUT.md](./docs/TEAM-ROLLOUT.md).

Want only the **test-integrity** half — the genie-catcher that fails a PR when a test was deleted, emptied, stripped of assertions, skipped, or stubbed trivially-true — without adopting specs or a merge policy? The same three-line adoption pins [`action/test-integrity`](./action/test-integrity/README.md) instead: one gate wrapping `test-guard.py`, catching by name the agent that makes tests pass by weakening tests. Integrity, never sufficiency — it never runs your suite, so keep your own build/test job alongside it.

## Making It Yours

These are reference templates — they get better when you tune them to how your team works.

- **Add MCP connectors** — `.mcp.json` ships the built-in `gate-runner` server (the merge bar + `spec-lint`/`test-guard`/`dep-guard` as MCP tools for any MCP-capable runtime); add your own alongside it, pointed at your data providers (GitHub, issue trackers, observability backends).
- **Add team context** — drop your terminology, processes, and standards into the skill files.
- **Adjust scope** — edit the skills to match how your team actually runs the workflow.
- **Add your own** — copy the structure for workflows we haven't covered.

## Contributing

Everything here is markdown, JSON, and a little Python. Fork, edit, PR — **[CONTRIBUTING.md](./CONTRIBUTING.md)** has the full validation battery, standards, and versioning rules. For new content:

- **New skill** → add it under the owning plugin at `plugins/<plugin>/skills/<name>/SKILL.md`, then update that plugin's model policy and the shared catalogs (skills are edited in place — there are no vendored copies to sync).
- **New plugin agent** → add a leaf custom agent under the owning plugin's `agents/` directory with `name`, `description`, and a scoped tool list; keep the skill as the source of truth.
- **New managed agent** → add a cookbook under `managed-agent-cookbooks/<slug>/` (`agent.yaml`, `system.md`, `README.md`, `steering-examples.json`) referencing the plugin's skills.
- Before pushing, run the canonical [full validation battery](./CONTRIBUTING.md#the-validation-battery). The umbrella check parses manifests, verifies skill/agent frontmatter and cookbook references, guards registered forked-gate copies from drift, checks the README catalog, and runs the corpus, authoring, managed-agent, product, and supply-chain checks. The remaining commands cover docs drift, eval fixtures and dry runs, evidence projections, portability, unit tests, cookbook deploy dry runs, and official plugin validation. Executed evals require `--execute` plus an explicit `--max-budget-usd`; under-budget full scenarios fail fast unless `--allow-low-budget` is passed deliberately. Update **[docs/HOW-IT-WORKS.md](./docs/HOW-IT-WORKS.md)** and this README in the same change whenever you add, rename, or remove a skill, plugin agent, managed-agent cookbook, gate, control, product route, or artifact path.

## License, commercial use, and third-party names

Except where a file expressly says otherwise, original project material is
licensed under the [Apache License 2.0](./LICENSE). Third-party material and
its terms are identified in
[THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md). The grants for versions
already published under Apache-2.0 continue according to its terms.
[COMMERCIAL.md](./COMMERCIAL.md) explains the project's current policy for
repository content, possible separate commercial offerings, and contributions;
it does not add to or replace the license.

This is an independent project. Third-party product names and trademarks belong
to their respective owners; references are for identification or comparison
and do not imply affiliation or endorsement.

Report security issues through the private channel described in
[SECURITY.md](./SECURITY.md). Copyright in original project material © 2026
Vladimir Gondarev and contributors.
