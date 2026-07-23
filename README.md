# vg-coding

> Repository-aware SDLC workflows for Claude Code, plus an agent-agnostic merge
> bar for every pull request.

The plugin turns repository evidence into reviewable plans, code, checks,
documentation, and a final release decision. It does not merge, deploy, publish,
rotate credentials, or accept product and security risk for a human.

The offline merge bar is separate from the model workflows. It runs deterministic
checks over committed state using
[`plugins/core-engineering/merge-policy.json`](./plugins/core-engineering/merge-policy.json)
and emits a SHA-anchored verdict. Claude Code is not required. See
[`action/merge-bar`](./action/merge-bar/README.md).

## Install

```bash
claude plugin marketplace add relusion/vg-sdlc-claude-plugins
claude plugin install core-engineering@vg-coding
```

If you do not know the command, start with:

```text
/core-engineering:ce-go <what you want to accomplish>
```

`ce-go` inspects repository state and starts an unambiguous model-invocable
workflow. For a direct-only or ambiguous destination it returns the exact next
command or asks one discriminating question.

## Week one

Start with the smallest workflow that solves the job:

| Outcome | Command |
|---|---|
| Understand the repository | `/core-engineering:ce-ask` |
| Refine a change before committing to it | `/core-engineering:ce-impact` |
| Make a genuinely small, low-risk fix | `/core-engineering:ce-patch` |
| Plan repository-changing work | `/core-engineering:ce-plan` |
| Build planned work | `/core-engineering:ce-implement` |
| Review and verify independently | `/core-engineering:ce-review` + `/core-engineering:ce-verify` |

`/core-engineering:ce-brief` is an optional specialist for a genuinely unclear
product request, not a required prelude to planning.

## The lean delivery path

The path adapts to evidence:

```text
[optional brief] → adaptive plan
  ├─ straightforward: plan directly
  └─ load-bearing architecture:
       plan [architecture explore + human direction] → decompose ⇄ architecture shape
       questions / evidence inspection / adjustment loop at the same human gate
       → governed baseline only when the plan requires it
→ specification route recorded by plan
  ├─ compact: implement composes + lints the canonical spec artifacts
  └─ explicit: ce-spec resolves non-build-ready decisions first
→ implement
→ review ∥ verify                 # independent evidence, one orchestrated handoff
→ generate docs from verified behavior
→ audit docs when reader risk warrants it
→ incorporate doc changes, then refresh review ∥ verify
→ release decision               # ce-ship-release is final; never deploys
```

Architecture is not a ceremony for every feature. When it is load-bearing,
`ce-architecture explore:` maintains an evidence-rich comparison of complete
options. The human may inspect evidence, ask questions, adjust the frame or an
option, select, or park; the workflow recomputes at the same gate and binds only
the final selected snapshot.

Plan always writes the same canonical plan-directory shape. It records whether
each feature is `compact` or `explicit`. Compact work still produces and lints
`ce-spec.md` and `tasks.json`; implementation composes them before editing.
Security/privacy, public contracts, cross-feature flows, architecture decisions,
or unresolved material judgment force the explicit route.

Review and verification remain independent: review judges code and risk;
verification demonstrates behavior and acceptance criteria. Demonstrated PASS
rows do not ask for human confirmation. Failures, uncertainty, and material
manual judgments route to the appropriate owner. Documentation or audit changes
become part of the candidate commit; review and verification are refreshed
before release so their receipts bind that exact state.

## Capability catalog

`core-engineering` ships **29 skills** and **2 plugin-shipped custom agents**.
The optional discovery plugin adds three skills.

<!-- skill-catalog:start -->
| Family | Skills | Job |
|---|---|---|
| Front door and setup | `/core-engineering:ce-go`, `/core-engineering:ce-init` | Route intent; profile and initialize repository policy. |
| Read and frame | `/core-engineering:ce-ask`, `/core-engineering:ce-impact`, `/core-engineering:ce-brief` | Answer, assess blast radius, or clarify a genuinely thin request. |
| Plan and build | `/core-engineering:ce-plan`, `/core-engineering:ce-architecture`, `/core-engineering:ce-spec`, `/core-engineering:ce-implement`, `/core-engineering:ce-patch`, `/core-engineering:ce-auto-build` | Use the adaptive spine, a bounded express lane, or explicit orchestration. |
| Assure and diagnose | `/core-engineering:ce-review`, `/core-engineering:ce-verify`, `/core-engineering:ce-debug`, `/core-engineering:ce-ux-audit`, `/core-engineering:ce-plan-audit`, `/core-engineering:ce-retro` | Produce independent findings, behavioral evidence, diagnosis, and process evidence. |
| Learn and decide | `/core-engineering:ce-onboard`, `/core-engineering:ce-domain`, `/core-engineering:ce-decide` | Teach implementation/domain context or compare one bounded technical fork. |
| Probe | `/core-engineering:ce-probe-sec`, `/core-engineering:ce-probe-perf`, `/core-engineering:ce-probe-infra`, `/core-engineering:ce-probe-deps` | Inspect a named security, performance, infrastructure, or dependency surface. |
| Handoff | `/core-engineering:ce-ship-backlog`, `/core-engineering:ce-ship-document`, `/core-engineering:ce-doc-audit`, `/core-engineering:ce-humanize`, `/core-engineering:ce-ship-release` | Export work, create and optionally audit docs, improve prose, then make the final release decision. |
| Optional product discovery | `/product-discovery:ce-idea-scout`, `/product-discovery:ce-idea-score`, `/product-discovery:ce-market-scan` | Generate, score, and research product directions before engineering planning. |
<!-- skill-catalog:end -->

Install discovery only when that job exists:

```bash
claude plugin install product-discovery@vg-coding
```

The custom agents are bounded leaf workers:

| Agent | Responsibility |
|---|---|
| `spec-author` | Run plan/spec authoring contracts and return real decisions to the caller. |
| `spec-impl` | Implement an approved or compact-routed feature test-first. |

They do not gain push, merge, deployment, or nested-agent authority.

## Human authority

Only actual decisions are gates. Deterministic PASS, read-only work, generated
projections, and clean negative results are reported and continue without
re-attestation. Deterministic failure stops or routes; a dialog cannot relabel it
PASS.

Product scope, material architecture, security acceptance, destructive actions,
contract breaks, accepted risk, and release remain human-owned. A material gate
shows evidence, alternatives, consequences, unknowns, recommendation, required
owner, and a gather-evidence/route/park path.

Hooks add cooperative backstops for write scope, recognized shared-history
commands, secret reads, outbound network calls, and installed-hook integrity.
They are not an OS sandbox. CI and branch protection remain separate controls.

## Evidence and adoption

The deterministic repository suite is extensive; current live-model evidence is
not. All current behavior scenarios are design-verified until fresh receipts are
recorded. A successful CI run that skipped model execution is explicitly not
behavioral evidence. See [Benchmarks](./docs/BENCHMARKS.md).

Use these documents:

- [Documentation index](./docs/README.md)
- [Getting Started](./docs/GETTING-STARTED.md)
- [Usage Matrix](./docs/USAGE-MATRIX.md)
- [Workflow Recipes](./docs/WORKFLOW-RECIPES.md)
- [How It Works](./docs/HOW-IT-WORKS.md)
- [Real Outputs](./docs/EXAMPLES.md)
- [Comparison](./docs/COMPARISON.md)
- [Team Rollout](./docs/TEAM-ROLLOUT.md)
- [Contributing](./CONTRIBUTING.md)

Before broad rollout, measure prompt/context proxy, human review time, first-pass
verification, review rework, park/retry/could-not-run rates, and repeat use among
eligible developers. Invocation count alone is not value.

## Merge bar

The GitHub composite action is pinned by full commit SHA:

```yaml
- uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
  with: { fetch-depth: 0 }
- uses: relusion/vg-sdlc-claude-plugins/action/merge-bar@<40-HEX-COMMIT-SHA>
```

Require it alongside the repository's own build/test jobs and protected human
review. The verdict proves only the configured integrity checks; it does not
prove the product works or is secure.

## Development

The canonical validation battery is documented in
[Contributing](./CONTRIBUTING.md). Public workflow behavior belongs in
[How It Works](./docs/HOW-IT-WORKS.md); routing belongs in the
[Usage Matrix](./docs/USAGE-MATRIX.md).

Licensed under [Apache-2.0](./LICENSE). See
[third-party notices](./THIRD_PARTY_NOTICES.md), [security policy](./SECURITY.md),
and the [commercial boundary](./COMMERCIAL.md).
