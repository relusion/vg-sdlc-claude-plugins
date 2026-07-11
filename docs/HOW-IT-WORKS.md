# How `core-engineering` Works

`core-engineering` is a Claude Code plugin for planning, implementing, and
checking software changes through repository-resident artifacts. It contains
**29 skills** and **2 plugin-shipped custom agents**. A separate
`product-discovery` plugin adds three optional idea and market-research skills.

The Claude Code plugin is the primary runtime. The repository also contains an
agent-independent merge bar that runs in CI without Claude Code, plus
experimental Managed Agent cookbooks. The cookbooks do not load the plugin's
hooks; their host must supply sandboxing, permissions, approvals, and state
management. See the
[Managed Agent orchestration guide](../managed-agent-cookbooks/ORCHESTRATION.md)
before using that surface.

For installation and a first session, start with
[Getting Started](GETTING-STARTED.md). For command selection, use the
[Usage Matrix](USAGE-MATRIX.md). This page explains the architecture and the
boundaries that apply across the whole framework.

## 1. The operating model

The main workflow is a spine in which each stage produces a durable input for
the next stage:

```text
/ce-brief -> /ce-plan -> /ce-spec -> /ce-implement
                                |-> /ce-verify   behavior and acceptance proof
                                |-> /ce-review   code-quality findings
                                `-> /ce-debug    cause analysis and fix routing

/ce-auto-build  orchestrates the planned spine across multiple features
/ce-patch       folds the spine into one bounded small-change workflow
/ce-ux-audit    checks a running product, with or without a plan

delivery tail: /ce-ship-deliver -> /ce-ship-release -> /ce-ship-document
```

The artifacts, rather than a chat transcript, are the handoff contract. A plan
defines feature boundaries and order. A spec defines acceptance criteria,
tests, and tasks for one feature. Implementation works against that approved
spec. Verification and review inspect the result and route defects back to the
layer that owns the correction.

### Scope Lock: escalate up, do not widen in place

Every write-capable stage has a **Scope Lock**:

- `/ce-spec` may refine one planned feature, but it may not expand the plan.
- `/ce-implement` may implement the approved spec, but it may not redesign it.
- `/ce-patch` may touch only its approved file set; structural work graduates
  to `/ce-plan`.
- product and release workflows may frame or prepare a decision, but do not
  take product or deployment authority from the human.

When a stage finds a conflict, it records the evidence and routes upward. A
spec-level boundary conflict returns to planning; an implementation/spec
conflict returns to specification. Read-only skills such as review, verify,
debug, ask, impact, and most probes report findings instead of changing the
layer they inspect.

This keeps a convenient request such as "fix it while you are here" from
silently turning a review or diagnosis into an unplanned code change.

## 2. The skill surface

`/ce-go <outcome>` is the front door when the caller does not know which skill
fits. It inspects repository state, explains one proposed route, and hands off
only after confirmation. Direct invocation remains available for callers who
already know the workflow they need.

### Entry, repository understanding, and onboarding

| Skill | Responsibility |
|---|---|
| `/ce-go` | Route a request to one appropriate skill; it does not perform the work itself. |
| `/ce-init` | Profile the repository and, with `--write`, create starter policy and guard configuration. |
| `/ce-ask` | Answer one codebase question with `file:line` evidence and no writes. |
| `/ce-impact` | Analyze the blast radius and unknowns of a proposed change without implementing it. |
| `/ce-domain` | Teach the business concepts encoded in a codebase, separating recorded, enforced, and inferred claims. |
| `/ce-onboard` | Teach the implementation of a built system or plan through an evidence-grounded walkthrough. |

### Planning, building, and bounded change

| Skill | Responsibility |
|---|---|
| `/ce-brief` | Turn a raw request into a planning-ready brief through a bounded interview. |
| `/ce-plan` | Decompose work into ordered features, decisions, risks, and cross-feature obligations. |
| `/ce-plan-audit` | Lint and review an existing plan without rewriting it. |
| `/ce-spec` | Convert one planned feature into EARS acceptance criteria, tests, and `tasks.json`. |
| `/ce-implement` | Execute an approved task list test-first and record verification evidence. |
| `/ce-patch` | Handle one genuinely small change; `--express` is the narrower two-file lane, and larger work graduates to planning. |
| `/ce-auto-build` | Run the planned spec/implement/check loop across features with budgets, retries, parks, checkpoints, and an end review. |

### Assurance, diagnosis, and operational evidence

| Skill | Responsibility |
|---|---|
| `/ce-verify` | Check implemented behavior, journeys, dependencies, and acceptance criteria; it does not fix failures. |
| `/ce-review` | Review code and inbound review comments, producing findings and a machine-readable summary; it does not patch. |
| `/ce-debug` | Reproduce and classify a failure, then route the fix to implementation, specification, or planning. |
| `/ce-ux-audit` | Walk planned journeys or probe an unplanned running surface for UX findings. |
| `/ce-probe-deps` | Check pinned dependencies against OSV advisories, with loud degraded behavior when offline. |
| `/ce-probe-infra` | Inspect infrastructure manifests and static scanner evidence. |
| `/ce-probe-sec` | Perform consent-gated dynamic security probing against an authorized target. |
| `/ce-probe-perf` | Collect measured performance signals from an authorized running target. |
| `/ce-retro` | Summarize recorded pipeline signals and optionally compile an evidence pack without re-judging the work. |

### Decisions, delivery, and documentation

| Skill | Responsibility |
|---|---|
| `/ce-decide` | Compare technical options and draft an evidence-tagged proposed ADR; a human promotes it. |
| `/ce-ship-backlog` | Emit one-way ADO, Jira, or GitHub work-item files from a spec; it does not call tracker APIs. |
| `/ce-ship-deliver` | Prepare a local delivery branch and manifest; it never pushes. |
| `/ce-ship-release` | Prepare a GO/NO-GO decision package, evidence inventory, and optional changelog; it never deploys. |
| `/ce-ship-document` | Generate user-facing documentation from verified behavior and runnable examples. |
| `/ce-humanize` | Rewrite supplied prose while preserving facts and markup; file edits require consent. |
| `/ce-doc-audit` | Execute an existing guide as a reader role in a sandbox and report findings without editing the source. |

The optional `product-discovery` plugin adds `/ce-idea-scout` for generating and
ranking directions, `/ce-idea-score` for evaluating one direction, and
`/ce-market-scan` for sourced market and competitor research. They sit before
`/ce-brief`; the engineering spine does not require them.

## 3. The artifact model

Durable workflow state is ordinary Markdown and JSON in the adopter
repository. It can be reviewed in a pull request, diffed, retained, or removed
without a proprietary database.

The central layout is:

```text
docs/
├── adr/                             # accepted cross-feature decisions
├── briefs/
│   ├── <slug>.md                    # human-readable brief
│   └── <slug>.json                  # machine-readable brief status
└── plans/
    ├── plans.json                   # registry of plans in this repository
    ├── repo-profile.json            # /ce-init repository profile
    ├── vc-policy.md                 # version-control and delivery policy
    ├── review-policy.md             # human-owned review calibration
    ├── patterns.md                  # known repository hazards
    ├── express-log.jsonl            # /ce-patch --express ledger
    └── <slug>/
        ├── feature-plan.md
        ├── shared-context.md
        ├── threat-model.md
        ├── interaction-contract.md
        ├── plan.json
        ├── features/<id>.md
        ├── specs/<id>/
        │   ├── ce-spec.md
        │   ├── tasks.json
        │   ├── verification.md
        │   ├── code-review.md
        │   ├── review-summary.json
        │   └── diagnosis.md
        ├── verification-report.md
        ├── evidence/
        ├── .metrics.jsonl
        ├── STATUS.md
        ├── ce-auto-build/<date>-run.md
        ├── delivery/<date>-manifest.md
        ├── release/<date>-release.md
        └── evidence-pack/<date>/
```

Not every plan contains every file. For example, review and diagnosis artifacts
appear only when those workflows run. `STATUS.md` is a generated projection of
plan and auto-build state, not a second source of truth.

Other skills write dated, never-overwritten reports such as
`docs/dep-audits/<date>-<slug>.md`,
`docs/infra-reviews/<date>-<slug>.md`,
`docs/sec-probes/<date>-<slug>.md`,
`docs/perf-profiles/<date>-<slug>.md`,
`docs/ux-audits/<date>-<slug>.md`,
`docs/plan-audits/<date>-<slug>.md`,
`docs/doc-audits/<date>-<slug>.md`,
`docs/decisions/<slug>/<date>.md`,
`docs/domain/<date>-<scope>-primer.md`, and
`docs/onboarding/<date>-<target>.md`. The relevant skill defines the exact
schema.

Draft directories under `docs/briefs/.drafts/` and `docs/plans/.drafts/` are
crash-resume scratch space. They are not registered plans or approved inputs
and are removed when the final artifact is accepted. Runtime guard state under
`.claude/` is also configuration or session state, not a project decision.

`tasks.json` is more than a checklist. When implementation marks work done, its
helper scripts can bind the state to a completion time, commit, and test-run
digest. Downstream workflows re-check that evidence and may report a task as
stale after a rebase, revert, or mismatched test record. A dated evidence pack
copies and hashes available artifacts; it compiles what the pipeline recorded
but is not a compliance attestation.

## 4. Human authority and runtime safety

The framework gives the model engineering work, not unrestricted authority.
The durable rule is that product, scope, security, destructive, and release
decisions remain human-owned.

### Human-in-the-loop gates

Material decisions are rendered with evidence, consequences, and a visible
`Gate N of M` locator. Dense gates lead with the rows that actually need a
decision. A human should not be asked to confirm a model-derived classification
without seeing its basis and the cost of being wrong.

The normative contributor rules live in the
[HITL Gate Standard](contributing/HITL-GATE-STANDARD.md). The installed skills
carry their runtime instructions inline, so an adopter does not need this
repository document for a gate to work.

Review, verification, audits, and probes follow **findings, not verdicts**. They
may classify severity and produce a blocking machine signal, but a human owns
the disposition and any accepted risk. A release skill prepares a decision; it
does not tag, publish, or deploy the release.

### Plugin hook backstops

On the Claude Code plugin surface, four PreToolUse hooks backstop common
high-risk capabilities:

- `git-guard.py` asks or denies, according to configured tiers, before shared-
  history operations such as push, pull-request mutation, tag creation, and
  writes on a protected branch.
- `env-guard.py` blocks high-risk credential-store and out-of-workspace secret
  reads. It is targeted confinement, not complete data-loss prevention.
- `write-scope-guard.py` enforces the active skill's session-bound write lease
  across direct file tools and recognized shell write forms. A lease left by a
  dead session self-heals to the baseline with a visible confirmation; an
  in-scope live lease still denies out-of-scope writes.
- `net-guard.py` checks common outbound calls and upload forms against the
  repository's network policy, and denies recognized secret-upload payloads.
  It is an egress checkpoint, not a network sandbox.

The guards append decisions to `.claude/ce-guard-log.jsonl`, whose records form
a hash chain that can reveal edits, deletion, or reordering. `hook-integrity.py`
checks the installed hook files at session start and warns on drift from the
shipped manifest. These controls are tamper-evident rather than tamper-proof: a
process with broad shell access is not contained like it would be by an OS or
container sandbox.

Read-only skills set a write lease at entry and clear it at exit.
`/ce-init --write` creates the deny-only baseline and starter network policy. Without the
relevant policy file, a hook may intentionally remain inert; the hook README
documents each default and limitation.

The safety contract also applies above the hooks. Skills do not push, open or
merge pull requests, deploy, rotate credentials, or publish packages on their
own. `/ce-auto-build` may make checkpoint commits only on an isolated
`auto-build/<slug>/<date>` branch when that mode is explicitly selected; it
does not push or merge that branch.

Plugin hooks do not run in the Managed Agent cookbooks or in a standalone CI
gate. Those surfaces must not be described as having equivalent runtime
confinement. Managed Agent hosts own tool grants and sandboxing; CI judges only
the committed repository state supplied to it.

## 5. Deterministic gates and the merge bar

The workflows use small, on-disk validators so important structural checks do
not depend on a model agreeing with its own output. Examples include plan DAG
and reference checks, spec traceability, test-integrity checks, dependency
declarations, patch-boundary checks, review summaries, and evidence schemas.
The scripts use a consistent exit shape: pass, finding/failure, or could-not-run.
Degraded execution is reported instead of being presented as a clean result.

### Two separate merge questions

The merge bar keeps two questions separate:

1. **Integrity:** did the configured deterministic gates pass against the
   committed base and head?
2. **Validity:** did the required human review happen for this change class?

[`scripts/gate_runner.py`](../scripts/gate_runner.py) executes the integrity
part from the committed
[`merge-policy.json`](../plugins/core-engineering/merge-policy.json). The
shipped `standard` and `sensitive` classes require `spec-lint`, `test-guard`,
and `dep-guard`. The policy also registers advisory checks for known-vulnerable
dependencies, implementation scope, review evidence, plan structure, added
secrets, and accepted-risk dispositions. Adopters can promote advisory gates
after their repository has the inputs those gates require.

The validity value is `human` or `two-human`. The runner records it but cannot
prove that a reviewer approved the pull request. The host platform must map it
to branch protection or repository rules. A green integrity result without
the required review is not a merge authorization.

### What a green result proves

A green default result proves the configured artifact-integrity conditions:
spec traceability held, tests were not weakened in the patterns the guard
recognizes, and no undeclared direct dependency entered a supported manifest.
It does **not** prove that:

- the project compiles;
- the test suite passes or is sufficient;
- the behavior meets the product need;
- a package name exists or is trustworthy on a registry;
- the system is secure, compliant, or ready for production.

Every adopter must keep its normal build, lint, test, and security jobs as
separate required checks.

### Keeping the PR from supplying its own policy

The merge action judges committed refs. A local merge-policy override is read
from the **base ref**, so a pull request cannot weaken its own bar in the same
change. The declared-dependency list is intentionally read from **both the base
ref and the PR head**, and the union is passed to `dep-guard`. This permits a
same-PR dependency declaration, while edits under `.github/**` or
`.merge-bar/**` classify the change as `sensitive` and therefore request two
human reviewers under the shipped policy.

The calling workflow is still part of the trust boundary. Protect `.github/**`
with CODEOWNERS or a ruleset, and require both the merge bar and the project's
build/test job. Optional signed verdicts bind a green result to base/head SHAs
and a policy hash, but they complement rather than replace repository rules.

### Delivery surfaces

GitHub users can pin the
[`action/merge-bar`](../action/merge-bar/README.md) composite action to a full
40-character commit SHA. Teams that cannot run a third-party action can use the
checksum-verified copy-in templates described in
[Team Rollout](TEAM-ROLLOUT.md); equivalent templates are included for GitLab
CI and Azure Pipelines. Teams that want only the test-integrity check can use
the separate [`action/test-integrity`](../action/test-integrity/README.md).

The same gate runner is exposed by the plugin's stdio MCP server for an
MCP-capable host. The server returns each underlying script's verdict and exit
code; it does not reinterpret a failure as a pass. `scripts/drift_scan.py` is
the post-merge complement: it re-projects committed plan/spec artifacts on a
schedule and routes drift to `/ce-plan` or `/ce-spec`.

## 6. Automation surfaces

The plugin ships two leaf custom agents:

- `spec-author` wraps `/ce-plan` and `/ce-spec` for focused artifact authoring.
- `spec-impl` wraps `/ce-implement` for focused test-first execution.

They use the same skills and artifact contracts as direct invocations. They do
not spawn nested task workers and do not gain push, merge, or deployment
authority.

`/ce-auto-build` is different: it is the in-plugin orchestrator for a complete
plan. Stage 0 fixes the feature, retry, park, checkpoint, and budget limits.
Each feature then moves through specification, implementation, verification,
and review gates. Blocking product decisions are parked for a human rather
than guessed. Run state is persisted under `ce-auto-build/`, and `--resume`
re-derives state from disk instead of trusting chat memory. The final review
surfaces provisional decisions and any downstream work that must be repeated
if a decision changes.

The Managed Agent cookbooks package four deployable workers around the same
skills, but they are reference building blocks rather than a hosted workflow
engine. Their host owns routing, state, retries, budgets, credentials, and
approvals. Because plugin hooks do not load there, use ephemeral checkouts and
restrict tools and network access at the host layer.

## 7. Evidence, evaluation, and honest limits

Repository validation combines several layers:

- `scripts/check.py` validates manifests, skill/agent inventory, model policy,
  forked-script integrity, the README catalog, and delegated linters.
- unit tests exercise hooks, gate scripts, the merge runner, eval tooling, and
  documentation drift checks;
- the eval corpus runs skills against small fixture repositories and replays
  frozen artifacts through deterministic gates;
- CI pins third-party actions, scans history for secrets, validates both
  plugins, and runs the portable gate corpus without Claude Code.

[Benchmarks and Measured Costs](BENCHMARKS.md) distinguishes recorded live runs
from design-verified scenarios and states which skills have not been measured.
[Real Outputs](EXAMPLES.md) shows captured artifacts with provenance. The eval
harness and contributor protocol live in the
[eval corpus README](../evals/README.md).

The framework records evidence; it does not convert evidence into a legal,
security, or product guarantee. The control mapping in
[Enterprise Hardening](ENTERPRISE-HARDENING.md) is a vocabulary bridge with
explicit residual owners and gaps, not a certification. Dynamic probes are
bounded observations, static checks have false-positive and false-negative
risk, and model-written prose still needs human review.

## 8. Contributor architecture

Skills are the source of truth. A `SKILL.md` holds the always-loaded purpose,
inputs, contract, human gates, escalation, and limitations. Larger skills move
stage bodies and artifact templates into companion files loaded only when that
stage runs. This progressive-disclosure shape reduces context use without
creating a second workflow definition.

The [Skill Authoring Standard](contributing/SKILL-AUTHORING.md) defines the
shared skeleton, vocabulary, description limits, and routing clauses. Gate
scripts that must exist beside multiple skills are registered in
`plugins/core-engineering/fork-manifest.json`; contributors edit the canonical
copy and run `python3 scripts/fork_sync.py --write` so CI can verify byte
identity.

When a change adds or removes a skill, changes a gate or escalation path, or
changes an artifact location, update this overview, the README catalog, and the
Usage Matrix in the same change. Mechanical refactors and typo fixes do not
need an architecture rewrite, but public behavior and public paths must never
be left to inference from implementation code.
