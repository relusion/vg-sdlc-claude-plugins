---
name: ce-go
description: |
  The front door — take a plain-language request ("why does export fail", "score this idea", "is the code good"), inspect repo state (a plan on disk? a spec for the named feature? a running target?), and route to the one right `/ce-*` skill with its reasoning shown first. Routes, never executes: it starts one model-invocable skill or returns the exact command for a direct-only skill, and writes nothing itself.
  Triggers: you know what you want but not which of the ~29 `/ce-*` skills runs it. ce-go picks; the routed skill does the work (and auto-detects any plan-existence mode itself, so you never have to).
argument-hint: "[what you want, in plain language]"
allowed-tools: Read, Glob, Grep, Bash, AskUserQuestion, Skill
---

# Go — front-door router

**Invocation input:** $ARGUMENTS

Choose one owning workflow from a plain-language request. Inspect only the
signals needed to disambiguate, explain the route briefly, and either invoke one
model-invocable skill or return one exact human-only command. Write nothing.

## Runtime Inputs

- A plain-language request; ask once only when it cannot be classified safely.
- The current repository, inspected read-only for the smallest routing signal.

## Resolve only decision-relevant state

Classify the request as question, symptom, change, discovery, review, probe, or
delivery. Ask one short question only when that classification would choose a
materially different route.

For a named plan/feature, inspect:

- `docs/plans/plans.json` and `docs/plans/<slug>/plan.json`;
- `features/<id>.md`, including `Specification route: compact|explicit`;
- `specs/<id>/` when deciding whether an implementation-ready spec exists;
- a named running target for dynamic probes;
- the architecture prerequisite before spec, implement, or auto-build.

For that prerequisite, run the plan's deterministic floor rather than
reproducing its schema in this router:

```bash
python3 "${CLAUDE_SKILL_DIR}/../ce-plan/scripts/plan-lint.py" \
  docs/plans/<slug> --json
```

- exit 1 or 2 routes to `/core-engineering:ce-plan` Stage R with the lint result;
- exit 0 plus either `required`/selected/converged or
  `recommended`/selected/converged and an lstat-confirmed absent
  `docs/plans/<slug>/architecture/` routes to
  `/core-engineering:ce-architecture <slug>`;
- otherwise continue to the requested downstream workflow and let that workflow
  validate any present architecture package as a consumer.

Never claim namespace presence means current. An unfinished architecture
publication transaction or ambiguous filesystem state routes to its recovery
owner rather than being treated as absence.

## Routing table

The table below is the single source of truth for where each request goes. It is
kept in lock-step with `docs/USAGE-MATRIX.md` by `check_front_door_parity()` in
`scripts/product_layer_check.py`: every `/ce-*` skill the matrix routes to
appears here, and vice versa (excluding `/core-engineering:ce-go` itself). Do not add prose routes
outside the markers — the parity lint reads only what is between them.

<!-- routing-table:start -->

**Understand / question (read-only, any repo)**

| The request is… | Route to | Because |
|---|---|---|
| a question about how existing code works, no change intended | `/core-engineering:ce-ask` | grounded, file-cited answer; writes nothing |
| "how big is this change / what does it touch" for a work item | `/core-engineering:ce-impact` | read-only blast-radius read with open questions |
| "teach me the system that was built" and a plan exists | `/core-engineering:ce-onboard` | paced, evidence-grounded walkthrough of the as-built code |
| "teach me the business domain this code serves" — actors, nouns, rules, vocabulary | `/core-engineering:ce-domain` | paced domain walkthrough with every claim typed; the unevidenced *why*s go to a known-unknowns register, never narrated |
| "which of these supplied options should we pick" for one bounded technical fork | `/core-engineering:ce-decide` | evidence-tagged engineering recommendation + proposed ADR |

**Something is broken**

| The request is… | Route to | Because |
|---|---|---|
| a **planned** feature misbehaving — a `docs/plans/<slug>/specs/<id>/` owns it | `/core-engineering:ce-debug` | planned mode: reproduces to a file:line cause and routes one fix against the spec |
| a component misbehaving with **no** plan/spec owning it | `/core-engineering:ce-debug` | plan-free mode: ranked root-cause hypotheses + a discrimination plan — `/core-engineering:ce-debug` auto-detects the mode, so route here either way |

**Build or change something**

| The request is… | Route to | Because |
|---|---|---|
| a genuinely small, bounded change with no reviewer-trigger surface | `/core-engineering:ce-patch` | conservative direct patch workflow; uncertainty routes to planning |
| a raw idea whose problem, users, scope, or outcome still need discovery | `/core-engineering:ce-brief` | optional intent brief with a bounded interview |
| a clear project/feature outcome to decompose | `/core-engineering:ce-plan` | adaptive repository-grounded planning; architecture only when load-bearing or explicitly requested |
| complete solution-architecture alternatives must be generated from requirements before planning | `/core-engineering:ce-plan` | it prepares the pre-decomposition frame and composes `/core-engineering:ce-architecture explore:<slug>` safely |
| a written plan fails its architecture disposition/direction lint, or says architecture is `required` but convergence is incomplete | `/core-engineering:ce-plan` | Stage R owns the plan correction before downstream work |
| a request would specify or implement a planned feature, or auto-build a whole plan, and that plan says architecture is selected + converged (`required` or `recommended`) but its `architecture` namespace is absent | `/core-engineering:ce-architecture` | publish the governed, current solution baseline before specification or implementation starts |
| a plan with a selected direction that needs system/runtime/deployment/data/integration views | `/core-engineering:ce-architecture` | plan-backed solution baseline with source hashes, traceability, gaps, and human approval |
| a planned feature marked `Specification route: explicit` to detail | `/core-engineering:ce-spec` | reviewed acceptance/design contract plus ordered `tasks.json` |
| a compact-route feature, or a feature with a linted spec, to build | `/core-engineering:ce-implement` | composes compact spec when allowed, then executes under Scope Lock |
| a whole plan to run unattended | `/core-engineering:ce-auto-build` | bounded sequential spec/implement/verify/review orchestration |
| a first run in a repo with no `repo-profile.json` | `/core-engineering:ce-init` | profiles commands/CI/surfaces, writes starter policy artifacts |

**Probe a risk surface**

| The request is… | Route to | Because |
|---|---|---|
| a **running** web/API/CLI security target is named | `/core-engineering:ce-probe-sec` | dynamic security probing under explicit consent |
| IaC / Kubernetes / Dockerfile / cloud manifests to audit statically | `/core-engineering:ce-probe-infra` | manifest-read + scanner-confirmed infra findings |
| pinned dependency versions to check for known CVEs | `/core-engineering:ce-probe-deps` | OSV-backed advisory findings per dependency |
| a **running** target to measure for latency/throughput | `/core-engineering:ce-probe-perf` | measured performance signals; records, does not block |

**Review / verify / audit**

| The request is… | Route to | Because |
|---|---|---|
| "does the implemented behavior actually work" across a plan | `/core-engineering:ce-verify` | whole-suite regression + journey + acceptance gate |
| "is this feature well written" | `/core-engineering:ce-review` | six-lens code review with adversarial verification |
| "a reviewer left these comments on my PR — are they right, how do I reply" (comments pasted) | `/core-engineering:ce-review` | auto-detects inbound mode: verifies each claim against the code, drafts paste-ready replies; posts nothing, patches nothing |
| "is the written plan sound" before building | `/core-engineering:ce-plan-audit` | structural lint + model-judged plan findings |
| "how did this plan's pipeline perform" | `/core-engineering:ce-retro` | descriptive metrics/process signals; mutates nothing |
| UX problems in a **running** app — walk a plan's **traced** journeys, or hunt unknown problems plan-free | `/core-engineering:ce-ux-audit` | auto-detects journey-walk (plan owns the surface) vs adversarial-discovery (no plan) mode itself |
| validate that a role can follow an existing doc / runbook / quickstart | `/core-engineering:ce-doc-audit` | ⌨ human-initiated — executes the doc's steps as a reader role in a sandbox; inline findings, not verdicts |

**Product direction** — these three ship in the companion **`product-discovery`** plugin (not `core-engineering`); if a route below fires and the skill is not installed, tell the user to `claude plugin install product-discovery@vg-coding`.

| The request is… | Route to | Because |
|---|---|---|
| "generate and rank many ideas" | `/product-discovery:ce-idea-scout` | a verdict-rendering funnel to a ranked shortlist (product-discovery plugin) |
| "score this one idea" | `/product-discovery:ce-idea-score` | seven-axis Pursue/Park/Drop verdict (product-discovery plugin) |
| "validate the market/competitors first" | `/product-discovery:ce-market-scan` | evidence-bound scan; frames, renders no go/no-go (product-discovery plugin) |

**Deliver / ship**

| The request is… | Route to | Because |
|---|---|---|
| "turn this spec into work items" | `/core-engineering:ce-ship-backlog` | paste-ready ADO items, one-way, no tracker writes |
| "decide release readiness / write the changelog" | `/core-engineering:ce-ship-release` | release decision package + changelog on consent |
| "generate the user-facing docs" | `/core-engineering:ce-ship-document` | docs grounded in verified behavior with run examples |
| "make this prose sound natural / less AI-generated" | `/core-engineering:ce-humanize` | rewrites tone of existing prose; preserves facts and markup; ephemeral, edits a named file only on consent |

<!-- routing-table:end -->

## Execution Contract

1. Pick exactly one row using the request and verified repository state.
2. Print one compact read-back:

   ```text
   Route: /<skill>
   Why: <request signal + repository evidence>
   Coverage gap: <none or exact ambiguity>
   ```

3. When the route is unambiguous and model-invocable, invoke it immediately
   through `Skill` with the user's request. A reversible routing choice does not
   need a consent gate.
4. For human-initiated skills—`ce-patch`, `ce-auto-build`, `ce-probe-sec`,
   `ce-probe-perf`, `ce-ship-release`, and `ce-doc-audit`—do not attempt model
   invocation. Return:

   ```text
   Run: /<namespace:skill> <request>
   ```

5. If a routed product-discovery skill is not installed, return its documented
   plugin-install command.
6. Never chain or fan out. The destination owns its gates and writes.

## Human-in-the-Loop — adaptive

Only a genuinely ambiguous fork opens:

```text
Gate 1 of 1 — Choose route
Evidence: <why two routes remain plausible>
```

Offer the two or three plausible routes with consequences, plus **Park**. Do not
offer irrelevant skills. Partial filesystem state, conflicting user intent, or
an unclassifiable mixed request is ambiguity; an ordinary clear route is not.

## Escalation

- No matching row → explain the coverage gap and route nowhere.
- Several independent tasks → route the first blocking task and name the later
  tasks without starting them.
- Deterministic plan lint unavailable/failing → Stage R, not a guessed
  downstream route.
- Missing or unsafe filesystem evidence → ask once or park.

## Honest Limitations

- This router validates routing prerequisites, not the destination's complete
  inputs.
- It writes nothing and performs no downstream work.
- It is one-hop routing, not pipeline orchestration.
