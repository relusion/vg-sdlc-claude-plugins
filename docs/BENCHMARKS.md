# Benchmarks & Evaluation Budgets

What this framework's quality claims rest on, with checks you can reproduce.
Two layers: an **offline enforcement floor** that runs free in CI on every
change, and **live behavior evals** that execute real skills against real
models on known-answer fixture repos. The dollar values are configured safety
caps, not observed usage or forecasts.

All dollar amounts in this document are US dollars (USD).

## The offline enforcement floor (free, every commit)

These run in CI on every push and PR, and locally via the commands shown —
no model calls, stdlib-only Python:

| Gate | What it proves | Scale |
|---|---|---|
| `scripts/check.py` | manifests parse; skill/agent frontmatter; forked-gate byte-identity from `fork-manifest.json`; model-policy two-way consistency; merge-policy validity; README catalog matches the corpus; delegates corpus, authoring, product-layer, and supply-chain checks | repository-wide |
| `scripts/corpus_lint.py` | no stale public names, no unknown `/ce-*` references, skeleton headings present, companion-file references resolve | repository corpus |
| `scripts/authoring_check.py` | the [skill-authoring](./contributing/SKILL-AUTHORING.md) vocabulary: HITL heading enum, gate-label sanity, `<date>` placeholder, concept canon, router-cluster clauses, size/description caps, glossary two-copy sync, material-gate locators | skill corpus |
| `scripts/portability_check.py` | every shipped hook/gate script is stdlib-only and runs with zero Claude Code present | all shipped scripts |
| `scripts/supply_chain_check.py` | SHA-pinned CI actions (incl. the adopter template), checksum-verified secret scanning, dependency-gate fork integrity, merge-bar anti-deregistration, live-eval workflow safety, evidence prompts present | supply-chain control set |
| `tests/` unit suite | gate scripts, hooks policy, merge bar, write lease, SCA guard, eval tooling, catalog drift | unit suite |
| `scripts/eval_check.py` | eval scenario catalog + fixtures valid; golden lint/schema replays pass deterministically; coverage ratchet (scenario or dated waiver per skill) | catalog + registered golden gates |

Reproduce all rows above:

```bash
python3 scripts/check.py --no-install-hooks
python3 scripts/portability_check.py
python3 scripts/eval_check.py
python3 -m unittest discover -s tests -q
```

## Live behavior evals

Every current catalog scenario is listed. The 2026-06-27 batch (executed via
`scripts/eval_run.py --execute`) originally recorded ten passing live runs.
The committed historical summary retains eight curated run assertions:
[`evals/results/2026-06-27-smoke-summary.json`](../evals/results/2026-06-27-smoke-summary.json)
— each naming a run id that was curated as `status=pass`. The raw runs were not
committed, and that older schema does not record the clean source,
deterministic-grade, completion-time, or current-contract fields now required
for promotion. It is therefore historical context, not independently
reproducible evidence or a current pass. New receipts
must carry a unique run id, clean full-commit source anchor, successful model
process, and successful deterministic grade bound to that scenario. The receipt
commit must contain the latest scenario skill, fixture, scenario catalog, runner,
and grader contract. A row without citable *current* evidence is labeled
**design-verified, not live-run**.

**Recency ratchet.** A `pass (DATE)` row is only as trustworthy as the code
behind it, so `scripts/product_layer_check.py` auto-degrades one: whenever the
scenario's skill directory (or its fixture) carries a committed change dated
after the cited run, the row *must* be relabeled **design-verified, not
live-run** until a fresh run is recorded. The check judges committed git history
alone — no model, no API — and fails loud rather than green on a shallow clone.
Promotion separately verifies the receipt's exact commit contains the current
skill, fixture, catalog, runner, and grader, so a newly dated row cannot revive an
old receipt. Because a subsequent hardening pass rewrote
every eval skill after 2026-06-27, all ten of that batch's rows have degraded
here to design-verified: the historical run remains useful diagnostic evidence,
but neither its code nor its receipt schema matches the current contract.
Re-running the smoke profile from a clean commit (and committing the summary) is
the path back to a live label.

| Scenario | Skill | Proves | Per-scenario cap | Live result |
|---|---|---:|---:|---|
| EVAL-001 | `/core-engineering:ce-ask` | grounded, `file:line`-cited answer, no writes | $1.00 | design-verified, not live-run |
| EVAL-002 | `/core-engineering:ce-impact` | grounded blast-radius read with citations + unknowns | $1.00 | design-verified, not live-run |
| EVAL-003 | `/core-engineering:ce-impact` | refuses a too-thin work item instead of guessing | $1.00 | design-verified, not live-run |
| EVAL-004 | `/core-engineering:ce-plan` | full plan directory: registry, plan JSON, threat model, interaction contract, feature files | $3.00 | design-verified, not live-run |
| EVAL-005 | `/core-engineering:ce-spec` | `ce-spec.md` + `tasks.json` that pass `spec-lint.py` with full traceability | $4.00 | design-verified, not live-run |
| EVAL-006 | `/core-engineering:ce-implement` | test-first implementation: tasks done, tests green, `verification.md` | $3.00 | design-verified, not live-run |
| EVAL-007 | `/core-engineering:ce-review` | finds the seeded high-severity IDOR, `blocking_high: 1`, machine summary | $2.00 | design-verified, not live-run |
| EVAL-008 | `/core-engineering:ce-probe-infra` | dated infra report + summary JSON + evidence for Dockerfile/K8s/Terraform findings | $3.00 | design-verified, not live-run |
| EVAL-009 | `/core-engineering:ce-patch` | admits a benign two-file fix, proves red→green, and stops at one diff/evidence gate | $4.00 | design-verified, not live-run |
| EVAL-010 | `/core-engineering:ce-patch` | refuses schema/durable-state work before editing and routes to `/core-engineering:ce-plan` | $2.00 | design-verified, not live-run |
| EVAL-011 | `/core-engineering:ce-ask` | resists adversarial repo instructions; cites real files, repeats no injected text | $1.00 | design-verified, not live-run |
| EVAL-012 | `/core-engineering:ce-impact` | ignores injected override/exfiltration text in fixture docs | $1.00 | design-verified, not live-run |
| EVAL-013 | `/core-engineering:ce-ask` | cross-stack: TypeScript authorization tracing | $1.00 | design-verified, not live-run |
| EVAL-014 | `/core-engineering:ce-impact` | cross-stack: OpenAPI/SQL contract impact | $1.00 | design-verified, not live-run |
| EVAL-015 | `/core-engineering:ce-ask` | cross-stack: CI workflow grounding | $1.00 | design-verified, not live-run |
| EVAL-016 | `/core-engineering:ce-probe-deps` | flags the OSV-listed `urllib3==1.24.1` pin, lists skipped unpinned, no false "clean bill" | $1.00 | design-verified, not live-run |
| EVAL-017 | `/core-engineering:ce-auto-build` | fixed sequential three-feature run: success, product park, retry exhaustion, schema-v2 state, and final human-review gate | $20.00 | design-verified, not live-run |
| EVAL-018 | `/core-engineering:ce-humanize` | rewrites generic prose while preserving facts, links, and structure | $1.00 | design-verified, not live-run |
| EVAL-019 | `/core-engineering:ce-go` | routes a bounded low-risk change to direct-only `/core-engineering:ce-patch`, then stops without writes | $1.00 | design-verified, not live-run |
| EVAL-020 | `/core-engineering:ce-architecture` | loads and lints the written plan, renders the evidence-first Scope Confirmation gate, and stops without publishing before human approval; its frozen package separately passes `architecture-lint.py` | $3.00 | design-verified, not live-run |

Honest failure log from the same batch — kept because it calibrated the
budgets and the runner behavior:

| Run | Result | What it taught |
|---|---|---|
| EVAL-003 @ $0.25, EVAL-008 @ $1.00, EVAL-005 @ $2.00, EVAL-009 @ $2.00 | budget exceeded | the recommended budgets above; the runner now fails fast below a scenario's recommendation |
| EVAL-003 `--bare` | failed before plugin execution (`Not logged in`) | `--bare` is for API-key/CI auth contexts, not subscription-keychain local runs |

## Historical successful-run budget caps

The 2026-06-27 curated summary retained only each run's configured
`max_budget_usd`; it did not retain actual token usage or spend. These values
are ceilings that were sufficient for those tiny fixture runs, not measured
costs, floors, or forecasts:

| Skill path | Configured per-scenario cap |
|---|---|
| `/core-engineering:ce-ask` · `/core-engineering:ce-impact` | $1 |
| `/core-engineering:ce-review` (one feature) | $2 |
| `/core-engineering:ce-plan` · `/core-engineering:ce-implement` (one feature) · `/core-engineering:ce-probe-infra` | $3 |
| `/core-engineering:ce-spec` (one feature) · historical `/core-engineering:ce-patch` run | $4 |

Summing those historical caps, plan → spec → implement → review authorized up
to **$12** across four separate model calls. Actual spend is unknown. Everything
autonomous is budget-capped up front
(`/core-engineering:ce-auto-build` Stage 0; `eval_run.py` refuses `--execute` without
`--max-budget-usd`).

## What is *not* yet measured — the honest boundary

- **Ten scenarios have never had a committed live pass:** adversarial
  `EVAL-011`/`EVAL-012`, cross-stack `EVAL-013`–`015`, dependency probing
  `EVAL-016`, auto-build `EVAL-017`, humanization `EVAL-018`, and front-door
  routing `EVAL-019`, plus architecture generation `EVAL-020`. Their current
  claims rest on fixtures and deterministic checks, not committed or citable
  model evidence.
- **Coverage:** the 2026-06-27 batch recorded live passes for 8 of 30 skills then
  shipped (the corpus is 32 today)
  (10 scenario passes — `/core-engineering:ce-impact` and `/core-engineering:ce-patch` each contribute two), but
  the recency ratchet has since degraded all ten of those rows to
  design-verified because that hardening pass changed every one of those
  skills, so no row currently carries a live label. The idea/decide/market
  genre, the probes beyond infra (deps included), verify, onboard,
  and the ship genre have no live behavioral run at all. These uncovered skills
  are not deferred to one cliff-edge date: `evals/coverage-allowlist.json` now
  stages them across a `burndown_schedule` (2026-09-30 dialog/fixture unblocks →
  2026-10-31 golden plan/spec fixtures → 2026-11-30 ship-genre fixtures →
  2027-03-31 runtime-harness probes), each tier capped so coverage burns down on
  a schedule the `eval_check.py` ratchet enforces.
- **A live CI path now exists but has recorded no run yet:** the `eval-live`
  workflow (manual dispatch + weekly schedule) executes the smoke profile with
  a hard budget cap once the `ANTHROPIC_API_KEY` Actions secret is configured,
  uploading run records and the runner-generated `summary.json` as CI artifacts — CI
  never commits results, curated summaries land in `evals/results/`, and raw
  outputs stay out of git (`evals/runs/` is gitignored). Until a CI run id is
  citable, the only dollar evidence here remains the configured caps from the
  2026-06-27 manual batch; actual spend was not retained. Curated excerpts
  remain in [EXAMPLES.md](./EXAMPLES.md).

## Reproduce a live run

```bash
# one cheap scenario
python3 scripts/eval_run.py --execute --scenario EVAL-001 --max-budget-usd 1.00

# the seven-scenario read-only smoke profile: $1 cap per call, up to $7 total
python3 scripts/eval_run.py --execute --profile smoke --max-budget-usd 1.00
```

Runs land in `evals/runs/<run-id>/` with detailed `metadata.json`, a
commit-ready `summary.json`, per-scenario outputs, and isolated fixture copies.
Unless `--skip-check` is used, the runner grades the saved outputs and records
that result in both receipts.
