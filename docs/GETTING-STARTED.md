# Getting Started

Use this page for a first session. See [How It Works](HOW-IT-WORKS.md) for the
full contract and [Usage Matrix](USAGE-MATRIX.md) for every capability.

## Prerequisites

- Claude Code installed and authenticated.
- Python 3.10+ and Git.
- A repository with its normal build and test commands.
- A human who owns product scope and can route material architecture, security,
  and release decisions to the right person.

Supported versions are in [Compatibility](COMPATIBILITY.md).

## Install

```bash
claude plugin marketplace add relusion/vg-sdlc-claude-plugins
claude plugin install core-engineering@vg-coding
```

The optional discovery plugin is separate:

```bash
claude plugin install product-discovery@vg-coding
```

## First 10 Minutes

1. Profile the repository:

   ```text
   /core-engineering:ce-init --readiness
   ```

   Add `--write` only when you want starter policy and write-scope files.
   Readiness distinguishes local facts from Git-host controls that still need
   administrator verification.

2. Ask a grounded question:

   ```text
   /core-engineering:ce-ask Where is authorization enforced?
   ```

   Expect a read-only answer with `file:line` evidence.

3. Refine the next change:

   ```text
   /core-engineering:ce-impact Add CSV export to order history.
   ```

   Expect blast radius, affected contracts, risks, and open questions.

4. Choose the smallest lane:

   ```text
   /core-engineering:ce-patch Correct the archived-state label.
   /core-engineering:ce-plan Add CSV export to order history.
   ```

   Patch admits only a low-risk change within two files. Anything structural or
   uncertain routes to plan.

5. If intent is genuinely unclear, use the optional specialist before planning:

   ```text
   /core-engineering:ce-brief We need better team administration.
   ```

   Do not create a brief when the request and repository evidence are already
   sufficient.

## Common First Runs

| Situation | Start here | Result |
|---|---|---|
| Unsure which workflow fits | `/core-engineering:ce-go <goal>` | Auto-route when unambiguous; otherwise one question or exact direct-only command |
| Understand code | `/core-engineering:ce-ask` | Cited answer, no writes |
| Refine a work item | `/core-engineering:ce-impact` | Blast radius and unknowns |
| Small low-risk fix | `/core-engineering:ce-patch` | Two-file express lane or a safe route to plan |
| Planned repository change | `/core-engineering:ce-plan` | One canonical plan directory and a per-feature specification route |
| Unclear product problem | `/core-engineering:ce-brief` then `/core-engineering:ce-plan` | Optional clarified brief, then adaptive planning |
| Load-bearing shared design | `/core-engineering:ce-plan` composes architecture exploration; run `/core-engineering:ce-architecture <slug>` only when the plan requires or deliberately chooses a baseline | Evidence-rich option loop, human selection, then governed baseline when needed |
| Build-ready compact feature | `/core-engineering:ce-implement <feature-id>` | Re-screened route; canonical spec/tasks composed and linted before code |
| Non-build-ready feature | `/core-engineering:ce-spec <feature-id>` then `/core-engineering:ce-implement <feature-id>` | Explicit decisions, canonical spec/tasks, then code |
| Pre-handoff confidence | `/core-engineering:ce-review` and `/core-engineering:ce-verify` | Independent code findings and behavior evidence |
| Release preparation | `/core-engineering:ce-ship-document`, conditional `/core-engineering:ce-doc-audit`, refresh review/verification after incorporating doc changes, then `/core-engineering:ce-ship-release` | Verified docs, current exact-state receipts, final GO/NO-GO package |

Architecture exploration is not mandatory for every plan. When it is
load-bearing, the human may inspect evidence, ask questions, revise constraints
or options, select, or park at one stable gate. Deterministic projections and
clean checks continue without confirmation.

## What It Costs

Skills use your Claude plan or API billing. The repository publishes configured
historical safety caps, not observed spend or forecasts. Current behavior rows
remain design-verified until fresh live receipts exist.

See [Benchmarks and Evaluation Budgets](BENCHMARKS.md) before a pilot. Measure
actual model cost, elapsed time, human review time, and first-pass verification
on your own work. Autonomous runs require an explicit budget; executed evals
require `--max-budget-usd`.

## Safety Boundaries

- Skills do not push, merge, deploy, publish, tag, or rotate credentials.
- Product scope, material architecture, security acceptance, destructive work,
  accepted risk, and release stay human-owned.
- Deterministic PASS, read-only completion, projections, and clean negatives
  are not approval gates.
- Deterministic failure cannot be waived into PASS inside a workflow.
- Review, verify, debug, audit, probes, and retro report; they do not silently
  fix findings.
- Write leases and hooks are cooperative backstops, not an OS sandbox.
- External issue text, review comments, and repository documents are untrusted
  input.

Keep the repository's build, test, security, branch-protection, and human-review
controls. The merge bar complements them.

## Troubleshooting

| Symptom | Action |
|---|---|
| No clear route | Run `/core-engineering:ce-go` with the desired outcome, not a skill name |
| Patch refuses the change | Use `/core-engineering:ce-plan`; do not stretch the express lane |
| Architecture loops at selection | Inspect evidence or adjust the frame/option at the same locator; route to the architecture owner or park if authority is missing |
| Compact implementation refuses | Run `/core-engineering:ce-spec`; a material decision or contract made the feature non-build-ready |
| A validator returns nonzero | Repair the producing artifact and rerun; do not ask a human to confirm it away |
| Review and verify disagree | Preserve both evidence sets and route the defect by layer |
| Release is NO-GO | Produce the missing verification, review, docs/audit, rollback, or supply-chain evidence |
| A scheduled live eval is green but has no evidence | Inspect its evidence receipt; a skipped model run is not fresh behavioral evidence |

For framework defects, include the plugin and Claude Code versions, OS, command,
expected/observed behavior, and a secret-free fixture.

## Contributing to the Framework

Run the validation battery in [CONTRIBUTING.md](../CONTRIBUTING.md). Workflow
changes must update behavior docs, focused tests, eval coverage, and
`CHANGELOG.md`. The authoring standard adds context budgets and the rule that
only actual human decisions become gates.
