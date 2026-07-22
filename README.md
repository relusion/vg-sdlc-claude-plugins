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
for organizations that forbid third-party composite actions. The copy-in still
fetches the toolkit at a pinned commit; it is not an offline/air-gapped path. A
prompt cannot override a deterministic failure without
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

Most model-invocable skills can be selected automatically when relevant. Every
skill can also be called directly by its plugin-qualified name (`/core-engineering:ce-plan`,
`/core-engineering:ce-review`, …). The bounded or safety-sensitive workflows `/core-engineering:ce-auto-build`,
`/core-engineering:ce-patch`, `/core-engineering:ce-probe-perf`, `/core-engineering:ce-probe-sec`, `/core-engineering:ce-ship-release`, and
`/core-engineering:ce-doc-audit` are direct-invocation only.

The merge bar needs no plugin install; it runs in CI from the pinned
[`action/merge-bar`](./action/merge-bar/README.md) or the copy-in template. The
upstream idea/market skills ship as a separate
[`product-discovery`](#the-product-discovery-plugin) plugin; add it only when
you want the discovery front-end.

## Week one — eight verbs

Most of the first-week value comes from eight skills ([evaluation status and budgets](./docs/BENCHMARKS.md));
everything else routes through [`docs/USAGE-MATRIX.md`](./docs/USAGE-MATRIX.md).

| Verb | Use when |
|---|---|
| `/core-engineering:ce-init` | First-run repo bootstrap: profile commands, CI, surfaces; write starter policy |
| `/core-engineering:ce-ask` | Grounded, `file:line`-cited answer to a codebase question |
| `/core-engineering:ce-impact` | Blast-radius read of a proposed change or work item before building |
| `/core-engineering:ce-patch` | One low-risk change of at most two files through a single approval gate |
| `/core-engineering:ce-plan` | Frame capabilities, select a solution direction when needed, then decompose an ordered feature plan |
| `/core-engineering:ce-spec` | Detail one planned feature into EARS criteria + `tasks.json` |
| `/core-engineering:ce-implement` | Build one specified feature test-first, task by task |
| `/core-engineering:ce-review` | Independently code-review a built feature across six lenses |

Use the [three adoption tiers](./docs/USAGE-MATRIX.md#adopt-in-three-tiers) to
keep the surface manageable: begin with the core developer path, add advanced
delivery controls only after test/CI and human ownership are clear, and install
or invoke specialist workflows for a named job. Running
`/core-engineering:ce-init --readiness` reports local prerequisites separately from repository-host rules
that still require administrator verification.

**Historical, with explicit limits:** a curated 2026-06-27 summary records ten
scenario passes under configured per-run caps of $1–$4. It did not retain raw
runs or actual spend. The skills and receipt contract have changed since then,
so every current row is **design-verified, not live-run** until rerun.

See the [results, budget caps, and caveats](./docs/BENCHMARKS.md) and the
[historical outputs and current goldens](./docs/EXAMPLES.md). Deterministic
repository, authoring, and unit-test gates enforce the structural claims in CI.
For adoption decisions, use the [comparison](./docs/COMPARISON.md) and
[pilot guide](./docs/TEAM-ROLLOUT.md).

## The `core-engineering` plugin

The core plugin carries **29 skills** and **2 plugin-shipped custom agents**. It
centers on one spec-driven spine, with supporting codebase, probe, and release
workflows. The upstream idea/market trio lives in the companion
`product-discovery` plugin described [below](#the-product-discovery-plugin).

The [documentation index](./docs/README.md) routes by audience. Start with
[Getting Started](./docs/GETTING-STARTED.md), use the
[Usage Matrix](./docs/USAGE-MATRIX.md) to pick a skill, and follow
[Workflow Recipes](./docs/WORKFLOW-RECIPES.md) for complete paths.

The production spine — each skill escalates conflicts *up* a layer, never expands its own scope:

```
brief → plan [architecture explore + human direction] → decompose ⇄ architecture shape
      → [baseline when required/chosen] → spec → implement
                                             gated by verify · review · debug
       auto-build  runs the bounded loop after kickoff approval
       patch       handles one low-risk change of at most two files
       ux-audit    walks the plan's journeys against the running app (or, plan-free, adversarially probes it)
       then the release tail:   release → document
```

Plugin skills are invoked directly with plugin-qualified names, e.g. `/core-engineering:ce-plan`, `/core-engineering:ce-probe-sec`, and `/core-engineering:ce-ship-release`.

### Skill map

<!-- skill-catalog:start -->
| Family | Skills | Use when |
|---|---|---|
| Front door | `/core-engineering:ce-go` | Not sure which skill runs your request: inspect repo state and route to the one right skill (it routes, never executes). |
| Repository setup | `/core-engineering:ce-init` | First-run repo bootstrap: profile commands, CI, surfaces, and write starter SDLC policy artifacts. |
| Production spine | `/core-engineering:ce-brief`, `/core-engineering:ce-plan`, `/core-engineering:ce-architecture`, `/core-engineering:ce-spec`, `/core-engineering:ce-implement` | Turn an idea into an architecture-informed plan, publish the cross-feature baseline when the recorded disposition requires it, then produce specs, tasks, and working code under the Scope Lock. |
| Spine gates | `/core-engineering:ce-verify`, `/core-engineering:ce-review`, `/core-engineering:ce-debug`, `/core-engineering:ce-ux-audit` | Check behavior, code quality, and UX journeys (planned, or adversarially probed plan-free), and diagnose any failure — a planned feature or a plan-free component (a stuck service/worker) — without widening scope. |
| Autonomous / small change | `/core-engineering:ce-auto-build`, `/core-engineering:ce-patch` | Run the spine sequentially under explicit bounds, or handle one low-risk change of at most two files through one gate. |
| Codebase bridging | `/core-engineering:ce-ask`, `/core-engineering:ce-impact`, `/core-engineering:ce-onboard`, `/core-engineering:ce-domain`, `/core-engineering:ce-decide`, `/core-engineering:ce-plan-audit`, `/core-engineering:ce-retro` | Ask grounded questions, analyze change impact, teach the implementation (or the business domain the code encodes), choose technical options, audit plans, and review pipeline signals. |
| Probes | `/core-engineering:ce-probe-sec`, `/core-engineering:ce-probe-perf`, `/core-engineering:ce-probe-infra`, `/core-engineering:ce-probe-deps` | Probe security, performance, infrastructure, and dependency advisories from the appropriate static or dynamic surface (adversarial UX probing now lives in the ce-ux-audit plan-free mode above). |
| Delivery | `/core-engineering:ce-ship-backlog`, `/core-engineering:ce-ship-release`, `/core-engineering:ce-ship-document`, `/core-engineering:ce-humanize`, `/core-engineering:ce-doc-audit` | Convert specs into work items, decide release readiness, produce docs, rewrite generated prose to read naturally, and validate that a reader can follow existing docs (findings only, never edits). |

**Companion `product-discovery` plugin** (installed separately — see [below](#the-product-discovery-plugin)). Use that plugin's namespace once it is installed:

| Family | Skills | Use when |
|---|---|---|
| Idea and market | `/product-discovery:ce-idea-scout`, `/product-discovery:ce-idea-score`, `/product-discovery:ce-market-scan` | Generate, score, and evidence-check product directions before planning. |
<!-- skill-catalog:end -->

### Practical starting paths

- First run in an existing repo: `/core-engineering:ce-init --write`, then `/core-engineering:ce-ask` or `/core-engineering:ce-impact`.
- New product or feature: `/core-engineering:ce-brief` → `/core-engineering:ce-plan` (conditionally generates/scores solution directions and requires a human selection before detailed decomposition, then checks the cut through read-only shaping) → `/core-engineering:ce-architecture` when the recorded disposition requires a baseline, or when a recommended baseline is chosen → `/core-engineering:ce-spec` → `/core-engineering:ce-implement`.
- Small bounded fix: `/core-engineering:ce-patch`; it graduates to `/core-engineering:ce-plan` if the change proves structural.
- Existing code question: `/core-engineering:ce-ask` for one answer, `/core-engineering:ce-onboard` when a maintainer needs a paced walkthrough, or `/core-engineering:ce-domain` to learn the business domain the code encodes.
- Work-item refinement: `/core-engineering:ce-impact` for a grounded, file-cited blast-radius read before planning or estimating.
- Risk discovery: `/core-engineering:ce-probe-infra` for static manifests, `/core-engineering:ce-probe-deps` for known-vulnerable dependency pins, `/core-engineering:ce-probe-sec` for a live target, `/core-engineering:ce-probe-perf` for measured performance, `/core-engineering:ce-ux-audit` for adversarial UX exploration (plan-free) or a plan's traced-journey walk.
- Pre-implementation confidence: `/core-engineering:ce-plan-audit` for a written plan, then `/core-engineering:ce-review` and `/core-engineering:ce-verify` after implementation.

## The `product-discovery` plugin

The three upstream idea/market skills — `/product-discovery:ce-idea-scout`, `/product-discovery:ce-idea-score`, `/product-discovery:ce-market-scan` — ship as a small **companion plugin** in this same marketplace. They score *product* directions before any engineering starts, so they live one plugin over from the core engineering spine; install core alone and you never carry them, add this plugin when you want the discovery front-end.

```bash
claude plugin install product-discovery@vg-coding
```

**Moved, with stable skill identifiers.** These skills used to live in
`core-engineering`; their `ce-*` identifiers are unchanged, but direct calls
must use the owning plugin namespace: `/product-discovery:ce-idea-score`,
`/product-discovery:ce-idea-scout`, and `/product-discovery:ce-market-scan`.
The [Usage Matrix](./docs/USAGE-MATRIX.md) shows when to use each one and how
the selected direction flows into `/core-engineering:ce-brief`.

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
When an underlying skill reaches a human gate, the leaf returns a structured
`Needs decision` checkpoint to its parent and resumes only after the caller
supplies that decision; it never guesses approval.

## Repository Layout

```
plugins/
  core-engineering/              # primary plugin
    agents/                      # 2 Claude Code custom agents: spec-author · spec-impl
    skills/<name>/               # the workflows; SKILL.md + optional stage files + scripts/
    hooks/                       # lifecycle safety, egress, integrity, and model-attestation hooks
    model-policy.json            # machine-readable model-tier policy (validated by check.py)
  product-discovery/             # companion plugin: idea-scout · idea-score · market-scan
    skills/<name>/               # discovery workflows and their lint helpers
    model-policy.json            # companion plugin's model-tier policy
.claude-plugin/marketplace.json  # marketplace manifest — registers both plugins
action/
  merge-bar/                     # composite GitHub Action — the merge bar as a 3-line CI adoption
  test-integrity/                # composite GitHub Action — the standalone test-integrity gate (genie-catcher)
templates/
  adopter-ci/                    # checksum-pinned copy-in workflow for adopter repos (gates.yml)
scripts/                         # check.py · corpus_lint.py · portability_check.py · product_layer_check.py
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

Install the plugin as shown under [Install](#install). Model-invocable skills may
be selected automatically; every skill remains directly callable. The six
direct-only workflows are listed in the install section above.

Typical direct calls include `/core-engineering:ce-init`, `/core-engineering:ce-plan`, `/core-engineering:ce-spec`,
`/core-engineering:ce-implement`, `/core-engineering:ce-review`, `/core-engineering:ce-ask`, `/core-engineering:ce-probe-infra`, and
`/core-engineering:ce-ship-release`.
The plugin-shipped `spec-author` and `spec-impl` custom agents are available from
Claude Code's agent picker after installation.

### The merge bar in CI (any repo — no plugin required)

The same integrity gates also ship as an agent-agnostic, offline composite
GitHub Action. It judges every PR the same way, regardless of what wrote the
code. Adoption is three workflow lines:

```yaml
- uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
  with: { fetch-depth: 0 } # the diff gates need the base ref, not a shallow tip
- uses: relusion/vg-sdlc-claude-plugins/action/merge-bar@<PIN-ME-40-HEX-COMMIT-SHA>
```

Pin the full 40-hex commit SHA of the release commit you trust. The action
refuses movable refs, and that one pin fetches the runner, policy, and gate
scripts atomically.

A green verdict proves **integrity, not function**: traceability held, tests
were not weakened, and dependency changes were declared. It does not prove the
code compiles or its tests pass, so keep your own build/test job as a second
required check. See the [action guide](./action/merge-bar/README.md), the
[checksum-pinned copy-in template](./templates/adopter-ci/gates.yml), and the
[branch-protection guidance](./docs/TEAM-ROLLOUT.md).

Want only the **test-integrity** half without adopting specs or a merge policy?
Pin [`action/test-integrity`](./action/test-integrity/README.md) instead. It
flags deleted, emptied, skipped, assertion-free, or trivially true tests. It
does not run the suite, so keep your build/test job alongside it.

## Making It Yours

These are reference templates — they get better when you tune them to how your team works.

- **Add external connectors deliberately** — configure a repository-specific MCP server only when a workflow needs an external system, and give it the narrowest tools and credentials that workflow requires. The plugin does not ship a built-in MCP wrapper.
- **Add team context** — drop your terminology, processes, and standards into the skill files.
- **Adjust scope** — edit the skills to match how your team actually runs the workflow.
- **Add your own** — copy the structure for workflows we haven't covered.

## Contributing

Everything here is markdown, JSON, and a little Python. Fork, edit, PR — **[CONTRIBUTING.md](./CONTRIBUTING.md)** has the full validation battery, standards, and versioning rules. For new content:

- **New skill** → add it under the owning plugin at `plugins/<plugin>/skills/<name>/SKILL.md`, then update that plugin's model policy and the shared catalogs (skills are edited in place — there are no vendored copies to sync).
- **New plugin agent** → add a leaf custom agent under the owning plugin's `agents/` directory with `name`, `description`, and a scoped tool list; keep the skill as the source of truth.
- Before pushing, run the canonical [full validation battery](./CONTRIBUTING.md#the-validation-battery). The umbrella check parses manifests, verifies skill/agent frontmatter, guards registered forked-gate copies from drift, checks the README catalog, and runs the corpus, authoring, product, and supply-chain checks. The remaining commands cover docs drift, eval fixtures and dry runs, evidence projections, portability, unit tests, and official plugin validation. Executed evals require `--execute` plus an explicit `--max-budget-usd`; under-budget full scenarios fail fast unless `--allow-low-budget` is passed deliberately. Update **[docs/HOW-IT-WORKS.md](./docs/HOW-IT-WORKS.md)** and this README in the same change whenever you add, rename, or remove a skill, plugin agent, gate, control, product route, or artifact path.

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
