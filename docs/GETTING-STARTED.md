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
  see [What It Costs](#what-it-costs) below for measured floors.

## Install

```bash
claude plugin marketplace add relusion/vg-sdlc-claude-plugins
claude plugin install core-engineering@vg-coding
```

The upstream idea/market skills (`/ce-idea-scout`, `/ce-idea-score`,
`/ce-market-scan`) ship as a small **companion** plugin. Install it only if you
also want the product-discovery front-end — the core engineering framework does
not need it:

```bash
claude plugin install product-discovery@vg-coding
```

Then open a project repository in Claude Code and invoke skills directly with
their `ce-` names, for example:

```text
/ce-ask Where is login rate limiting enforced?
/ce-impact Add CSV export to the orders report.
/ce-init --write
/ce-brief We need team invitations with role-based access.
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

**One command to remember in week one:** `/ce-go <what you want>`. It is the
front door — describe the outcome in plain language ("why does export fail",
"score this idea", "is this code safe to ship") and it inspects repo state (a
plan on disk? a spec for the named feature? a running target?), routes to the one
right skill, shows its reasoning, and asks you to confirm before it hands off. It
routes, never executes — so the practical surface you need to learn shrinks from
~30 skill names to one. The steps below are what `/ce-go` routes *to*; run them
directly once you know which you want.

```text
/ce-go The export job silently stops after a few hundred rows.
```

Expected output: a single routing gate — e.g. *"Routing to `/ce-debug`
because a failing component matches the diagnosis lane — Proceed / Pick another /
Abort"* — then it starts the chosen skill. It writes nothing itself.

1. Bootstrap repository policy:

   ```text
   /ce-init --write
   ```

   Expected output: `docs/plans/repo-profile.json`, `vc-policy.md`,
   `review-policy.md`, and `patterns.md` when missing, plus the
   `.claude/ce-write-scope.json` deny-only write-scope baseline (git internals
   and the lease file itself are never agent-writable) and `.gitignore`
   entries for the four runtime guard/session files
   (`.claude/ce-write-scope.json`, `.claude/ce-write-scope.session.json`,
   `.claude/ce-guard-log.jsonl`, `.claude/ce-session-model.json`) appended when
   absent.

2. Ask one grounded question:

   ```text
   /ce-ask Where is authentication enforced?
   ```

   Expected output: a short answer with `file:line` citations and no file
   writes.

3. Analyze one proposed change:

   ```text
   /ce-impact Add CSV export to the orders report.
   ```

   Expected output: affected components, blast radius, rough sizing, open
   questions, and a paste-ready summary.

4. If the work is real, start the planning path:

   ```text
   /ce-brief Add team invitations with role-based access.
   /ce-plan <brief-or-project-description>
   ```

   Expected output: `docs/briefs/<slug>.md`, then `docs/plans/<slug>/`.

5. If the work is genuinely small:

   ```text
   /ce-patch Fix the typo in the paid invoice status label.
   ```

   Expected output: an eligibility gate before code edits. If the change proves
   structural, the patch lane routes to `/ce-plan`. For a featherweight change
   (≤ 2 files, no auth/secrets/payments/migration/i18n/a11y surface), add
   `--express` for the one-gate express fold: a mechanical screen, a test-first
   edit behind a single combined gate, and one line in
   `docs/plans/express-log.jsonl` — no spec artifacts. A failed screen falls back
   to the full lane.

## Common First Runs

| Situation | Start Here | What You Get |
|---|---|---|
| I am using this plugin in a repo for the first time | `/ce-init --write` | Repo profile, starter SDLC policy artifacts, and the write-scope baseline |
| I need to understand code | `/ce-ask` | Cited answer, no writes |
| I need to refine a work item | `/ce-impact` | Blast-radius read and open questions |
| I have a raw feature idea | `/ce-brief` -> `/ce-plan` | Brief, plan, feature decomposition |
| I have an approved plan feature | `/ce-spec` -> `/ce-implement` | `ce-spec.md`, `tasks.json`, code, tests, verification |
| I need confidence before handoff | `/ce-review` + `/ce-verify` | Review findings and behavior-verification evidence |
| I need release readiness | `/ce-ship-deliver` -> `/ce-ship-release` | Delivery manifest and release decision package |
| I need a risk probe | `/ce-probe-infra`, `/ce-probe-sec`, `/ce-probe-perf`, or `/ce-ux-audit` (UX) | Evidence-backed findings within each probe boundary |
| I need hosted automation | Managed-agent flow | `spec-author` -> `spec-impl` -> `quality-gate` -> `release-coordinator` |

**Enforcement caveat:** plugin hooks (write leases, `git-guard`, deterministic
gate enforcement) do not load on the managed-agent surface. Use that
experimental path only when the host supplies equivalent sandboxing, approvals,
and policy enforcement; see
`managed-agent-cookbooks/ORCHESTRATION.md`.

For the full router, use `docs/USAGE-MATRIX.md`. For recipes with stop
conditions, use `docs/WORKFLOW-RECIPES.md`.

## What It Costs

Skills make model calls on your Claude plan or API key. Measured USD floors from
the live eval harness — on deliberately tiny fixture repos, so treat these as
floors, not averages; real repositories cost more (method, caveats, and
reproduction commands in [docs/BENCHMARKS.md](./BENCHMARKS.md)):

| Path | Measured floor (USD) |
|---|---|
| `/ce-ask` grounded answer · `/ce-impact` blast-radius read | ~$1 |
| `/ce-review` six-lens review of one feature | ~$2 |
| `/ce-plan` decomposition · `/ce-implement` one feature · `/ce-probe-infra` audit | ~$3 |
| `/ce-spec` one implementation-ready spec · `/ce-patch` lane | ~$4 |

Summing those floors, one tiny feature through plan → spec → implement →
review is ≈ $12 of model calls. Anything autonomous is budget-capped up front:
`/ce-auto-build` asks for a token budget at Stage 0, and executed evals refuse
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
  the guard sees a new session no longer owns it, auto-replaces it with the
  deny-only baseline, and asks you to approve **once** — no hidden JSON file to
  hunt down and hand-delete. A deny you *do* see means a **live** skill still
  holds the lease and the edit is outside its declared scope; let that skill
  finish or reconcile with it rather than forcing the write.

## Troubleshooting

| Symptom | Likely Cause | Next Step |
|---|---|---|
| A skill picked the wrong lane | The request was ambiguous or too broad | Invoke the intended skill directly, for example `/ce-impact ...` |
| `/ce-impact` refuses | The change description is too thin | Add subject, action, and desired outcome |
| `/ce-patch` stops before editing | The patch charter needs human consent or the change is structural | Answer the gate or promote to `/ce-plan` |
| `/ce-patch --express` dropped to the full lane | The mechanical express screen failed — more than 2 files, a reviewer-trigger surface, a cross-feature collision, or a dependency manifest | Expected: express is refused, never shrunk. Continue on the full `/ce-patch` lane, or narrow the change and re-run `--express` |
| A probe refuses | Target, environment, or authorization is unsafe or unclear | Use a local/dedicated target and pass the consent gate |
| A release is NO-GO | Verification, review, rollback, or supply-chain evidence is missing | Run the routed skill or have the human accept the gap |
| Claude asked me to confirm a `git push` / PR command | The `git-guard` hook backstop is working: shared-history operations (`git push`, `gh pr create`/`merge`, commits on the protected branch) default to an `ask` confirmation | Approve or refuse the prompt. To hard-enforce instead, set the per-operation env tiers `CE_GIT_GUARD_PUSH` / `CE_GIT_GUARD_PR` / `CE_GIT_GUARD_COMMIT` to `deny` (see `plugins/core-engineering/hooks/README.md`) |
| A file edit was denied mid-skill | A read-only skill holds the session write lease and the edit is outside its declared scope | If the lease belongs to a **dead** session (a different session set it, or it is older than the lease TTL), the guard auto-replaces it with the deny-only baseline and asks you **once** — approve and continue; there is no file to hand-delete. If it belongs to a **live** skill, the edit really is out of scope — let that skill finish or reconcile with its write contract. Only in the rare ambiguous case (the host sent no session id, or a pre-upgrade lease has no id) does the deny fall back to the manual lift the message names (delete `.claude/ce-write-scope.json`) |

## Where To Go Next

- `docs/README.md` for the audience-based documentation index.
- `docs/USAGE-MATRIX.md` for the canonical command router.
- `docs/WORKFLOW-RECIPES.md` for common end-to-end paths.
- `managed-agent-cookbooks/ORCHESTRATION.md` for experimental hosted-agent
  handoffs and host gates.
- `docs/HOW-IT-WORKS.md` for the framework model.
- `docs/ENTERPRISE-HARDENING.md` for control mapping and supply-chain evidence.
- `evals/README.md` for behavior-evaluation setup and grading.

## Contributing to the Framework

Working on this repository itself rather than using the plugin? Contributor
prerequisites, the full validation battery, and the authoring standards live
in [CONTRIBUTING.md](../CONTRIBUTING.md).
