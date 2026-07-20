# Usage Matrix

Use this as the quick router for `core-engineering`. The detailed architecture is
in `docs/HOW-IT-WORKS.md`; this page answers "which skill do I run now?"
Use `docs/GETTING-STARTED.md` for a first session,
`docs/WORKFLOW-RECIPES.md` for end-to-end operating paths, and
`docs/README.md` for the complete documentation index.

## Starting Points

| I want to... | Use | Why |
|---|---|---|
| Not sure which skill runs this | `/ce-go <what you want>` | The front door: inspects repo state (plan on disk? spec for the feature? running target?) and routes to the one right skill, showing its reasoning before it hands off. Routes, never executes. |
| Bootstrap this framework in a repo | `/ce-init --write` | Profiles commands, package managers, CI, risk surfaces, and writes starter `docs/plans/` policy artifacts. |
| Shape a raw idea before planning | `/ce-brief` | Elicits intent through selected persona lenses and writes a planning-ready brief. |
| Validate market context before investing planning time | `/ce-market-scan` *(product-discovery plugin)* | Produces sourced market and competitor findings without rendering a go/no-go verdict. |
| Score one product idea | `/ce-idea-score` *(product-discovery plugin)* | Renders an opinionated, evidence-tagged Pursue / Park / Drop style verdict. |
| Generate and rank many ideas | `/ce-idea-scout` *(product-discovery plugin)* | Creates a shortlist, cuts weak candidates with reasons, then deep-scores survivors. |
| Decompose a real feature/project | `/ce-plan` | Owns scope, feature boundaries, ship order, reachability, and plan artifacts. |
| Make one genuinely small change | `/ce-patch` | Uses a ≤ 2-file express lane with one approval gate and one ledger line. Any failed or uncertain admission check routes to `/ce-plan`; patch never expands into a larger lane. |

## Build Path

| I have... | Use | Output |
|---|---|---|
| A written plan and one feature to detail | `/ce-spec <feature-id>` | `ce-spec.md` + `tasks.json` with acceptance criteria and traceability. |
| An approved spec and task list | `/ce-implement <feature-id>` | Code/tests updated, tasks marked done, `verification.md` written. |
| A whole plan to run unattended | `/ce-auto-build <plan-slug>` | Per-feature spec/implement runs, gates, status board, and end-review package. |
| A plan on disk and a need to see where it stands | `python3 plugins/core-engineering/skills/ce-auto-build/scripts/status-board.py docs/plans/<slug>` | Disk-derived status board with a `Next:` route per feature; degrades loudly without `plan.json` (Recipe 19 in `docs/WORKFLOW-RECIPES.md`). |
| A sprint to plan from an existing plan | `status-board.py` + `plan.json` ship order/complexity, then `/ce-ship-backlog <feature-id>` | Selects the next slate in dependency order and sizes it against the plan's own Final Complexity; `/ce-plan-audit` first, so a sprint is never planned on a plan that does not lint (Recipe 33). |
| An auto-build run that stopped, or one to supervise | `/ce-auto-build <plan-slug> --resume` | Disk-validated resume of a halted run; watch `docs/plans/<slug>/STATUS.md` between features (Recipe 20 in `docs/WORKFLOW-RECIPES.md`). |
| A built feature that may be wrong | `/ce-debug <feature-id or failure>` | Reproduced cause, classification, and routed fix path (planned mode — a spec owns the feature); no patches. |

## Review And Verify

| Question | Use | Boundary |
|---|---|---|
| Does the implemented behavior work? | `/ce-verify <plan-slug>` | Runs behavior, journey, dependency, and acceptance checks; does not fix. |
| Is the code well written? | `/ce-review <feature-id>` | Reviews correctness, security, performance, maintainability, conformance, and simplicity; does not patch. |
| A reviewer commented on my PR — are they right, and how do I answer? | `/ce-review` (paste the comments, or `--comments <file>`) | Inbound mode, auto-detected from the payload: verifies each comment as a *claimed* finding (substantiated / refuted / unverifiable), drafts paste-ready replies, routes accepted fixes. Posts to no forge, edits no code, writes nothing. |
| Is the written plan sound? | `/ce-plan-audit <plan-slug>` | Lints plan structure and reports model-judged findings; does not re-plan. |
| How did the pipeline perform? | `/ce-retro <plan-slug>` | Reads metrics and artifacts for descriptive process signals; mutates nothing by default. |
| Produce an audit / evidence pack for a plan | `/ce-retro <plan-slug>` export mode (or `/ce-ship-release <plan-slug>` per release) | Compiles one dated, sha256-stamped bundle of the pipeline's recorded evidence (guard log, metrics, gate verdicts, attestations, model identity) under `evidence-pack/<date>/`; compilation, not a compliance attestation. |
| UX in the running app — planned journeys or plan-free discovery? | `/ce-ux-audit [plan-slug \| scope]` | Walk planned journeys, or adversarially probe plan-free; auto-detected from plan state. Reports evidence-backed UX findings; no fixes. |

## Discovery On Any Repo

| I need to... | Use | Notes |
|---|---|---|
| Ask how existing code works | `/ce-ask <question>` | Read-only, file-cited answer; writes nothing. |
| Estimate blast radius of a proposed change | `/ce-impact <change text>` | Read-only impact summary with file citations and open questions. |
| Teach a maintainer the built system | `/ce-onboard <plan/path>` | Guided walkthrough with citations and optional internal learning guide. |
| Learn the business domain a codebase encodes | `/ce-domain [path]` | Guided walkthrough of actors, nouns, lifecycles, rules, and vocabulary — every claim typed recorded/enforced/inferred; the unevidenced *why*s go to a known-unknowns register for a human, never narrated. |
| Capture what a departing owner knows, before they go | `/ce-ask` per claim, then an ADR backfill in `docs/adr/` | The inverse of `/ce-onboard`: the human teaches, and every claim is verified to `file:line`, marked CONTRADICTED, or recorded as unverified lore — never enshrined unchecked (Recipe 34). |
| Split an epic along real seams | `/ce-impact` → `/ce-brief` → `/ce-plan` | `/ce-impact` names the seams and the open questions; `/ce-plan` owns the cut, because it owns the sizing, dependency, and reachability gates (Recipe 2). |
| Investigate a misbehaving component with no plan/spec | `/ce-debug <component> <symptom>` | Ranked hypotheses plus discrimination plan (plan-free mode — auto-detected); no fixes. |
| Choose among technical options | `/ce-decide <decision + options>` | Evidence-tagged engineering recommendation plus proposed ADR. |

## Probes

| Surface | Use | What It Proves |
|---|---|---|
| Running web/API/CLI security | `/ce-probe-sec <target>` | Dynamic security findings under explicit consent; not a pentest. |
| Static IaC / Kubernetes / Dockerfile | `/ce-probe-infra [path]` | Manifest-read and scanner-confirmed infra findings; read-only. |
| Known-vulnerable dependency versions (SCA) | `/ce-probe-deps [path]` | OSV-backed advisory findings per pinned dependency; read-only, loud offline degradation. |
| Runtime performance | `/ce-probe-perf <target>` | Measured latency/throughput/resource signals; records, does not block. |

## Delivery

| I want to... | Use | Boundary |
|---|---|---|
| Convert a spec to ADO / Jira / GitHub work items | `/ce-ship-backlog <feature-id> [--format ado-md\|ado-csv\|jira-csv\|gh-jsonl]` | Paste-ready or bulk-import output, one-way; no tracker API writes. |
| Decide release readiness and changelog | `/ce-ship-release <plan-slug>` | Writes release decision package and changelog on consent; never deploys. |
| Generate user-facing docs | `/ce-ship-document <plan-slug>` | Grounds docs in verified behavior and runnable examples. |
| Rewrite AI-sounding or generic prose to read naturally | `/ce-humanize <text or file>` | Preserves meaning, facts, and markup; ephemeral by default, edits a named file only on consent. Rewrites tone; does not generate docs (use `/ce-ship-document`). |
| Validate that a reader role can follow an existing doc / runbook / quickstart | `/ce-doc-audit <doc> [--role <name>]` | Impersonates the role, executes steps in a sandbox, reports inline findings; never edits the doc. Validates existing docs (use `/ce-ship-document` to generate them). |

## Default Routes

This is the canonical route list — `README.md` and the other guides link here
rather than duplicating it.

- First run in a repo: `/ce-init --write`, then `/ce-ask` or `/ce-impact`.
- New feature: `/ce-brief` -> `/ce-plan` -> (`/ce-plan-audit`) -> `/ce-spec` -> `/ce-implement` -> `/ce-review` + `/ce-verify`.
- Small fix: `/ce-patch` for a ≤ 2-file change (one gate, one ledger line, no spec artifacts); use `/ce-plan` when admission fails or scope is uncertain.
- Unattended: `/ce-plan-audit` -> `/ce-auto-build` -> `/ce-onboard` -> `/ce-retro`.
- Pre-release: `/ce-probe-deps` + `/ce-probe-infra` (add `/ce-probe-sec` / `/ce-probe-perf` / `/ce-ux-audit` with a running target) -> `/ce-ship-release` -> `/ce-ship-document`.
- Production-style handoff: `/ce-verify` -> `/ce-review` -> `/ce-ship-release` -> `/ce-ship-document`.
- Unknown failure or a misbehaving component: `/ce-debug` — it auto-detects planned (a spec owns the feature) vs plan-free mode from plan state; you need not know which.
