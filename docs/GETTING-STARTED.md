# Getting Started

This is the fast path for using `core-engineering` in a real repository. Use
`docs/HOW-IT-WORKS.md` when you need the architecture; use this page when you
want to get useful output in the first session.

## Prerequisites

- **Claude Code** installed and authenticated (subscription or API billing) —
  the plugin runs inside it, on any OS Claude Code supports.
- **`python3`** (3.10+) on `PATH` — the plugin's safety hooks and on-disk gate
  scripts are stdlib-only Python; nothing to `pip install`.
- **A git repository to work in** — every artifact the skills write is plain
  markdown/JSON, meant to be committed and reviewed like code.
- **Model-spend awareness** — skills make model calls on your plan or API key;
  see [What It Costs](#what-it-costs) below for historical budget caps.

## Install

```bash
claude plugin marketplace add relusion/vg-sdlc-claude-plugins
claude plugin install core-engineering@vg-coding
```

The upstream idea/market skills (`/product-discovery:ce-idea-scout`, `/product-discovery:ce-idea-score`,
`/product-discovery:ce-market-scan`) ship as a small **companion** plugin. Install it only if you
also want the product-discovery front-end — the core engineering framework does
not need it:

```bash
claude plugin install product-discovery@vg-coding
```

Then open a project repository in Claude Code and invoke skills directly with
their plugin-qualified names, for example:

```text
/core-engineering:ce-ask Where is login rate limiting enforced?
/core-engineering:ce-impact Add CSV export to the orders report.
/core-engineering:ce-init --write
/core-engineering:ce-brief We need team invitations with role-based access.
```

### Watch it catch a cheat (60 seconds, offline)

From a clone of this repository (bash + git + python3 only — no network, no
Claude required):

```bash
bash scripts/demo-cheat-catch.sh
```

The script builds a throwaway adopter repo from a shipped fixture and runs the
merge bar three times: an honest change passes (green verdict), a committed
"cheat" that guts the test file's assertions goes red with `test-guard` named
in the hard failures, and reverting the cheat goes green again. On a color
terminal the PASS/FAIL headline renders bold green/red so the verdict is
readable from across the room.

## First 10 Minutes

**One command to remember in week one:** `/core-engineering:ce-go <what you want>`. It is the
front door: describe the outcome in plain language ("why does export fail",
"score this idea", "is this code safe to ship") and it inspects repo state (a
plan on disk? a spec for the named feature? a running target?), routes to the
right skill, shows its reasoning, and asks you to confirm before it hands off.
It routes, never executes: after confirmation it starts a model-invocable skill,
or prints the exact command when the destination requires direct human
invocation. Instead of learning ~30 skill names, you learn one. The steps below
are what `/core-engineering:ce-go` routes *to*; run them directly once you know which one you want.

```text
/core-engineering:ce-go The export job silently stops after a few hundred rows.
```

Expected output: a single routing gate — e.g. *"Routing to `/core-engineering:ce-debug`
because a failing component matches the diagnosis lane — Proceed / Pick another /
Abort"* — then it starts the chosen skill or prints its direct command. It writes
nothing itself.

1. Bootstrap repository policy:

   ```text
   /core-engineering:ce-init --write
   ```

   Expected output: `docs/plans/repo-profile.json`, `vc-policy.md`,
   `review-policy.md`, and `patterns.md` when missing, plus the
   `.claude/ce-write-scope.json` deny-only write-scope baseline (git internals
   and the lease file itself are never agent-writable). It also appends
   `.gitignore` entries for the five runtime guard/session files
   (`.claude/ce-write-scope.json`, `.claude/ce-write-scope.session.json`,
   `.claude/ce-guard-log.jsonl`, `.claude/ce-session-model.json`, and
   `.claude/ce-net-policy.json`) when they are absent.

2. Ask one grounded question:

   ```text
   /core-engineering:ce-ask Where is authentication enforced?
   ```

   Expected output: a short answer with `file:line` citations and no file
   writes.

3. Analyze one proposed change:

   ```text
   /core-engineering:ce-impact Add CSV export to the orders report.
   ```

   Expected output: affected components, blast radius, rough sizing, open
   questions, and a paste-ready summary.

4. If the work is real, start the planning path:

   ```text
   /core-engineering:ce-brief Add team invitations with role-based access.
   /core-engineering:ce-plan <brief-or-project-description>
   ```

   Expected output: `docs/briefs/<slug>.md`, then `docs/plans/<slug>/`.

5. If the work is genuinely small:

   ```text
   /core-engineering:ce-patch Fix the typo in the archived item status label.
   ```

   Expected output: a mechanical admission screen for a change bounded to at
   most two files. An admitted patch runs test-first, shows the diff and
   evidence at one human gate, and records one line in
   `docs/plans/express-log.jsonl` after acceptance. If the screen is uncertain
   or the change is structural, `/core-engineering:ce-patch` stops and routes to `/core-engineering:ce-plan`.

## Common First Runs

| Situation | Start Here | What You Get |
|---|---|---|
| I am using this plugin in a repo for the first time | `/core-engineering:ce-init --write` | Repo profile, starter SDLC policy artifacts, and the write-scope baseline |
| I need to understand code | `/core-engineering:ce-ask` | Cited answer, no writes |
| I need to refine a work item | `/core-engineering:ce-impact` | Blast-radius read and open questions |
| I have a raw feature idea | `/core-engineering:ce-brief` -> `/core-engineering:ce-plan` | Brief, plan, feature decomposition |
| I have an approved plan feature | `/core-engineering:ce-spec` -> `/core-engineering:ce-implement` | `ce-spec.md`, `tasks.json`, code, tests, verification |
| I need confidence before handoff | `/core-engineering:ce-review` + `/core-engineering:ce-verify` | Review findings and behavior-verification evidence |
| I need release readiness | `/core-engineering:ce-ship-release` | Release decision package and changelog proposal |
| I need a risk probe | `/core-engineering:ce-probe-infra`, `/core-engineering:ce-probe-sec`, `/core-engineering:ce-probe-perf`, or `/core-engineering:ce-ux-audit` (UX) | Evidence-backed findings within each probe boundary |

For the full router, use `docs/USAGE-MATRIX.md`. For recipes with stop
conditions, use `docs/WORKFLOW-RECIPES.md`.

## What It Costs

Skills make model calls on your Claude plan or API key. These are the configured
caps on successful 2026-06-27 runs against deliberately tiny fixtures, not
actual spend, current-contract passes, or forecasts. Every current scenario
awaits a clean rerun after contract changes. Method, recency status, and reproduction commands
are in [docs/BENCHMARKS.md](./BENCHMARKS.md):

| Path | Historical per-run cap (USD) |
|---|---|
| `/core-engineering:ce-ask` grounded answer · `/core-engineering:ce-impact` blast-radius read | $1 |
| `/core-engineering:ce-review` six-lens review of one feature | $2 |
| `/core-engineering:ce-plan` decomposition · `/core-engineering:ce-implement` one feature · `/core-engineering:ce-probe-infra` audit | $3 |
| `/core-engineering:ce-spec` one implementation-ready spec · prior `/core-engineering:ce-patch` contract | $4 |

Historically, those four calls authorized up to $12 for one tiny feature through
plan → spec → implement → review; actual spend was not retained. Use a
project-specific pilot before budgeting.
Anything autonomous is budget-capped up front:
`/core-engineering:ce-auto-build` asks for a token budget at Stage 0, and executed evals refuse
to run without an explicit `--max-budget-usd`.

## Safety Boundaries

The framework is intentionally conservative:

- It does not push, merge, deploy, rotate secrets, or tag releases.
- Review, verify, debug, ask, impact, audit, probe, and retro workflows report
  findings or evidence; they do not silently patch.
- Product, scope, security, release, and destructive decisions stay with the
  human.
- Generated artifacts live in `docs/` so they can be reviewed, versioned, and
  discarded like normal project files.
- Read-only skills hold a **write lease** during their session (a small
  `.claude/ce-write-scope.json` policy the write guard enforces, bound to the
  session that set it). A lease left behind by a **dead** session self-heals:
  the guard notices the current session does not own it, auto-replaces it with
  the deny-only baseline, and asks you to approve **once** — no hidden JSON
  file to hunt down and hand-delete. A deny you *do* see means a **live** skill
  still holds the lease and the edit is outside its declared scope; let that
  skill finish or reconcile with it rather than forcing the write.

## Troubleshooting

| Symptom | Likely Cause | Next Step |
|---|---|---|
| A skill picked the wrong lane | The request was ambiguous or too broad | Invoke the intended skill directly, for example `/core-engineering:ce-impact ...` |
| `/core-engineering:ce-impact` refuses | The change description is too thin | Add subject, action, and desired outcome |
| `/core-engineering:ce-patch` routes to `/core-engineering:ce-plan` before editing | The screen found more than 2 files, a reviewer-trigger surface, a cross-feature collision, a dependency manifest, or uncertain scope | Narrow the request or continue with `/core-engineering:ce-plan`; patch never silently expands its scope |
| A probe refuses | Target, environment, or authorization is unsafe or unclear | Use a local/dedicated target and pass the consent gate |
| A release is NO-GO | Verification, review, rollback, or supply-chain evidence is missing | Run the routed skill or have the human accept the gap |
| Claude asked me to confirm a `git push` / PR command | The `git-guard` backstop is preserving human authority over shared history | Approve or refuse the prompt. For hard-deny tiers and environment variables, see the [hooks guide](../plugins/core-engineering/hooks/README.md). |
| A file edit was denied mid-skill | A read-only skill holds the session write lease and the edit is outside its scope | Let a live skill finish. For a stale or ambiguous lease, follow the guard's recovery message and the [hooks guide](../plugins/core-engineering/hooks/README.md); do not bypass a live lease. |

## Where To Go Next

- `docs/README.md` for the audience-based documentation index.
- `docs/USAGE-MATRIX.md` for the canonical command router.
- `docs/WORKFLOW-RECIPES.md` for common end-to-end paths.
- `docs/HOW-IT-WORKS.md` for the framework model.
- `docs/ENTERPRISE-HARDENING.md` for control mapping and supply-chain evidence.
- `evals/README.md` for behavior-evaluation setup and grading.

## Contributing to the Framework

Working on this repository itself rather than using the plugin? Contributor
prerequisites, the full validation battery, and the authoring standards live
in [CONTRIBUTING.md](../CONTRIBUTING.md).
