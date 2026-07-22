# How `core-engineering` Works

`core-engineering` is a Claude Code plugin for planning, implementing, and
checking software changes through repository-resident artifacts. It contains
**29 skills** and **2 plugin-shipped custom agents**. A separate
`product-discovery` plugin adds three optional idea and market-research skills.

The Claude Code plugin is the primary runtime. The repository also contains an
agent-independent merge bar that runs in CI without Claude Code.

For installation and a first session, start with
[Getting Started](GETTING-STARTED.md). For command selection, use the
[Usage Matrix](USAGE-MATRIX.md). This page explains the architecture and the
boundaries that apply across the whole framework.

## 1. The operating model

The main workflow is a spine where each stage produces a durable input for the
next:

```text
/core-engineering:ce-brief -> /core-engineering:ce-plan
    (capability frame -> conditional architecture options + human direction selection
     -> detailed decomposition -> architecture/plan shaping)
    -> [/core-engineering:ce-architecture baseline, required by plan disposition when load-bearing]
    -> /core-engineering:ce-spec -> /core-engineering:ce-implement
                                      |-> /core-engineering:ce-verify   behavior and acceptance proof
                                      |-> /core-engineering:ce-review   code-quality findings
                                      `-> /core-engineering:ce-debug    cause analysis and fix routing

/core-engineering:ce-auto-build  orchestrates the planned spine across multiple features
/core-engineering:ce-patch       handles one low-risk change of at most two files
/core-engineering:ce-ux-audit    checks a running product, with or without a plan

release tail: /core-engineering:ce-ship-release -> /core-engineering:ce-ship-document
```

The artifacts, rather than a chat transcript, are the handoff contract. Planning
first reconciles intent with repository evidence and builds a coarse capability
map—never feature IDs or tasks. When architecture can determine the delivery
shape, it invokes `/core-engineering:ce-architecture explore:<draft-slug>` to
generate complete solution directions, eliminate hard-constraint failures, and
score the viable options against human-confirmed requirements and quality
priorities. A human selects the direction before detailed feature decomposition.
The exact option set and selection survive in `architecture-selection.json`.

After decomposition, `/core-engineering:ce-architecture shape:<draft-slug>` checks
that provisional features realize the selected direction; planning alone applies
any human-approved delta. The written plan records `architecture_disposition` and
the selection-file hash. A required disposition blocks specification and direct implementation until
the normal architecture mode projects the stable plan into approved system,
deployment, data/integration, and quality views. Recommended, not-required, and
human-waived routes remain explicit rather than treating absence as silently
optional. A spec then defines acceptance criteria, tests, and tasks for one feature.
Implementation works against that approved spec. Verification and review
inspect the result and route defects back to the layer that owns the
correction.

### Scope Lock: escalate up, do not widen in place

Every write-capable stage has a **Scope Lock**:

- `/core-engineering:ce-architecture` shape mode may propose an evidence-backed
  delta to a provisional candidate but may not apply it; `/core-engineering:ce-plan`
  and the human retain decomposition authority. Explore mode may generate,
  eliminate, score, and recommend complete solution directions, but only the
  human selects one and only planning persists the binding. Baseline mode may synthesize
  cross-feature views from a written plan, but it may not re-cut features, add
  obligations, or make feature-level design decisions.
- `/core-engineering:ce-spec` may refine one planned feature, but it may not expand the plan.
- `/core-engineering:ce-implement` may implement the approved spec, but it may not redesign it.
- `/core-engineering:ce-patch` may touch only its approved file set; structural work graduates
  to `/core-engineering:ce-plan`.
- product and release workflows may frame or prepare a decision, but do not
  take product or deployment authority from the human.

When a stage finds a conflict, it records the evidence and routes upward. A
spec-level boundary conflict returns to planning; an implementation/spec
conflict returns to specification. Code-read-only analysis workflows such as review, verify,
debug, ask, impact, and most probes report findings instead of changing the
layer they inspect.

This keeps a convenient request such as "fix it while you are here" from
silently turning a review or diagnosis into an unplanned code change.

## 2. The skill surface

`/core-engineering:ce-go <outcome>` is the front door when the caller does not know which skill
fits. It inspects repository state, explains one proposed route, and hands off
only after confirmation. It starts model-invocable routes and returns the exact
command for direct-only routes. Callers who already know the workflow they need
can invoke it directly.

### Entry, repository understanding, and onboarding

| Skill | Responsibility |
|---|---|
| `/core-engineering:ce-go` | Route a request to one appropriate skill; it does not perform the work itself. |
| `/core-engineering:ce-init` | Profile the repository and, with `--write`, create starter policy and guard configuration; `--readiness` separates local prerequisites from host controls that still need administrator evidence. |
| `/core-engineering:ce-ask` | Answer one codebase question with `file:line` evidence and no writes. |
| `/core-engineering:ce-impact` | Analyze the blast radius and unknowns of a proposed change without implementing it. |
| `/core-engineering:ce-domain` | Teach the business concepts encoded in a codebase, separating recorded, enforced, and inferred claims. |
| `/core-engineering:ce-onboard` | Teach the implementation of a built system or plan through an evidence-grounded walkthrough. |

### Planning, building, and bounded change

| Skill | Responsibility |
|---|---|
| `/core-engineering:ce-brief` | Turn a raw request into a planning-ready brief through a bounded interview. |
| `/core-engineering:ce-plan` | Reconcile intent and repository evidence, conditionally obtain a human-selected solution direction, then decompose work into ordered features and verify architecture/plan convergence before the cut freezes. |
| `/core-engineering:ce-architecture` | In `explore:<draft-slug>` mode, generate and score complete solution directions before decomposition; in `shape:<draft-slug>` mode, assess whether provisional features realize the selected direction; in normal mode, turn one written multi-feature plan into a human-approved repository-grounded baseline. It never applies a re-cut or replaces feature specifications. |
| `/core-engineering:ce-plan-audit` | Lint and review an existing plan without rewriting it. |
| `/core-engineering:ce-spec` | Validate the plan's architecture disposition and any occupied package, then convert one eligible planned feature into EARS acceptance criteria, tests, and `tasks.json`; required missing or stale architecture blocks. |
| `/core-engineering:ce-implement` | Revalidate the plan's architecture prerequisite before trusting an existing spec, then execute its approved task list test-first and record verification evidence. |
| `/core-engineering:ce-patch` | Handle one change of at most two files through a single approval gate; failed or uncertain admission routes to planning. |
| `/core-engineering:ce-auto-build` | Run one fixed, sequential spec/implement/verify/review loop across features with budgets, retries, parks, and an end review. |

### Assurance, diagnosis, and operational evidence

| Skill | Responsibility |
|---|---|
| `/core-engineering:ce-verify` | Check implemented behavior, journeys, dependencies, and acceptance criteria; it does not fix failures. |
| `/core-engineering:ce-review` | Review code and inbound review comments, producing findings and a machine-readable summary; it does not patch. |
| `/core-engineering:ce-debug` | Reproduce and classify a failure, then route the fix to implementation, specification, or planning. |
| `/core-engineering:ce-ux-audit` | Walk planned journeys or probe an unplanned running surface for UX findings. |
| `/core-engineering:ce-probe-deps` | Check pinned dependencies against OSV advisories, with loud degraded behavior when offline. |
| `/core-engineering:ce-probe-infra` | Inspect infrastructure manifests and static scanner evidence. |
| `/core-engineering:ce-probe-sec` | Perform consent-gated dynamic security probing against an authorized target. |
| `/core-engineering:ce-probe-perf` | Collect measured performance signals from an authorized running target. |
| `/core-engineering:ce-retro` | Summarize recorded pipeline signals and optionally compile an evidence pack without re-judging the work. |

### Decisions, release, and documentation

| Skill | Responsibility |
|---|---|
| `/core-engineering:ce-decide` | Compare supplied options for one bounded technical fork and draft an evidence-tagged proposed ADR; complete solution-direction generation belongs to architecture exploration. |
| `/core-engineering:ce-ship-backlog` | Emit one-way ADO, Jira, or GitHub work-item files from a spec; it does not call tracker APIs. |
| `/core-engineering:ce-ship-release` | Prepare a GO/NO-GO decision package, evidence inventory, and optional changelog; it never deploys. |
| `/core-engineering:ce-ship-document` | Generate user-facing documentation from verified behavior and runnable examples. |
| `/core-engineering:ce-humanize` | Rewrite supplied prose while preserving facts and markup; file edits require consent. |
| `/core-engineering:ce-doc-audit` | Execute an existing guide as a reader role in a sandbox and report findings without editing the source. |

The optional `product-discovery` plugin adds `/product-discovery:ce-idea-scout` for generating and
ranking directions, `/product-discovery:ce-idea-score` for evaluating one direction, and
`/product-discovery:ce-market-scan` for sourced market and competitor research. They sit before
`/core-engineering:ce-brief`; the engineering spine does not require them.

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
    ├── repo-profile.json            # /core-engineering:ce-init repository profile
    ├── vc-policy.md                 # version-control and release policy
    ├── review-policy.md             # human-owned review calibration
    ├── patterns.md                  # known repository hazards
    ├── express-log.jsonl            # accepted /core-engineering:ce-patch ledger
    └── <slug>/
        ├── architecture-selection.json    # reviewed option set + human-selected pre-decomposition direction
        ├── feature-plan.md
        ├── shared-context.md
        ├── threat-model.md
        ├── interaction-contract.md
        ├── plan.json
        ├── features/<id>.md
        ├── architecture/
        │   ├── solution-architecture.md
        │   ├── views.md
        │   ├── data-and-integrations.md
        │   ├── quality-attributes.md
        │   └── architecture.json
        ├── specs/<id>/
        │   ├── ce-spec.md
        │   ├── tasks.json
        │   ├── verification.md
        │   ├── code-review.md
        │   └── review-summary.json
        ├── diagnosis.md
        ├── verification-report.md
        ├── evidence/
        ├── .metrics.jsonl
        ├── STATUS.md
        ├── ce-auto-build/
        │   ├── <date>-state.json
        │   ├── <date>-ledger.jsonl
        │   └── <date>-run.md
        ├── release/<date>-release.md
        └── evidence-pack/<date>/
```

Every newly written full plan carries `architecture-selection.json`: either the
exact reviewed option set and selected direction, an adopted existing direction,
or an explicit not-applicable/deferred/waived record. Legacy absence routes to
plan revision before a write-capable downstream workflow proceeds. The
`architecture/` package remains conditional:
it is mandatory before spec, direct implementation, or auto-build when
`plan.json` records `required`, a
visible coverage gap when `recommended`, N/A when `not-required`, and an
explicit residual risk when human-waived. It is written as one coherent set
only after human approval; an approved package is design context for downstream specs, not implementation, security,
compliance, release, or deployment authority. Review and diagnosis artifacts
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

`<date>` is the first run key for that UTC day. A never-overwritten workflow
resolves every companion path before it writes: if the first key already exists,
the next run uses a shared `-2`, then `-3`, suffix across its report, machine
companion, and evidence directory. For example, a second same-day audit uses
`<date>-<slug>-2` everywhere. This keeps reruns distinct without splitting one
evidence set across different keys.

Draft directories under `docs/briefs/.drafts/` and `docs/plans/.drafts/` are
crash-resume scratch space. They are not registered plans or approved inputs
and are removed when the final artifact is accepted. Runtime guard state under
`.claude/` is also configuration or session state, not a project decision.

`tasks.json` is more than a checklist. When implementation marks work done, its
helper scripts can bind the state to a completion time, commit, and test-run
digest. Downstream workflows re-check that evidence and may report a task as
stale after a rebase, revert, or mismatched test record. Legacy evidence checks
continue to warn on unstamped tasks, while release uses the explicit strict mode:
every done task must be stamped and fresh before the workflow can issue GO.
Unstamped, stale, malformed, or unreadable evidence keeps the workflow at NO-GO;
a release owner can act under separate external authority, but that exception is
not relabeled as tool approval. A dated evidence pack
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

Architecture scores are decision support, never automatic selection. Hard
constraints gate before weighting; a failed or materially unknown residency,
security, contractual, platform, or accepted-decision constraint cannot be
averaged away. Even a single viable direction requires affirmative human
selection before detailed decomposition.

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

- `git-guard.py` asks or denies, according to configured tiers, before recognized
  shared-history operations: pushes, `gh pr create` / `gh pr merge`, mutating
  `gh api` calls to pull/merge endpoints, tag changes, and history writes on a
  protected branch. Other clients and indirect shell forms remain outside this
  pattern-based backstop.
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
process with broad shell access is not contained the way an OS or container
sandbox would contain it.

Code-read-only skills set a write lease at entry and clear it at exit. A skill
may still own a narrow evidence artifact: for example, `/core-engineering:ce-verify`
can update its cumulative `verification-report.md` and append best-effort
`.metrics.jsonl`, while source, plans, specs, task state, and implementation
evidence remain outside its lease.
`/core-engineering:ce-init --write` creates the deny-only baseline and starter network policy. Without the
relevant policy file, a hook may intentionally remain inert; the hook README
documents each default and limitation.

The safety contract also applies above the hooks. Skills do not push, open or
merge pull requests, deploy, rotate credentials, or publish packages on their
own. `/core-engineering:ce-auto-build` also does not create branches, commits, or worktrees; its
final human review owns the complete working-tree diff.

Plugin hooks do not run in a standalone CI gate. CI judges only the committed
repository state supplied to it and must not be described as equivalent runtime
confinement.

## 5. Deterministic gates and the merge bar

The workflows use small, on-disk validators so important structural checks do
not depend on a model agreeing with its own output. Examples include plan DAG
and reference checks, spec traceability, test-integrity checks, dependency
declarations, patch-boundary checks, review summaries, and evidence schemas.
The scripts use a consistent exit shape: pass, finding/failure, or could-not-run.
Degraded execution is reported instead of being presented as a clean result.
The review-evidence gate requires a non-negative `blocking_high` count and rejects
a contradictory `status` before trusting it; malformed review evidence is a
could-not-run result, never a pass. Auto-build also requires a validated
`blocking_route`: implementation defects may retry implementation, while a
`plan-conflict` parks for human-owned planning instead of looping on code.

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
prove that a reviewer approved the pull request. GitHub branch protection
cannot vary its approval count per PR from that runtime value, so the supported
default is **two required approvals globally**. That conservatively enforces
both classes; `human` remains the reported minimum. A green integrity result
without the protected review rule is not a merge authorization.

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

`scripts/drift_scan.py` is the post-merge complement: it re-projects committed
plan/spec artifacts on a schedule and routes drift to `/core-engineering:ce-plan` or `/core-engineering:ce-spec`.
The plugin does not wrap these local gates in a built-in MCP server; teams add
external connectors only where a repository workflow actually needs them.

## 6. Automation surfaces

The plugin ships two leaf custom agents:

- `spec-author` wraps `/core-engineering:ce-plan` and `/core-engineering:ce-spec` for focused artifact authoring.
- `spec-impl` wraps `/core-engineering:ce-implement` for focused test-first execution.

They use the same skills and artifact contracts as direct invocations. They do
not spawn nested task workers and do not gain push, merge, or deployment
authority. Because these leaf agents do not own an interactive-question channel,
a skill gate pauses through a structured parent handoff (`Needs decision`, gate,
evidence, options and consequences, and an exact resume input). The caller's
answer resumes from the named checkpoint; silence is never approval.

`/core-engineering:ce-auto-build` is different: it is the in-plugin orchestrator for a complete
plan. Stage 0 validates the architecture-selection binding,
`architecture_disposition`, and any present package,
blocking a missing/stale required baseline before a worker spawns; it then fixes
the feature range, failure-attempt cap, park cap, and budget. Features
then move in ship order, one at a time, through specification, deterministic
lint, implementation, verification, and independent review. Blocking product,
security-acceptance, destructive, architecture, and scope decisions are parked
for a human rather than guessed. Run state is persisted under `ce-auto-build/`,
and `--resume` re-derives state from disk instead of trusting chat memory. One
integration verification and a final human review close the run; the workflow
never creates a branch or lands its own output.

## 7. Evidence, evaluation, and honest limits

Repository validation combines several layers:

- `scripts/check.py` validates manifests, skill/agent inventory, model policy,
  forked-script integrity, the README catalog, and delegated linters;
- unit tests exercise hooks, gate scripts, the merge runner, eval tooling, and
  documentation drift checks;
- the eval corpus runs skills against small fixture repositories and replays
  frozen artifacts through deterministic gates; executed receipts record the
  observed Claude CLI version and local plugin manifest version when available,
  while unavailable provenance and unobserved token/cost data remain explicit;
- CI pins third-party actions, scans history for secrets, validates both
  plugins, and runs the portable gate corpus without Claude Code.

[Benchmarks and Evaluation Budgets](BENCHMARKS.md) distinguishes recorded live runs
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

Best-effort plan telemetry uses a versioned event contract. Current producers
can add run identity, terminal outcome, measured duration, and resolved runtime
versions; legacy streams remain readable. Repository reports validate new event
shapes and count missing streams and metadata as coverage gaps rather than zero
activity. Events must not contain prompt bodies, source, credentials, raw tool
output, or unnecessary personal data, and the adopter owns access and retention
for both `.metrics.jsonl` and any evidence-pack copy.

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

When a change adds or removes a skill, alters a gate or escalation path, or
moves an artifact, update this overview, the README catalog, and the
Usage Matrix in the same change. Mechanical refactors and typo fixes do not
need an architecture rewrite, but public behavior and public paths must never
be left to inference from implementation code.
