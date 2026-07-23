# Usage Matrix

Start with `/core-engineering:ce-go <goal>` when the route is unclear. It starts
an unambiguous model-invocable workflow; direct-only or ambiguous work returns
an exact next command or one discriminating question.

## Adopt In Three Tiers

| Tier | Default use |
|---|---|
| Core | Ask, impact, patch, adaptive plan, implement, independent review and verify |
| Controlled delivery | Explicit specification, load-bearing architecture, auto-build, probes, docs, final release |
| Specialists | Briefing, learning, audits, decisions, discovery, backlog export, prose work |

Tiering changes discoverability, not authority.

## Core route

| Need | Use | Boundary |
|---|---|---|
| Initialize repository policy | `/core-engineering:ce-init --write` | `--readiness` is read-only and does not attest Git-host controls |
| Answer one code question | `/core-engineering:ce-ask` | Cited and read-only |
| Refine a proposed change | `/core-engineering:ce-impact` | Blast radius and unknowns; no implementation |
| Make a small low-risk fix | `/core-engineering:ce-patch` | At most two files; uncertainty routes to plan |
| Plan repository-changing work | `/core-engineering:ce-plan` | Adaptive questions, one canonical plan shape, per-feature `compact|explicit` route |
| Build planned work | `/core-engineering:ce-implement` | Compact composes/lints spec artifacts; explicit requires ce-spec first |
| Review code quality and risk | `/core-engineering:ce-review` | Independent findings; no patch |
| Demonstrate behavior | `/core-engineering:ce-verify` | Independent evidence; no fix |
| Diagnose a failure | `/core-engineering:ce-debug` | Confirms or ranks cause and routes repair; no fix |

## Conditional planning and build capabilities

| Trigger | Use | Result |
|---|---|---|
| Product intent is genuinely thin or conflicted | `/core-engineering:ce-brief` | Optional planning-ready brief |
| Architecture changes the delivery shape | `/core-engineering:ce-plan` composes `/core-engineering:ce-architecture explore:<draft-slug>` and `shape:<draft-slug>` | Pre-decomposition architecture exploration/selection, evidence-rich question/adjust loop, then convergence |
| A written plan requires or deliberately chooses a shared baseline | `/core-engineering:ce-architecture <plan-slug>` | Human-approved, digest-bound architecture package |
| A feature has unresolved design or material decisions | `/core-engineering:ce-spec <feature-id>` | Canonical `ce-spec.md` and `tasks.json` |
| A whole bounded plan should run sequentially | `/core-engineering:ce-auto-build <plan-slug>` | Persisted status, bounded retries/parks/budget, human decisions returned to owner |

Detailed decomposition starts only after a required architecture direction is
selected. Straightforward work skips the architecture workbench. A required
missing or stale baseline blocks downstream work.
The load-bearing branch is pre-decomposition architecture exploration/selection;
it is not a default ceremony.

`compact` does not mean “no specification.” Implementation re-screens the
feature, runs the canonical specification stages, and requires `spec-lint`
before code. Complexity, security/privacy, public contracts, shared shapes,
cross-feature flow, architecture, or unresolved human judgment forces
`explicit`.

## Assurance and learning

| Need | Use | Result |
|---|---|---|
| Audit a plan without rewriting it | `/core-engineering:ce-plan-audit` | Structural and model findings |
| Walk planned or plan-free UX | `/core-engineering:ce-ux-audit` | Evidence-backed UX findings |
| Summarize process evidence | `/core-engineering:ce-retro` | Metrics and optional evidence pack; not attestation |
| Teach the implemented system | `/core-engineering:ce-onboard` | Cited technical walkthrough |
| Teach the encoded business domain | `/core-engineering:ce-domain` | Actors, nouns, lifecycles, rules, known unknowns |
| Compare one bounded technical fork | `/core-engineering:ce-decide` | Evidence-tagged proposed ADR; no architecture substitution |

## Risk probes

| Surface | Use | Boundary |
|---|---|---|
| Dynamic security | `/core-engineering:ce-probe-sec` | Explicit target/consent; not a pentest |
| Runtime performance | `/core-engineering:ce-probe-perf` | Measured observation; not a capacity guarantee |
| IaC and deployment manifests | `/core-engineering:ce-probe-infra` | Static findings; read-only |
| Pinned dependency advisories | `/core-engineering:ce-probe-deps` | SCA evidence; loud offline degradation |

## Documentation and final handoff

| Need | Use | Order and authority |
|---|---|---|
| Export plan/spec work items | `/core-engineering:ce-ship-backlog` | Generates importable output; no tracker writes |
| Generate user/operator docs | `/core-engineering:ce-ship-document` | Ground in verified behavior and runnable examples |
| Test an existing doc as a reader | `/core-engineering:ce-doc-audit` | Conditional before release for runbooks, migrations, safety procedures, and high-impact journeys; findings only |
| Improve prose tone | `/core-engineering:ce-humanize` | Preserves facts/markup; does not generate product docs |
| Make the final readiness decision | `/core-engineering:ce-ship-release` | Last workflow after required docs/audit evidence; GO/NO-GO package, never deploy |

Review and verification can be orchestrated together but remain independent
evidence producers. A demonstrated PASS or clean negative is reported without
re-attestation. Failure, uncertainty, target ambiguity, stakeholder acceptance,
or a material manual judgment creates the decision route.

## Optional product discovery plugin

| Need | Use |
|---|---|
| Generate and rank ideas | `/product-discovery:ce-idea-scout` |
| Score one idea | `/product-discovery:ce-idea-score` |
| Research market context | `/product-discovery:ce-market-scan` |

Install `product-discovery` only for these upstream jobs.

## Default Routes

- Small fix: patch.
- Planned change: adaptive plan → compact implementation or explicit spec →
  implementation → independent review and verify.
- Load-bearing design: plan → iterative architecture selection → decomposition
  and shape → baseline when required → build.
- Final handoff: review and verify → generate docs → conditional doc audit →
  release decision.
- Unattended: plan audit → auto-build; inspect `STATUS.md`, use `--resume` only
  to continue deliberately.

See [Workflow Recipes](WORKFLOW-RECIPES.md) for commands, expected artifacts,
and stop conditions.
