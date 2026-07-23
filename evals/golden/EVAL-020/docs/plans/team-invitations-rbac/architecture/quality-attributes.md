# Quality Attributes: team-invitations-rbac

## Quality Scenarios

| Quality | Name | Attribute | Source | Stimulus | Environment | Response | Target | Tactic | Verification | Operations | Features | Evidence state | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| QA-001 | Invitation creation latency | latency | docs/briefs/team-invitations-rbac.md | A team administrator submits a valid invitation. | normal load | The API confirms invitation creation. | p95 under 500 ms | Keep authorization and persistence in a bounded synchronous path and use indexed PostgreSQL access. | /core-engineering:ce-probe-perf against the accepted criterion after implementation. | OP-001 | 02-team-invitations | inferred | `docs/briefs/team-invitations-rbac.md` |
| QA-002 | Unauthorized invitation denial | security | docs/briefs/team-invitations-rbac.md | An unauthorized caller submits an invitation. | any supported load | The request is denied before invitation persistence. | Unauthorized invitation attempts return HTTP 403 and create no invitation. | Cross SR-001 before the PostgreSQL invitation write. | Automated HTTP response and no-persistence assertions. | OP-001 | 01-roles-authz-foundation, 02-team-invitations | inferred | `docs/briefs/team-invitations-rbac.md`, `docs/plans/team-invitations-rbac/threat-model.md` |
| QA-003 | Idempotent invitation acceptance | reliability | docs/briefs/team-invitations-rbac.md | A recipient or client retries invitation acceptance. | normal operation, timeout recovery, or concurrent retry | The existing membership is returned without duplication. | Invitation acceptance is idempotent per invitation token. | Consume the token and create membership transactionally with a uniqueness invariant. | Automated replay, rollback, uniqueness, and concurrency tests. | OP-001, OP-002 | 01-roles-authz-foundation, 02-team-invitations | inferred | `docs/briefs/team-invitations-rbac.md`, `docs/plans/team-invitations-rbac/interaction-contract.md` |

## QA-001 — Invitation creation latency

The target is a written requirement, not measured performance evidence.

## QA-002 — Unauthorized invitation denial

The scenario binds the threat obligation to an observable no-write result.

## QA-003 — Idempotent invitation acceptance

IC-001 supplies the architecture-level invariant; specification owns concrete schema and test cases.

## Operations

| Operation | Name | Category | Responsibility | Owner | Signals | Failure domain | Target | Tactic | Runbook | Verification | Components / nodes | Quality | Features | Evidence state | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| OP-001 | Invitation and authorization path health | observability | Detect invitation latency, authorization denials, persistence failures, and unsafe token exposure. | unknown | request latency; HTTP outcome count; authorization denial count; transaction rollback count; redacted correlation identifier | single application request and PostgreSQL transaction path | Use QA-001, QA-002, and QA-003 as architecture thresholds and behavioral outcomes. | Emit correlated metrics and structured failures without invitation-token values. | unknown | Review the telemetry contract during specification and probe the implemented path during verification. | component=C-002, C-003, C-004; deployment_node=N-002, N-003 | QA-001, QA-002, QA-003 | 01-roles-authz-foundation, 02-team-invitations | inferred | `docs/briefs/team-invitations-rbac.md`, `docs/plans/team-invitations-rbac/threat-model.md`, `docs/plans/team-invitations-rbac/interaction-contract.md` |
| OP-002 | Invitation and membership recovery | recovery | Recover invitation and membership state without violating authorization or idempotency invariants. | unknown | database availability; transaction rollback count; acceptance replay outcome | PostgreSQL durable state and the shared application runtime | unknown | Preserve transactional rollback and uniqueness; define production recovery objectives before deployment. | unknown | Exercise rollback and replay behavior after implementation, then verify the accepted recovery target before deployment. | component=C-002, C-003, C-004; deployment_node=N-002, N-003 | QA-003 | 01-roles-authz-foundation, 02-team-invitations | inferred | `docs/plans/team-invitations-rbac/shared-context.md`, `docs/plans/team-invitations-rbac/interaction-contract.md` |

## Operability and Observability

The request path exposes latency, denial, persistence-failure, and replay signals, while production signal ownership and runbook ownership remain GAP-003.

## Capacity, Resilience, and Recovery

The brief records a p95 latency requirement and the fixture records one local application and database. Production capacity, topology, availability, and recovery targets remain explicit downstream gaps.

## Cost and Complexity Trade-Offs

The selected single-runtime direction avoids a new service boundary and migration while retaining logical seams for a later evidence-backed extraction.

## Quality and Operations Gaps

| Gap | Dimension | Type | Statement | Status |
|---|---|---|---|---|
| GAP-002 | operability | quality-target | Production backup policy, recovery point objective, and recovery time objective are not recorded. | open |
| GAP-003 | operability | ownership | Production operations ownership and runbook ownership are not recorded. | open |
