# Real Outputs

Every excerpt below is a **real captured output** — from the historical live
eval batch of 2026-06-27 or from the committed golden artifacts — not a mockup.
Each carries its provenance and a command that reruns the same scenario or
deterministic check. Fixtures are tiny by design; the point is the *shape and
discipline* of the output, not scale.

All dollar amounts in this document are US dollars (USD).

Every example here is indexed in `docs/examples-manifest.json` and checked by
`scripts/docs_drift.py` in CI. The two deterministic entries are replayed on
every push; the two live excerpts are historical snapshots and are not replayed
without an explicit paid model run. The checker also fails if this page grows a
`Provenance:` line with no manifest entry. See [Benchmarks](BENCHMARKS.md) for
the current live-evidence status; none of the historical live rows is labeled
current after subsequent skill changes.

## 1. `/core-engineering:ce-ask` — a grounded answer, cited, no writes

Provenance: historical live `EVAL-001`, 2026-06-27, $1.00 cap,
`minimal-service` fixture. Excerpt (opening of the actual answer):

> **TL;DR:** Login rate limiting is enforced in `app.py` inside the `login()`
> function, which calls `rate_limiter.allow(username)` before authenticating
> and returns HTTP 429 when the per-username attempt count exceeds the limit
> (`app.py:10-11`). The actual counting logic lives in the `RateLimiter`
> class in `auth.py:9-16`. The limit is set to 5 attempts per username at
> module load (`app.py:5`).
>
> **Key files**
> - `app.py:5,9-15` — wires up a module-level `RateLimiter(limit=5)` and enforces it as the first step of `login()`.
> - `auth.py:9-16` — the `RateLimiter` class: holds the per-username counter and decides allow/deny.
> - `checks/auth_check.py:4-7` — the test that pins the behavior: 5 attempts return 401, the 6th returns 429.

The full answer also walks the mechanism step-by-step and closes with a
"known unknowns / caveats" section — the *no evidence → no claim* discipline.

Rerun the current scenario (paid model call):
`python3 scripts/eval_run.py --execute --scenario EVAL-001 --max-budget-usd 1.00`

## 2. `/core-engineering:ce-review` — a confirmed security finding, triage left to the human

Provenance: historical live `EVAL-007`, 2026-06-27, $2.00 cap,
`review-target` fixture (seeded IDOR). Excerpt (the actual close-out):

> ## Code Review complete: order-cancellation — diff-only (advisory)
>
> **Findings:** 1 (1 high [1 confirmed, 0 suspected], 0 medium, 0 low)
> **Suppressed:** 0 · **Calibration:** `review-policy.md` absent — uncalibrated
> **Report:** `code-review.md` · **Machine summary:** `review-summary.json` (`status: blocked`, `blocking_high: 1`, `blocking_route: implement`)
>
> **CR-1 — Any actor can cancel any order** · `service.py:8-10`
> (`diff.patch:3-5`) · **High · Security (IDOR / broken access control) ·
> confirmed** — `cancel_order(order, actor_id)` accepts the authorization
> principal `actor_id` but never compares it to `order.owner_id` … Verified
> reachable by trace: `cancel_order(victim_order, attacker_id)` cancels an
> order the actor doesn't own.

Note the disciplines visible in one screen: confirmed-vs-suspected evidence
states, a machine-readable summary a pipeline can gate on, honest
"uncalibrated" self-labeling, and *findings-not-verdicts* — the review blocks
and routes (`/core-engineering:ce-implement` with the suggested fix) but the human triages.

Rerun the current scenario (paid model call):
`python3 scripts/eval_run.py --execute --scenario EVAL-007 --max-budget-usd 2.00`

## 3. `/core-engineering:ce-spec` — an implementation-ready spec that passes its own lint

Provenance: committed golden artifact `evals/golden/EVAL-005/` (a minimized
real `/core-engineering:ce-spec` output, kept in-repo as a deterministic gate). Excerpt from
`specs/01-invite-user/ce-spec.md`:

> ## AC-001
> WHEN a team admin submits an email address and role
> THE system SHALL create a pending invitation for that team.
>
> ## AC-002 [SECURITY: TZ-001]
> WHEN a non-admin attempts to create a team invitation
> THE system SHALL reject the request.
>
> ## AC-003 [SURFACE: pending invitations list]
> WHEN an invitation is created
> THE pending invitations list SHALL show the email, role, and pending status without clipping.

EARS-shaped criteria, each tagged to its origin (a threat-model zone, a
surface contract) and each traced to a test case with a declared verification
modality — the traceability `spec-lint.py` mechanically enforces. The golden
directory also carries the `tasks.json` and `threat-model.md` the spec
composes with.

Reproduce (no model call — deterministic replay):
`python3 scripts/eval_check.py` runs `spec-lint.py` over this golden artifact
on every CI push. To regenerate the live equivalent:
`python3 scripts/eval_run.py --execute --scenario EVAL-005 --max-budget-usd 4.00`

## 4. The golden-replay layer — frozen artifacts, replayed through their lints

The `/core-engineering:ce-spec` golden above is one of **six** deterministic gates
`scripts/eval_check.py` replays on every CI push — a frozen known-good artifact
run back through the same lint or schema check its producing skill emits, with no
model call. When a validator changes (a new `plan-lint` hard check, a
`review-summary.json` field rename), the frozen goldens catch the regression for
free. Each is a minimized real skill output kept in-repo under `evals/golden/`:

| Gate | Golden artifact | Replayed through | Asserts |
|---|---|---|---|
| EVAL-004 | `evals/golden/EVAL-004/` (plan dir) | `plan-lint.py --require-architecture-direction --json` | the frozen plan is structurally well-formed and binds a current-schema, hash-bound architecture workbench and human direction (H1–H10 pass) |
| EVAL-005 | `evals/golden/EVAL-005/specs/01-invite-user/` | `spec-lint.py --json` | the frozen spec passes referential-integrity + traceability |
| EVAL-007 | `evals/golden/EVAL-007/review-summary.json` | `json_fields` schema check | `status: blocked`, integer `blocking_high: 1`, `blocking_route: implement`, and the `CR-1` IDOR finding shape auto-build gates on |
| EVAL-008 | `evals/golden/EVAL-008/infra-summary.json` | `json_fields` schema check | `status: pass`, `blocking_hard: 0`, all three formats detected, secrets redacted |
| EVAL-009 | `evals/golden/EVAL-009/express.json` | `json_fields` schema check | the admitted two-file scope and requested label fix stay frozen for the express-only lane |
| EVAL-020 | `evals/golden/EVAL-020/docs/plans/team-invitations-rbac/architecture/` | `architecture-lint.py --json` | the strict schema-v2 package is source-current, its deterministic projections and approval receipt match, and trigger-required context/dynamic/trust/transition/operations structures or typed gaps resolve through each feature mapping |

Provenance: committed golden artifacts, each a minimized real skill output
distilled from the live eval batch of 2026-06-27 (`evals/runs/` originals):
EVAL-004 from `20260627-060527Z`, EVAL-007 from `20260627-045826Z`, and EVAL-008
from `20260627-053616Z`. EVAL-009 was replaced in 2026-07 when the patch contract
became express-only, and EVAL-020 was added with the architecture capability;
both current goldens are design-verified and await a fresh live run. The plan
golden is trimmed to the structural surface `plan-lint.py` reads.

Reproduce (no model call — deterministic replay):
`python3 scripts/eval_check.py` replays all six goldens and prints
`6 golden gate(s)`. A mutated golden (a broken `plan.json`, a dropped
`blocking_high`, a changed admitted file, or a dangling architecture endpoint)
turns the run red — see
`tests/test_eval_check.py::GoldenGates`.
