# Usage Matrix

Use this as the quick router for `core-engineering`. The detailed architecture is
in `docs/HOW-IT-WORKS.md`; this page answers "which skill do I run now?"
Use `docs/GETTING-STARTED.md` for a first session,
`docs/WORKFLOW-RECIPES.md` for end-to-end operating paths, and
`docs/README.md` for the complete documentation index.

## Adopt In Three Tiers

The tiers are an adoption order, not a reliability rating. Start with the
smallest workflow that solves the developer's job; add autonomy or specialist
probes only when the repository has their inputs, owners, and review path.

| Tier | Capabilities | Adopt when |
|---|---|---|
| **Core developer path** | `/core-engineering:ce-go`, `/core-engineering:ce-init`, `/core-engineering:ce-ask`, `/core-engineering:ce-impact`, `/core-engineering:ce-patch`, `/core-engineering:ce-plan`, `/core-engineering:ce-spec`, `/core-engineering:ce-implement`, `/core-engineering:ce-review`, `/core-engineering:ce-verify`, `/core-engineering:ce-debug` | Default for individual developers. Run `/core-engineering:ce-init --readiness` to expose missing local prerequisites without claiming host controls are enabled. |
| **Advanced delivery controls** | `/core-engineering:ce-brief`, `/core-engineering:ce-architecture`, `/core-engineering:ce-plan-audit`, `/core-engineering:ce-auto-build`, `/core-engineering:ce-ux-audit`, the four `ce-probe-*` skills, `/core-engineering:ce-retro`, `/core-engineering:ce-ship-release`, `/core-engineering:ce-ship-document` | The team has stable test/CI commands, named reviewers, bounded targets, and a quality/release owner. Direct-only and consent gates still apply. |
| **Optional specialist workflows** | `product-discovery`, `/core-engineering:ce-domain`, `/core-engineering:ce-onboard`, `/core-engineering:ce-decide`, `/core-engineering:ce-ship-backlog`, `/core-engineering:ce-humanize`, `/core-engineering:ce-doc-audit` | A specific discovery, learning, decision, tracker-export, prose, or documentation-validation job exists. Install or invoke only that capability. |

Tiering changes discoverability, not authority: no tier can merge, deploy, accept
security risk, or convert missing evidence into approval.

## Starting Points

| I want to... | Use | Why |
|---|---|---|
| Not sure which skill runs this | `/core-engineering:ce-go <what you want>` | The front door: inspects repo state, proposes one route, then starts a model-invocable skill or returns the exact direct-only command. Routes, never executes. |
| Bootstrap this framework in a repo | `/core-engineering:ce-init --write` | Profiles commands, package managers, CI, risk surfaces, and writes starter `docs/plans/` policy artifacts. Add `--readiness` for an explicit local-vs-host adoption gap report. |
| Shape a raw idea before planning | `/core-engineering:ce-brief` | Elicits intent through selected persona lenses and writes a planning-ready brief. |
| Validate market context before investing planning time | `/product-discovery:ce-market-scan` *(product-discovery plugin)* | Produces sourced market and competitor findings without rendering a go/no-go verdict. |
| Score one product idea | `/product-discovery:ce-idea-score` *(product-discovery plugin)* | Renders an opinionated, evidence-tagged Pursue / Park / Drop style verdict. |
| Generate and rank many ideas | `/product-discovery:ce-idea-scout` *(product-discovery plugin)* | Creates a shortlist, cuts weak candidates with reasons, then deep-scores survivors. |
| Decompose a real feature/project | `/core-engineering:ce-plan` | Owns scope, feature boundaries, ship order, reachability, and plan artifacts. |
| Establish the cross-feature solution architecture for a written plan | `/core-engineering:ce-architecture <plan-slug>` | Projects the frozen plan and repository evidence into human-approved system, deployment, data/integration, and quality views. It does not decompose the request or replace feature specs. |
| Make one genuinely small change | `/core-engineering:ce-patch` | Uses a ≤ 2-file express lane with one approval gate and one ledger line. Any failed or uncertain admission check routes to `/core-engineering:ce-plan`; patch never expands into a larger lane. |

## Build Path

| I have... | Use | Output |
|---|---|---|
| A written plan and one feature to detail | `/core-engineering:ce-spec <feature-id>` | `ce-spec.md` + `tasks.json` with acceptance criteria and traceability. |
| A written multi-feature plan that needs a shared design baseline | `/core-engineering:ce-architecture <plan-slug>` | Five-file package under `docs/plans/<slug>/architecture/`, structurally linted and written only after final human approval. |
| An approved spec and task list | `/core-engineering:ce-implement <feature-id>` | Code/tests updated, tasks marked done, `verification.md` written. |
| A whole plan to run unattended | `/core-engineering:ce-auto-build <plan-slug>` | Per-feature spec/implement runs, gates, status board, and end-review package. |
| A plan on disk and a need to see where it stands | Open `docs/plans/<slug>/STATUS.md`; use `/core-engineering:ce-auto-build <slug> --resume` only when you intend to continue a halted run | Last generated status plus a deliberate continuation route; inspect plan/spec artifacts directly if the projection is stale (Recipe 19). |
| A sprint to plan from an existing plan | Read `STATUS.md` + `plan.json` ship order/complexity, then `/core-engineering:ce-ship-backlog <feature-id>` | Selects the next slate in dependency order and sizes it against the plan's own Final Complexity; `/core-engineering:ce-plan-audit` first (Recipe 33). |
| An auto-build run that stopped, or one to supervise | `/core-engineering:ce-auto-build <plan-slug> --resume` | Disk-validated resume of a halted run; watch `docs/plans/<slug>/STATUS.md` between features (Recipe 20 in `docs/WORKFLOW-RECIPES.md`). |
| A built feature that may be wrong | `/core-engineering:ce-debug <feature-id or failure>` | Reproduced cause, classification, and routed fix path (planned mode — a spec owns the feature); no patches. |

## Review And Verify

| Question | Use | Boundary |
|---|---|---|
| Does the implemented behavior work? | `/core-engineering:ce-verify <plan-slug>` | Runs behavior, journey, dependency, and acceptance checks; does not fix. |
| Is the code well written? | `/core-engineering:ce-review <feature-id>` | Reviews correctness, security, performance, maintainability, conformance, and simplicity; does not patch. |
| A reviewer commented on my PR — are they right, and how do I answer? | `/core-engineering:ce-review` (paste the comments, or `--comments <file>`) | Inbound mode, auto-detected from the payload: verifies each comment as a *claimed* finding (substantiated / refuted / unverifiable), drafts paste-ready replies, routes accepted fixes. Posts to no forge, edits no code, writes nothing. |
| Is the written plan sound? | `/core-engineering:ce-plan-audit <plan-slug>` | Lints plan structure and reports model-judged findings; does not re-plan. |
| How did the pipeline perform? | `/core-engineering:ce-retro <plan-slug>` | Reads metrics and artifacts for descriptive process signals; mutates nothing by default. |
| Produce an audit / evidence pack for a plan | `/core-engineering:ce-retro <plan-slug>` export mode (or `/core-engineering:ce-ship-release <plan-slug>` per release) | Compiles one dated, sha256-stamped bundle of the pipeline's recorded evidence (guard log, metrics, gate verdicts, attestations, model identity) under `evidence-pack/<date>/`; compilation, not a compliance attestation. |
| UX in the running app — planned journeys or plan-free discovery? | `/core-engineering:ce-ux-audit [plan-slug \| scope]` | Walk planned journeys, or adversarially probe plan-free; auto-detected from plan state. Reports evidence-backed UX findings; no fixes. |

## Discovery On Any Repo

| I need to... | Use | Notes |
|---|---|---|
| Ask how existing code works | `/core-engineering:ce-ask <question>` | Read-only, file-cited answer; writes nothing. |
| Estimate blast radius of a proposed change | `/core-engineering:ce-impact <change text>` | Read-only impact summary with file citations and open questions. |
| Teach a maintainer the built system | `/core-engineering:ce-onboard <plan/path>` | Guided walkthrough with citations and optional internal learning guide. |
| Learn the business domain a codebase encodes | `/core-engineering:ce-domain [path]` | Guided walkthrough of actors, nouns, lifecycles, rules, and vocabulary — every claim typed recorded/enforced/inferred; the unevidenced *why*s go to a known-unknowns register for a human, never narrated. |
| Capture what a departing owner knows, before they go | `/core-engineering:ce-ask` per claim, then an ADR backfill in `docs/adr/` | The inverse of `/core-engineering:ce-onboard`: the human teaches, and every claim is verified to `file:line`, marked CONTRADICTED, or recorded as unverified lore — never enshrined unchecked (Recipe 34). |
| Split an epic along real seams | `/core-engineering:ce-impact` → `/core-engineering:ce-brief` → `/core-engineering:ce-plan` | `/core-engineering:ce-impact` names the seams and the open questions; `/core-engineering:ce-plan` owns the cut, because it owns the sizing, dependency, and reachability gates (Recipe 2). |
| Investigate a misbehaving component with no plan/spec | `/core-engineering:ce-debug <component> <symptom>` | Ranked hypotheses plus discrimination plan (plan-free mode — auto-detected); no fixes. |
| Choose among technical options | `/core-engineering:ce-decide <decision + options>` | Scores one consequential option set and drafts a proposed ADR. Use `/core-engineering:ce-architecture` for the whole cross-feature solution baseline. |

## Probes

| Surface | Use | What It Proves |
|---|---|---|
| Running web/API/CLI security | `/core-engineering:ce-probe-sec <target>` | Dynamic security findings under explicit consent; not a pentest. |
| Static IaC / Kubernetes / Dockerfile | `/core-engineering:ce-probe-infra [path]` | Manifest-read and scanner-confirmed infra findings; read-only. |
| Known-vulnerable dependency versions (SCA) | `/core-engineering:ce-probe-deps [path]` | OSV-backed advisory findings per pinned dependency; read-only, loud offline degradation. |
| Runtime performance | `/core-engineering:ce-probe-perf <target>` | Measured latency/throughput/resource signals; records, does not block. |

## Delivery

| I want to... | Use | Boundary |
|---|---|---|
| Convert a spec to ADO / Jira / GitHub work items | `/core-engineering:ce-ship-backlog <feature-id> [--format ado-md\|ado-csv\|jira-csv\|gh-jsonl]` | Paste-ready or bulk-import output, one-way; no tracker API writes. |
| Decide release readiness and changelog | `/core-engineering:ce-ship-release <plan-slug>` | Writes release decision package and changelog on consent; never deploys. |
| Generate user-facing docs | `/core-engineering:ce-ship-document <plan-slug>` | Grounds docs in verified behavior and runnable examples. |
| Rewrite AI-sounding or generic prose to read naturally | `/core-engineering:ce-humanize <text or file>` | Preserves meaning, facts, and markup; ephemeral by default, edits a named file only on consent. Rewrites tone; does not generate docs (use `/core-engineering:ce-ship-document`). |
| Validate that a reader role can follow an existing doc / runbook / quickstart | `/core-engineering:ce-doc-audit <doc> [--role <name>]` | Impersonates the role, executes steps in a sandbox, reports inline findings; never edits the doc. Validates existing docs (use `/core-engineering:ce-ship-document` to generate them). |

## Default Routes

This is the canonical route list — `README.md` and the other guides link here
rather than duplicating it.

- First run in a repo: `/core-engineering:ce-init --write`, then `/core-engineering:ce-ask` or `/core-engineering:ce-impact`.
- New feature: `/core-engineering:ce-brief` -> `/core-engineering:ce-plan` -> (`/core-engineering:ce-plan-audit`) -> optionally `/core-engineering:ce-architecture` for a multi-feature solution baseline -> `/core-engineering:ce-spec` -> `/core-engineering:ce-implement` -> `/core-engineering:ce-review` + `/core-engineering:ce-verify`.
- Small fix: `/core-engineering:ce-patch` for a ≤ 2-file change (one gate, one ledger line, no spec artifacts); use `/core-engineering:ce-plan` when admission fails or scope is uncertain.
- Unattended: `/core-engineering:ce-plan-audit` -> `/core-engineering:ce-auto-build` -> `/core-engineering:ce-onboard` -> `/core-engineering:ce-retro`.
- Pre-release: `/core-engineering:ce-probe-deps` + `/core-engineering:ce-probe-infra` (add `/core-engineering:ce-probe-sec` / `/core-engineering:ce-probe-perf` / `/core-engineering:ce-ux-audit` with a running target) -> `/core-engineering:ce-ship-release` -> `/core-engineering:ce-ship-document`.
- Production-style handoff: `/core-engineering:ce-verify` -> `/core-engineering:ce-review` -> `/core-engineering:ce-ship-release` -> `/core-engineering:ce-ship-document`.
- Unknown failure or a misbehaving component: `/core-engineering:ce-debug` — it auto-detects planned (a spec owns the feature) vs plan-free mode from plan state; you need not know which.
