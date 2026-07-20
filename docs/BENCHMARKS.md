# Benchmarks & Measured Costs

What this framework's quality claims rest on, with numbers you can reproduce.
Two layers: an **offline enforcement floor** that runs free in CI on every
change, and **live behavior evals** that execute real skills against real
models on known-answer fixture repos. Floors, not marketing: the fixtures are
deliberately tiny, so treat every number as a lower bound.

All dollar amounts in this document are US dollars (USD).

## The offline enforcement floor (free, every commit)

These run in CI on every push and PR, and locally via the commands shown —
no model calls, stdlib-only Python:

| Gate | What it proves | Scale |
|---|---|---|
| `scripts/check.py` | manifests parse; skill/agent frontmatter; forked-gate byte-identity from `fork-manifest.json`; model-policy two-way consistency; merge-policy validity; README catalog matches the corpus; delegates every lint below | repository-wide |
| `scripts/corpus_lint.py` | no stale public names, no unknown `/ce-*` references, skeleton headings present, companion-file references resolve | repository corpus |
| `scripts/authoring_check.py` | the [skill-authoring](./contributing/SKILL-AUTHORING.md) vocabulary: HITL heading enum, gate-label sanity, `<date>` placeholder, concept canon, router-cluster clauses, size/description caps, glossary two-copy sync, material-gate locators | skill corpus |
| `scripts/portability_check.py` | every shipped hook/gate script is stdlib-only and runs with zero Claude Code present | all shipped scripts |
| `scripts/supply_chain_check.py` | SHA-pinned CI actions (incl. the adopter template), checksum-verified secret scanning, dependency-gate fork integrity, merge-bar anti-deregistration, live-eval workflow safety, evidence prompts present | supply-chain control set |
| `tests/` unit suite | gate scripts, hooks policy, merge bar, write lease, SCA guard, eval tooling, catalog drift | unit suite |
| `scripts/eval_check.py` | eval scenario catalog + fixtures valid; golden lint/schema replays pass deterministically; coverage ratchet (scenario or dated waiver per skill) | catalog + registered golden gates |

Reproduce all of it: `python3 scripts/check.py && python3 -m unittest discover -s tests -q`.

## Live behavior evals

Every current catalog scenario is listed. The 2026-06-27 batch (executed via
`scripts/eval_run.py --execute`) recorded ten passing live runs, with
per-scenario provenance committed at
[`evals/results/2026-06-27-smoke-summary.json`](../evals/results/2026-06-27-smoke-summary.json)
— each resolving to a run id whose record shows `status=pass`. Every passing run
was then converted into deterministic output/artifact checks so regressions are
catchable without re-spending. Budgets are hard caps the runner enforces. A row
without a citable *current* live run is labeled **design-verified, not
live-run**: its claim rests on the fixture plus deterministic checks, not on
recorded model behavior.

**Recency ratchet.** A `pass (DATE)` row is only as trustworthy as the code
behind it, so `scripts/product_layer_check.py` auto-degrades one: whenever the
scenario's skill directory (or its fixture) carries a committed change dated
after the cited run, the row *must* be relabeled **design-verified, not
live-run** until a fresh run is recorded. The check judges committed git history
alone — no model, no API — and fails loud rather than green on a shallow clone,
so a stale claim can never coast on age. Because a subsequent hardening pass rewrote
every eval skill after 2026-06-27, all ten of that batch's rows have degraded
here to design-verified: the recorded run is still committed evidence, but the
current skill is no longer the one that produced it. Re-running the smoke profile
(and committing the summary) is the path back to a live label.

| Scenario | Skill | Proves | Budget | Live result |
|---|---|---:|---:|---|
| EVAL-001 | `/ce-ask` | grounded, `file:line`-cited answer, no writes | $1.00 | design-verified, not live-run |
| EVAL-002 | `/ce-impact` | grounded blast-radius read with citations + unknowns | $1.00 | design-verified, not live-run |
| EVAL-003 | `/ce-impact` | refuses a too-thin work item instead of guessing | $1.00 | design-verified, not live-run |
| EVAL-004 | `/ce-plan` | full plan directory: registry, plan JSON, threat model, interaction contract, feature files | $3.00 | design-verified, not live-run |
| EVAL-005 | `/ce-spec` | `spec.md` + `tasks.json` that pass `spec-lint.py` with full traceability | $4.00 | design-verified, not live-run |
| EVAL-006 | `/ce-implement` | test-first implementation: tasks done, tests green, `verification.md` | $3.00 | design-verified, not live-run |
| EVAL-007 | `/ce-review` | finds the seeded high-severity IDOR, `blocking_high: 1`, machine summary | $2.00 | design-verified, not live-run |
| EVAL-008 | `/ce-probe-infra` | dated infra report + summary JSON + evidence for Dockerfile/K8s/Terraform findings | $3.00 | design-verified, not live-run |
| EVAL-009 | `/ce-patch` | admits a benign two-file fix, proves red→green, and stops at one diff/evidence gate | $4.00 | design-verified, not live-run |
| EVAL-010 | `/ce-patch` | refuses schema/durable-state work before editing and routes to `/ce-plan` | $2.00 | design-verified, not live-run |
| EVAL-011 | `/ce-ask` | resists adversarial repo instructions; cites real files, repeats no injected text | $1.00 | design-verified, not live-run |
| EVAL-012 | `/ce-impact` | ignores injected override/exfiltration text in fixture docs | $1.00 | design-verified, not live-run |
| EVAL-013 | `/ce-ask` | cross-stack: TypeScript authorization tracing | $1.00 | design-verified, not live-run |
| EVAL-014 | `/ce-impact` | cross-stack: OpenAPI/SQL contract impact | $1.00 | design-verified, not live-run |
| EVAL-015 | `/ce-ask` | cross-stack: CI workflow grounding | $1.00 | design-verified, not live-run |
| EVAL-016 | `/ce-probe-deps` | flags the OSV-listed `urllib3==1.24.1` pin, lists skipped unpinned, no false "clean bill" | $1.00 | design-verified, not live-run |
| EVAL-017 | `/ce-auto-build` | fixed sequential three-feature run: success, product park, retry exhaustion, schema-v2 state, and final human review | $20.00 | design-verified, not live-run |
| EVAL-018 | `/ce-humanize` | rewrites generic prose while preserving facts, links, and structure | $1.00 | design-verified, not live-run |

Honest failure log from the same batch — kept because it calibrated the
budgets and the runner behavior:

| Run | Result | What it taught |
|---|---|---|
| EVAL-003 @ $0.25, EVAL-008 @ $1.00, EVAL-005 @ $2.00, EVAL-009 @ $2.00 | budget exceeded | the recommended budgets above; the runner now fails fast below a scenario's recommendation |
| EVAL-003 `--bare` | failed before plugin execution (`Not logged in`) | `--bare` is for API-key/CI auth contexts, not subscription-keychain local runs |

## Measured cost floors

Model spend per skill from the 2026-06-27 recorded runs above — on **tiny
fixture repos**, so these are floors; real repositories cost more with size and
iteration:

| Skill path | Measured floor |
|---|---|
| `/ce-ask` · `/ce-impact` | ~$1 |
| `/ce-review` (one feature) | ~$2 |
| `/ce-plan` · `/ce-implement` (one feature) · `/ce-probe-infra` | ~$3 |
| `/ce-spec` (one feature) · `/ce-patch` lane | ~$4 |

Summing the floors, one tiny feature through plan → spec → implement → review
is **≈ $12** of model calls. Everything autonomous is budget-capped up front
(`/ce-auto-build` Stage 0; `eval_run.py` refuses `--execute` without
`--max-budget-usd`).

## What is *not* yet measured — the honest boundary

- **Eight scenarios have never had a recorded live pass:** adversarial
  `EVAL-011`/`EVAL-012`, cross-stack `EVAL-013`–`015`, dependency probing
  `EVAL-016`, auto-build `EVAL-017`, and humanization `EVAL-018`. Their current
  claims rest on fixtures and deterministic checks, not recorded model behavior.
- **Coverage:** the 2026-06-27 batch recorded live passes for 8 of 30 skills then shipped (the corpus is 32 today)
  (10 scenario passes — `/ce-impact` and `/ce-patch` each contribute two), but
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
  uploading run records and a distilled `summary.json` as CI artifacts — CI
  never commits results, curated summaries land in `evals/results/`, and raw
  outputs stay out of git (`evals/runs/` is gitignored). Until a CI run id is
  citable, every number here remains the distilled record of the 2026-06-27
  manual batch, with curated excerpts in [EXAMPLES.md](./EXAMPLES.md).

## Reproduce a live run

```bash
# one cheap scenario
python3 scripts/eval_run.py --execute --scenario EVAL-001 --max-budget-usd 1.00

# the read-only smoke profile
python3 scripts/eval_run.py --execute --profile smoke --max-budget-usd 5.00
```

Runs land in `evals/runs/<run-id>/` with per-scenario metadata (result,
budget, failure kind). Grade saved outputs with
`python3 scripts/eval_check.py`.
