# Quality Attributes: team-invitations-rbac

## Quality Scenarios

| ID | Attribute | Evidence state | Source | Stimulus | Environment | Response | Target | Tactic | Verification | Features |
|---|---|---|---|---|---|---|---|---|---|---|
| QA-001 | latency | inferred | `docs/briefs/team-invitations-rbac.md` | An administrator submits an invitation | normal load | The API confirms invitation creation | p95 under 500 ms | Keep the synchronous path bounded and use indexed PostgreSQL access | `/core-engineering:ce-probe-perf after implementation` | 02-team-invitations |
| QA-002 | security | inferred | `docs/plans/team-invitations-rbac/threat-model.md` | An unauthorized caller submits an invitation | any supported load | The request is denied without an invitation write | Unauthorized invitation attempts return HTTP 403 and create no invitation. | Invoke C-003 before C-004 persistence | Automated HTTP response and persistence assertion | 01-roles-authz-foundation, 02-team-invitations |
| QA-003 | reliability | inferred | `docs/plans/team-invitations-rbac/interaction-contract.md` | A recipient replays invitation acceptance | normal operation or client retry | The existing membership is returned without duplication | Invitation acceptance is idempotent per invitation token. | Consume the token and create membership transactionally with uniqueness | Automated replay and concurrency tests | 01-roles-authz-foundation, 02-team-invitations |

## QA-001 — Invitation creation latency

**Evidence state:** inferred — the target is recorded, while the tactic and verification
route are architecture synthesis.

The target is a stated requirement, not a measurement. Specification should preserve a
measurable HTTP criterion; runtime proof belongs to a consented performance profile.

## QA-002 — Authorization before persistence

**Evidence state:** inferred — the security target is recorded, while its realization
through C-003 before C-004 is architecture synthesis.

The HTTP response and absence of a new invitation row make this security obligation
deterministically testable without asking a reviewer to judge whether it is secure.

## QA-003 — Idempotent acceptance

**Evidence state:** inferred — IC-001 is recorded, while the transactional tactic and
verification route are architecture synthesis.

Replay and concurrent acceptance tests verify the IC-001 behavior against the shared
PostgreSQL source of truth.

## Operability and Observability

The application must expose explicit HTTP failures and preserve enough structured event
metadata to correlate invitation requests without logging invitation tokens. Exact metric
and alert names remain feature-level design inputs for `/core-engineering:ce-spec`.

## Capacity, Resilience, and Recovery

No infrastructure size or recovery-time target is invented. The recorded topology keeps
application and database failure domains visible, while QA-001 and QA-003 provide the
source-backed latency and retry behaviors that downstream verification owns.

## Cost and Complexity Trade-Offs

One application deployment avoids a new network hop and operational unit. The trade-off is
a shared deployment blast radius for authorization and invitations, accepted in ADR-0001.

## Quality Coverage Gaps

None relative to the written requirements. Unstated cloud sizing, RTO/RPO, and alert-owner
targets are not architecture claims and must be planned before they become binding.
