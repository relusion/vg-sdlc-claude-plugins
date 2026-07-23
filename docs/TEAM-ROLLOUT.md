# Team Rollout

Pilot the lean path on representative work before standardizing it. The goal is
better cycle time and first-pass quality with unchanged human authority, not
maximum skill usage.

## 1. Choose a bounded pilot

Pick:

- one team and two to four weeks;
- repository work with known build/test commands;
- a mix of one small patch, one straightforward planned feature, and one
  feature with a real shared-design decision;
- named product, architecture, security, quality, documentation, and release
  owners.

Baseline cycle time, first-pass verification, review rework, and developer
satisfaction before rollout. Do not use invocation count as the value metric.

## 2. Adopt the smallest default

Teach three outcomes first:

1. understand/refine: ask or impact;
2. small fix: patch;
3. planned work: adaptive plan → compact implementation or explicit spec →
   implementation → independent review and verify.

`ce-brief` is optional. Architecture exploration and a governed baseline run
only when shared design is load-bearing. Documentation is generated from
verified behavior, audited when reader/operational risk warrants it, and the
release workflow runs last.

Keep one repository-owned `review-policy.md` that defines severity, required
reviewers, risk owners, and escalation. Keep normal build, test, lint, and
security jobs.

## 3. Configure authority before autonomy

Before enabling auto-build:

- name feature range, attempt/park limits, and budget;
- require real decisions to return as structured checkpoints;
- confirm product, architecture, security acceptance, destructive operations,
  scope, and release remain human-owned;
- treat deterministic PASS and clean negative evidence as automatic progress;
- treat deterministic failure or could-not-run as stop/route, never a
  confirmation dialog.

Review and verification may be orchestrated but must remain independent evidence
producers.

## 4. Add the merge bar deliberately

The composite action is the shortest GitHub integration:

```yaml
- uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
  with: { fetch-depth: 0 }
- uses: relusion/vg-sdlc-claude-plugins/action/merge-bar@<40-HEX-COMMIT-SHA>
```

That is not the whole control:

1. pin a reviewed full commit SHA;
2. keep the repository's build/test jobs required;
3. require the merge-bar status;
4. configure protected human review (the shipped conservative default is two
   approvals);
5. protect workflow and policy paths with CODEOWNERS or a ruleset;
6. configure the base-ref policy and declared dependency inputs.

The [merge-bar action guide](../action/merge-bar/README.md) covers cold start,
signed verdicts, and the checksum-pinned copy-in alternative. GitLab and Azure
ports are under [`templates/adopter-ci/`](../templates/adopter-ci/).

The bar proves configured artifact integrity, not compilation, test sufficiency,
security, or production readiness.

## 5. Validate live behavior honestly

Run the offline suite first:

```bash
python3 scripts/check.py --no-install-hooks
python3 scripts/portability_check.py
python3 scripts/eval_check.py
python3 -m unittest discover -s tests -q
```

Then run live scenarios from a clean reviewed commit with explicit budget.
[BENCHMARKS.md](./BENCHMARKS.md) distinguishes design verification from current
live evidence.

The scheduled live-eval workflow writes an evidence receipt on every run:

- `evidence_produced: true` only when a clean, non-dry, deterministically graded
  live summary exists for the run SHA;
- `false` for a missing secret, missing/invalid summary, or other skipped path.

The main-health canary checks the receipt and freshness, not only the GitHub
workflow conclusion. A green skipped run therefore cannot masquerade as fresh
behavioral evidence.

## 6. Measure the pilot

Use a small scorecard:

| Outcome | Metric | Evidence |
|---|---|---|
| Less context tax | Entry/companion token proxy and files loaded per workflow | Authoring check plus sampled run trace |
| Faster flow | Median time from accepted scope to verification handoff | Work-item timestamps and terminal events |
| Better first pass | Share passing verification without implementation reopen | Verification/task evidence |
| Less review rework | Confirmed findings requiring another loop | Review summary and retry events |
| Predictable automation | Complete, park, retry, abort, could-not-run rates | Metrics stream; missing stream is a gap |
| Useful experience | Repeat use among eligible developers and short satisfaction score | Opt-in pilot survey |

`python3 scripts/metrics_report.py --json` aggregates repository-recorded events.
It cannot infer whether an eligible developer chose not to use the workflow, so
keep the cohort and survey outside prompt telemetry.

Compare the lean path with the previous baseline on the same job types. A good
initial success criterion is materially lower prompt/review volume with no loss
in deterministic contract pass rate, seeded-defect recall, or human decision
quality.

## 7. Expansion rule

Expand only when:

- developers can choose the correct route without memorizing the catalog;
- compact versus explicit specification routes correctly;
- material architecture choices show sufficient evidence and remain
  human-owned;
- review and verification catch different defect classes without duplicate
  confirmation;
- release packages include required documentation/audit evidence;
- the scorecard improves without worse escaped defects or rework.

Otherwise fix or remove the highest-friction default before adding another
workflow.

## 8. Keeping controls live

Use the shipped drift workflow for post-merge plan/spec checks. Roll it out
advisory-first, triage existing findings, then arm failure. Route plan drift to
plan and spec drift to spec; the monitor does not repair artifacts.

Track scheduled live-eval evidence separately from ordinary CI health. A missing,
skipped, stale, or failed receipt is an evidence gap even if all offline checks
are green.

## Rolling back

Stop write-capable runs, preserve the working tree and receipts, and restore the
previously reviewed plugin bundle through the normal plugin-management process.
Plain Markdown/JSON artifacts remain in the repository.

Remove required CI status or policy only through the repository's normal
human-reviewed governance change. Do not delete evidence, bypass a live write
lease, or weaken deterministic policy to make an older workflow appear green.
