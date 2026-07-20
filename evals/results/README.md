# Curated live-eval summaries

The committed, citable record of live eval runs. Raw run output never lands
in git (`evals/runs/` is gitignored by policy); this directory holds only the
**distilled summaries** a human curates when refreshing
[docs/BENCHMARKS.md](../../docs/BENCHMARKS.md).

## The flow

1. A live run executes — either locally
   (`python3 scripts/eval_run.py --execute --profile smoke --max-budget-usd 2.00`)
   or in CI via the `eval-live` workflow (manual dispatch or the weekly
   schedule; requires the `ANTHROPIC_API_KEY` Actions secret).
2. The runner writes detailed `metadata.json` and a small, commit-ready
   `summary.json`. CI uploads both in a workflow artifact named
   `eval-live-<run id>-<attempt>`; CI never commits to the repository.
3. When updating BENCHMARKS, copy the runner-generated `summary.json` here as
   `<YYYY-MM-DD>-<profile>-summary.json`, commit it unchanged, and cite the CI
   run id (or local run directory) in the doc.

## Summary schema (`schema_version: 1`)

- `run_id` — the runner-generated immutable timestamp id, independent of the
  chosen output-directory name. A single run's
  `summary.json` carries this at top level; a curated summary that AGGREGATES
  several per-scenario local runs omits it at top level and puts `run_id` on
  each scenario instead (as `2026-06-27-smoke-summary.json` does).
- `git_head` — the exact repository commit loaded by a single CI run. Local
  dirty-worktree runs must not claim that the commit contains their uncommitted
  changes; leave them unpromoted until rerun from committed state.
- `source_clean` — `true` only when the source repository had no tracked or
  untracked changes before or after model calls and HEAD stayed fixed.
- `dry_run` — must be `false` for the file to count as live evidence
- `started_at` / `completed_at` — UTC timestamps for the run. A BENCHMARKS
  `pass (DATE)` claim must use the `completed_at` calendar date.
- `grade_status` / `grade_returncode` — the aggregate deterministic grader result;
  promotion requires `"pass"` and `0`, not just a successful Claude process.
- `graded_scenarios` — the scenario ids covered by that passing deterministic
  grade. A scenario is not promotable merely because another output in the same
  batch passed.
- `max_budget_usd` — the hard **per-scenario** cap the run enforced (top-level
  for a single batch; per-scenario in an aggregated summary). A profile can
  authorize up to this cap once for every selected scenario; it is not a batch
  total or a record of actual spend.
- `scenarios[]` — `id`, `skill`, `status` (`pass`/`failed`), `returncode`, and
  a per-scenario `run_id` for aggregated local summaries. A single-run summary
  may instead use the top-level `run_id`; a per-scenario value takes precedence.
  Aggregated local summaries may put `git_head`, `source_clean`, and grade fields
  on each scenario when their source runs differ; use `graded: true` to bind that
  scenario to its passing grade.
  `scripts/product_layer_check.py` counts a scenario as live evidence only when
  the file is tracked and unchanged from `HEAD`, the model and deterministic
  grader passed, the completion date matches the claim, the source was clean
  and anchored to an existing full commit with no later relevant contract
  changes, and the run id identifies exactly one local run or CI batch;
  `failure_kind`
  (`budget-exceeded` / `auth-error` / `timeout` / `git-state-error` /
  `claude-error`) is absent on a pass

A BENCHMARKS row may cite a live result only if a summary here (or a CI
artifact) records it; everything else stays labeled
**design-verified, not live-run**.

The 2026-06-27 summary predates this receipt contract. Its raw run directories
were not retained, so it is historical context only and cannot be promoted by
adding missing fields after the fact.
