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
2. CI uploads the full run records **as a workflow artifact** named
   `eval-live-<run id>` — including `summary.json`, the distilled per-scenario
   verdicts. CI never commits to the repository.
3. When updating BENCHMARKS, copy that `summary.json` here as
   `<YYYY-MM-DD>-<profile>-summary.json` and cite the CI run id in the doc.

## Summary schema (`schema_version: 1`)

- `run_id` — the run's timestamp id (or CI out-dir id). A single CI run's
  `summary.json` carries this at top level; a curated summary that AGGREGATES
  several per-scenario local runs omits it at top level and puts `run_id` on
  each scenario instead (as `2026-06-27-smoke-summary.json` does).
- `dry_run` — must be `false` for the file to count as live evidence
- `max_budget_usd` — the hard per-scenario cap the run enforced (top-level for a
  single run; per-scenario in an aggregated summary)
- `scenarios[]` — `id`, `skill`, `status` (`pass`/`failed`), `returncode`, and
  (required on a `pass`) `run_id` — the provenance needle in
  `scripts/product_layer_check.py` only counts a scenario as live evidence when
  it carries `status: pass`, `returncode: 0`, and a `run_id`; `failure_kind`
  (`budget-exceeded` / `auth-error` / `claude-error`) is absent on a pass

A BENCHMARKS row may cite a live result only if a summary here (or a CI
artifact) records it; everything else stays labeled
**design-verified, not live-run**.
