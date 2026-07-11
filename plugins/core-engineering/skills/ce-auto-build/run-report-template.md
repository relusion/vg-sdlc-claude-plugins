# Run Report Template — on-demand write-time template

Loaded by `auto-build/SKILL.md` at Stage 3 (End-Review) only, when the orchestrator writes
the run report — never on the common autonomous path. Write to
`docs/plans/<slug>/ce-auto-build/<date>-run.md`; do not reconstruct this structure from memory.

````markdown
# Auto-Build Run — <date> · <slug>

> Scope: <whole plan | range>   ·   Status: complete | halted (<reason>)
> Substrate: spawning orchestrator with plugin agents | spawning orchestrator with generic Task workers | in-context (spec/implement isolation relaxed)
> Worker selection: plugin agents (`spec-author`, `spec-impl`) | generic Task workers | in-context   ·   Degradation policy: best-effort | strict
> Checkpoint Mode: isolated-branch `auto-build/<slug>/<date>` | none   ·   not pushed, not on your branch
> Parallelism: off | worktree accepted | worktree requested -> sequential fallback
> Features: <built> built · <parked> parked · <failed> failed · <blocked> blocked

## Foundational Decisions (Kickoff)
| # | Unknown | Disposition | Decision | Promoted to |
|---|---|---|---|---|

## Capability Preflight
| Capability | Status | Tier | Disposition |
|---|---|---|---|

## Worktree Preflight
| Status | Parallel groups | Fallback/degradation |
|---|---|---|

## Decisions Made On Your Behalf
| D | Feature | Decision | Disposition | Class | Confidence | Reversible | Provisional? | Where |
|---|---|---|---|---|---|---|---|---|
> *Provisional?* = a `provisional (auto-build <date>)` ledger append awaiting end-review confirm/revert (a revert re-spawns the conservative downstream superset).

## Shared-Shape Reconciliations (§3.5) — additive-vs-breaking, surfaced as discrete decisions
| # | Feature | Shape | NEW/SHARED | Consumers | Per-consumer call | Challenge verdict | End-review confirm |
|---|---|---|---|---|---|---|---|
| SS-1 | 05 | OrderV2 (persisted) | SHARED | 03 reads `status`; migration 0007 | additive (new optional field) | accepted | confirmed |

## Challenges (Challenger) — mode: off | material-only | thorough
| # | Feature | Decision | Verdict | Resolution |
|---|---|---|---|---|
| C-1 | 03 | data store choice | weak-default | revised → indexed map per ADR-0005 |
| C-2 | 04 | retry policy | mis-classified | escalated → park (business) |

## Parked — Needs Your Input
| Feature | Blocking decision | Class | Dependents blocked |
|---|---|---|---|

## Verification (index — full evidence in each `specs/<id>/verification.md`)
One row per feature, **in ship order**, linking to its verification artifact.
| Feature | verification.md | Tests | Criteria met | Manual:judgment pending |
|---|---|---|---|---|

## Code Review (review gate) — mode: off | advisory [default] | blocking-on-high
| CR | Feature | Lens | Severity | Confidence | Finding | Disposition |
|---|---|---|---|---|---|---|
| CR-1 | 04 | security | high | confirmed | unparameterized query at orders.py:88 | blocked → fixed (retry 1) |
| CR-2 | 05 | correctness | high | suspected | possible null deref at cart.ts:42 (path not shown reachable) | recorded → end-review |

## Diagnoses (diagnose gate) — mode: off [default] | on
One row per failure root-caused before a retry or park.
| DX | Feature | Trigger | Cause @ file:line | Confidence | Class | Outcome |
|---|---|---|---|---|---|---|
| DX-1 | 04 | verify regression | cart.ts:88 | confirmed | bug | re-implemented (retry 1) → passed |
| DX-2 | 05 | review high-sev | api.py:30 | suspected | spec-gap | parked |

## Integration (verify)
(whole-suite · build · lint · criteria re-confirmation · journeys · bridges)

## Merge-Bar Verdict
This run, as landed, judged against your **exact CI merge bar** (`scripts/gate_runner.py`
over `plugins/core-engineering/merge-policy.json`) — computed at the end-review, BEFORE any
PR. Acknowledge-only: the bar reports; opening the PR stays your call. In `isolated-branch`
mode the committed `auto-build/<slug>/<date>` branch is judged against the run's Stage-0
integrity baseline; in `none` mode the bar cannot run (it judges committed state only) — say
so as a labeled degradation, never a fabricated verdict.

> Checkpoint Mode: isolated-branch | none
> Verdict: PASS | FAIL | not-run (Checkpoint Mode = `none`) | could-not-run (`<reason>`)
> Summary: <N>/<M> required integrity gates pass — integrity conjunct holds | FAILED
> base_sha: <sha>   ·   head_sha: <sha>   ·   change class: defaults
> policy: plugins/core-engineering/merge-policy.json (sha256 <first-12>)
> validity still owed: human | two-human  (attested by branch protection, never this run)

Full `--json` verdict (the reproducible-from-its-SHAs attestation the evidence pack embeds):

```json
{ "status": "pass", "change_class": "defaults", "base_sha": "...", "head_sha": "...",
  "policy": { "sha256": "...", "shipped_default": true },
  "gates": [ { "id": "spec-lint", "disposition": "required", "status": "pass" } ],
  "hard_failures": [], "advisory": [] }
```

## Degradations
(anything that ran reduced, recorded never silent: capability degradations, a
budget bound that went advisory, a consented **proceed-dirty** working-tree baseline
(Stage 0 step 6), a `status-board.py` generation failure, a gate that exit-2'd to the
artifact-only floor — each with the feature + reason)

## End-Review Record
(accepted / overridden / parked-resolved · date · by)
````
