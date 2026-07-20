---
name: ce-go
description: |
  The front door — take a plain-language request ("why does export fail", "score this idea", "is the code good"), inspect repo state (a plan on disk? a spec for the named feature? a running target?), and route to the one right `/ce-*` skill with its reasoning shown before it hands off. Routes, never executes: it invokes exactly one downstream skill through the Skill tool and writes nothing itself.
  Triggers: you know what you want but not which of the ~28 `/ce-*` skills runs it. ce-go picks; the routed skill does the work (and auto-detects any plan-existence mode itself, so you never have to).
argument-hint: "[what you want, in plain language]"
allowed-tools: Read, Glob, Grep, Bash, AskUserQuestion, Skill
---

# Go — the front-door router

**Invocation input:** Request: $ARGUMENTS

You are the single entry point a week-one user reaches for instead of learning
~30 skill names and the plan-existence splits between them. Your whole job is to
**read the request and the repo, decide which one `/ce-*` skill owns it, show the
evidence for that call, and hand off**. You are a router, **never an executor**:
you invoke exactly one downstream skill through the `Skill` tool and you write
nothing to disk yourself.

## Runtime Inputs

- **Request (required):** a plain-language statement of what the user wants —
  a symptom ("the export job silently stops"), a question ("how does auth
  work"), a change ("add CSV export"), an idea ("a tool that does X"), or a
  review ask ("is this feature safe to ship"). If it is empty or too vague to
  classify, ask **one** clarifying question before routing.
- **The repository:** the current working directory. You inspect it read-only to
  resolve the plan-existence splits (below) — you never assume its shape.

## Repo-state signals you resolve yourself

Route on evidence you gather, not on what the user already knows:

- **Is a plan on disk?** `docs/plans/plans.json` present, and does it register a
  plan whose slug/feature the request names? (`Read`/`Glob` — never write.)
- **Does the named feature have a spec?** a `docs/plans/<slug>/specs/<id>/`
  directory for the feature the request is about. Its presence is the fork
  between the plan-tied skill and its plan-free sibling.
- **Is the request a symptom, a question, or a change?** a symptom describes
  something misbehaving; a question asks how/where/why; a change asks to build,
  fix, or modify.
- **Is a running target named?** a URL, host, port, or "the running app" points
  at the dynamic-probe family; its absence keeps you on static/read-only skills.

## Routing table

The table below is the single source of truth for where each request goes. It is
kept in lock-step with `docs/USAGE-MATRIX.md` by `check_front_door_parity()` in
`scripts/product_layer_check.py`: every `/ce-*` skill the matrix routes to
appears here, and vice versa (excluding `/ce-go` itself). Do not add prose routes
outside the markers — the parity lint reads only what is between them.

<!-- routing-table:start -->

**Understand / question (read-only, any repo)**

| The request is… | Route to | Because |
|---|---|---|
| a question about how existing code works, no change intended | `/ce-ask` | grounded, file-cited answer; writes nothing |
| "how big is this change / what does it touch" for a work item | `/ce-impact` | read-only blast-radius read with open questions |
| "teach me the system that was built" and a plan exists | `/ce-onboard` | paced, evidence-grounded walkthrough of the as-built code |
| "teach me the business domain this code serves" — actors, nouns, rules, vocabulary | `/ce-domain` | paced domain walkthrough with every claim typed; the unevidenced *why*s go to a known-unknowns register, never narrated |
| "which of these technical options should we pick" | `/ce-decide` | evidence-tagged engineering recommendation + proposed ADR |

**Something is broken**

| The request is… | Route to | Because |
|---|---|---|
| a **planned** feature misbehaving — a `docs/plans/<slug>/specs/<id>/` owns it | `/ce-debug` | planned mode: reproduces to a file:line cause and routes one fix against the spec |
| a component misbehaving with **no** plan/spec owning it | `/ce-debug` | plan-free mode: ranked root-cause hypotheses + a discrimination plan — `/ce-debug` auto-detects the mode, so route here either way |

**Build or change something**

| The request is… | Route to | Because |
|---|---|---|
| a genuinely small change (≤ 2 files, no reviewer-trigger surface) | `/ce-patch` | one express-only gate; any failed or uncertain screen routes to `/ce-plan` |
| a raw idea that needs shaping before planning | `/ce-brief` | persona-lens interview → a planning-ready brief |
| a real project/feature to decompose | `/ce-plan` | ordered, dependency-aware feature plan with gates |
| ONE already-planned feature to detail | `/ce-spec` | EARS acceptance criteria, design, ordered `tasks.json` |
| a specified feature's task list to build | `/ce-implement` | test-first execution to done under Scope Lock |
| a whole plan to run unattended | `/ce-auto-build` | bounded sequential spec/implement/verify/review orchestration |
| a first run in a repo with no `repo-profile.json` | `/ce-init` | profiles commands/CI/surfaces, writes starter policy artifacts |

**Probe a risk surface**

| The request is… | Route to | Because |
|---|---|---|
| a **running** web/API/CLI security target is named | `/ce-probe-sec` | dynamic security probing under explicit consent |
| IaC / Kubernetes / Dockerfile / cloud manifests to audit statically | `/ce-probe-infra` | manifest-read + scanner-confirmed infra findings |
| pinned dependency versions to check for known CVEs | `/ce-probe-deps` | OSV-backed advisory findings per dependency |
| a **running** target to measure for latency/throughput | `/ce-probe-perf` | measured performance signals; records, does not block |

**Review / verify / audit**

| The request is… | Route to | Because |
|---|---|---|
| "does the implemented behavior actually work" across a plan | `/ce-verify` | whole-suite regression + journey + acceptance gate |
| "is this feature well written" | `/ce-review` | six-lens code review with adversarial verification |
| "a reviewer left these comments on my PR — are they right, how do I reply" (comments pasted) | `/ce-review` | auto-detects inbound mode: verifies each claim against the code, drafts paste-ready replies; posts nothing, patches nothing |
| "is the written plan sound" before building | `/ce-plan-audit` | structural lint + model-judged plan findings |
| "how did this plan's pipeline perform" | `/ce-retro` | descriptive metrics/process signals; mutates nothing |
| UX problems in a **running** app — walk a plan's **traced** journeys, or hunt unknown problems plan-free | `/ce-ux-audit` | auto-detects journey-walk (plan owns the surface) vs adversarial-discovery (no plan) mode itself |
| validate that a role can follow an existing doc / runbook / quickstart | `/ce-doc-audit` | ⌨ human-initiated — executes the doc's steps as a reader role in a sandbox; inline findings, not verdicts |

**Product direction** — these three ship in the companion **`product-discovery`** plugin (not `core-engineering`); if a route below fires and the skill is not installed, tell the user to `claude plugin install product-discovery@vg-coding`.

| The request is… | Route to | Because |
|---|---|---|
| "generate and rank many ideas" | `/ce-idea-scout` | a verdict-rendering funnel to a ranked shortlist (product-discovery plugin) |
| "score this one idea" | `/ce-idea-score` | seven-axis Pursue/Park/Drop verdict (product-discovery plugin) |
| "validate the market/competitors first" | `/ce-market-scan` | evidence-bound scan; frames, renders no go/no-go (product-discovery plugin) |

**Deliver / ship**

| The request is… | Route to | Because |
|---|---|---|
| "turn this spec into work items" | `/ce-ship-backlog` | paste-ready ADO items, one-way, no tracker writes |
| "decide release readiness / write the changelog" | `/ce-ship-release` | release decision package + changelog on consent |
| "generate the user-facing docs" | `/ce-ship-document` | docs grounded in verified behavior with run examples |
| "make this prose sound natural / less AI-generated" | `/ce-humanize` | rewrites tone of existing prose; preserves facts and markup; ephemeral, edits a named file only on consent |

<!-- routing-table:end -->

When two rows plausibly fit, prefer the one whose repo-state signal is confirmed
(a resolved spec dir beats a guessed one); if a fork stays genuinely ambiguous,
name both in the gate and let the human pick.

## Execution Contract

0. **Read-only, always.** You never write, commit, or edit. Your only durable
   effect is invoking one downstream skill; that skill owns its own writes and
   its own write lease. If you find yourself wanting to change a file, you have
   mis-scoped — route to the skill that owns the change instead.
1. **Classify the request.** Determine symptom vs question vs change vs idea vs
   review ask. If it is empty or unclassifiable, ask one clarifying question.
2. **Resolve the repo-state signals** for any fork the request touches — read
   `docs/plans/plans.json`, look for the `specs/<id>/` dir, check whether a
   running target is named. Gather only what the routing decision needs; do not
   bulk-read.
3. **Pick exactly one route** from the table using the request class + the
   resolved signals. Hold the evidence that decided it (the file you found or
   did not find, the signal that tipped a fork).
4. **Render the single routing gate** (below), then act on the choice.
5. **Hand off — the mechanism depends on the destination's invocation mode.**
   - **Model-invocable route** (the default) → invoke the chosen `/ce-*` skill
     via the `Skill` tool, passing the user's request through as its argument.
     You do not do the downstream skill's work yourself; you start it.
   - **Human-initiated route** — `/ce-patch`, `/ce-auto-build`, `/ce-probe-sec`,
     `/ce-probe-perf`, `/ce-ship-release`, and `/ce-doc-audit`
     carry `disable-model-invocation: true`, so the `Skill` tool cannot start them by
     design (these lanes write code, act on live targets, or cut releases, and
     must be human-pulled). Do **not** attempt a `Skill` handoff, and do **not**
     report them as "not installed" — they are installed, just human-only. Hand
     *back*: print the exact command for the user to run —
     `Run:  /ce-patch <request>` — with the one-line reason from the table.
   - **Not-installed route** (e.g. the `product-discovery` trio when that plugin
     is absent) → tell the user the `claude plugin install …` command.
6. **Never chain.** Route to one skill and stop. The routed skill (or the user)
   decides what comes next.

## Human-in-the-Loop — light

One consent gate, with the routing decision read back and its evidence shown, so
the call is decidable in the dialog. Routing is reversible and low-stakes (the
user can pick another route or abort before any skill runs), so this is not a
material-class gate — but it is still located and labeled (Gate 1 of 1).

**Gate 1 of 1 — confirm the route**

```
Routing to /<skill> because <the evidence that decided it — e.g. "docs/plans/
checkout/specs/03-export/ exists, so the failing export is a planned feature">.

  • Proceed        → I hand off to /<skill> now with your request (or, for a
                     human-initiated lane, I hand you the exact command to run).
  • Pick another   → choose a different route from the table (I show the fits).
  • Abort          → I stop and route nowhere; nothing runs.
```

Never skip this gate, even when the route feels obvious — the read-back is how
the user catches a mis-read repo signal before a skill starts. If the user picks
another route, re-render the gate for the new choice.

## Escalation

- **Ambiguous fork:** if the plan-existence signal is genuinely unresolvable
  (e.g. a partial `specs/` dir), present both candidate routes in the gate with
  the evidence for each and let the human decide — do not guess silently.
- **No good route:** if the request matches nothing in the table (it is not a
  coding, product, probe, review, or delivery task), say so plainly and stop;
  do not force a route. Routing nowhere is a valid outcome.
- **Request is really several tasks:** route the first/blocking one and tell the
  user the others exist; you never fan out into multiple skills from one call.

## Honest Limitations

- **Not an executor** — it does the work of no skill. Every real action happens
  in the routed skill, under that skill's own gates, locks, and write lease.
- **Only as good as the repo signals** — if `plans.json` is missing or a spec
  dir is half-written, the fork it informs degrades to the ambiguity path (the
  gate shows both routes), never to a silent wrong guess.
- **One hop, no orchestration** — it is not `/ce-auto-build`; it starts a single
  skill and stops. It does not sequence a pipeline or resume a run.
- **Writes nothing** — no artifact, no ledger line; its `allowed-tools`
  deliberately exclude `Write` and `Edit`. The only trace it leaves is the
  downstream skill it started.
