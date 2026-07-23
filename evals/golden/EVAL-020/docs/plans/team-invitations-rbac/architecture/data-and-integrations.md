# Data and Integrations: team-invitations-rbac

## Data Ownership and Lifecycle

| Data | Durable noun / data set | Class | Source of truth | Writers | Readers | Retain / Export / Erase | Consistency | Storage | Residency | Backup / recovery | Transitions | Plan trace | Features | Evidence state | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DATA-001 | membership | personal | C-004 | C-002, C-003 | C-002, C-003 | owned-by:01-roles-authz-foundation / owned-by:01-roles-authz-foundation / owned-by:01-roles-authz-foundation | Membership creation is unique per team and user and is coordinated transactionally with invitation acceptance. | existing PostgreSQL data store | Production residency is not recorded; GAP-001 owns closure. | Production backup and recovery targets are not recorded; GAP-002 owns closure. | — | feature-plan.md#durable-state-closure | 01-roles-authz-foundation, 02-team-invitations | inferred | `docs/plans/team-invitations-rbac/feature-plan.md`, `docs/plans/team-invitations-rbac/interaction-contract.md`, `deploy/compose.yaml` |
| DATA-002 | invitation | personal | C-004 | C-002 | C-002 | owned-by:02-team-invitations / owned-by:02-team-invitations / owned-by:02-team-invitations | Invitation token consumption and membership creation complete in one acceptance transaction. | existing PostgreSQL data store | Production residency is not recorded; GAP-001 owns closure. | Production backup and recovery targets are not recorded; GAP-002 owns closure. | — | feature-plan.md#durable-state-closure | 02-team-invitations | inferred | `docs/plans/team-invitations-rbac/feature-plan.md`, `docs/plans/team-invitations-rbac/features/02-team-invitations.md`, `docs/plans/team-invitations-rbac/interaction-contract.md` |

## Integration Flows

| Flow | Name | Producer | Consumer | Protocol / mode | Data | Data entities | Source of truth | Failure | Timeout / retry | Contract realizations | Security realizations | Plan trace | Features | Evidence state | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| IF-001 | Invitation API request | C-001 | C-002 | HTTPS / synchronous | invitation command; invitation token | DATA-002 | C-004 | The caller receives an explicit HTTP failure and no success is implied. | A caller may retry only under the invitation-token idempotency behavior realized by CTR-001. | — | SR-002 | feature-plan.md#journey-map | 02-team-invitations | recorded | `docs/plans/team-invitations-rbac/feature-plan.md`, `docs/plans/team-invitations-rbac/threat-model.md`, `docs/plans/team-invitations-rbac/shared-context.md` |
| IF-002 | Authorization and membership call | C-002 | C-003 | Python call / in-process | caller identity; team identifier; required capability; membership command | DATA-001 | C-004 | Authorization denial stops the request before any invitation or membership persistence. | The in-process result is returned in the same request; callers do not bypass a denial. | — | SR-001, SR-002 | feature-plan.md#dependency-flow | 01-roles-authz-foundation, 02-team-invitations | recorded | `docs/plans/team-invitations-rbac/feature-plan.md`, `docs/plans/team-invitations-rbac/threat-model.md`, `src/auth.py` |
| IF-003 | Invitation and membership transaction | C-002 | C-004 | PostgreSQL transaction / data-access | invitation record; membership record | DATA-001, DATA-002 | C-004 | The transaction rolls back; replay returns the existing membership without duplication. | Retry is safe only through the idempotent token and unique membership contract. | CTR-001 | SR-001, SR-002 | feature-plan.md#durable-state-closure | 01-roles-authz-foundation, 02-team-invitations | inferred | `docs/plans/team-invitations-rbac/interaction-contract.md`, `docs/plans/team-invitations-rbac/feature-plan.md`, `deploy/compose.yaml` |

## Flow Details

### IF-001 — Invitation API request

The public request carries team, email, role, or token input into the application boundary.

### IF-002 — Authorization and membership call

The logical component boundary is explicit even though both responsibilities share one runtime.

### IF-003 — Invitation and membership transaction

The existing PostgreSQL store is the source of truth for both durable nouns.

## Consistency, Idempotency, and Concurrency

Invitation acceptance consumes one token and creates at most one team membership through a transaction and uniqueness invariant; authorization denial terminates before a durable write.

## Trust Boundaries

| Boundary | Name | Type | Description | Inside | Outside | Crossing flows | Residency | Features | Evidence state | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| TB-001 | Public API boundary | trust | Untrusted invitation and bearer-token input crosses from a user-controlled client into the application. | C-002, C-003, C-004, N-002, N-003 | A-001, A-002, C-001, N-001 | IF-001 | Production processing residency is tracked by GAP-001. | 02-team-invitations | recorded | `docs/plans/team-invitations-rbac/threat-model.md`, `docs/plans/team-invitations-rbac/shared-context.md` |
| TB-002 | Authorization chokepoint | authorization | Invitation orchestration crosses the central capability check before protected persistence. | C-003 | C-002 | IF-002 | Logical in-process boundary within the selected single application runtime. | 01-roles-authz-foundation, 02-team-invitations | recorded | `docs/plans/team-invitations-rbac/threat-model.md`, `docs/adr/0001-single-service-runtime.md` |

## Security and Privacy Re-Projection

| Realization | Obligation | Boundaries | Actors | Components | Integrations | Data | Tactics | Verification | Features | Evidence state | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| SR-001 | TZ-001 | TB-002 | A-001 | C-002, C-003, C-004 | IF-002, IF-003 | DATA-001, DATA-002 | Evaluate the required team capability before protected persistence; Stop on denial without writing invitation or membership state | Automated capability-denial assertions prove HTTP 403 and no durable write. | 01-roles-authz-foundation, 02-team-invitations | inferred | `docs/plans/team-invitations-rbac/threat-model.md`, `docs/plans/team-invitations-rbac/feature-plan.md` |
| SR-002 | TZ-002 | TB-001, TB-002 | A-001, A-002 | C-001, C-002, C-003, C-004 | IF-001, IF-002, IF-003 | DATA-002 | Validate invitation input; Do not log invitation tokens; Authorize invitation creation before persistence | Automated validation, redaction, denial, and no-write assertions cover the invitation boundary. | 02-team-invitations | inferred | `docs/plans/team-invitations-rbac/threat-model.md` |

## Interaction Contract Realizations

| Realization | Obligation | Relationships | Integrations | Dynamic scenarios | Data | Behavior | Failure | Compatibility | Verification | Features | Evidence state | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CTR-001 | IC-001 | R-003, R-004 | IF-003 | DS-001 | DATA-001, DATA-002 | Invitation acceptance consumes one token and creates at most one membership per team and user. | A replay returns the existing membership, while a failed transaction creates neither a partial acceptance nor a duplicate. | The plan-owned IC-001 remains authoritative for both feature specifications and any later evolution. | Replay, uniqueness, rollback, and concurrent-acceptance tests after specification. | 01-roles-authz-foundation, 02-team-invitations | recorded | `docs/plans/team-invitations-rbac/interaction-contract.md`, `docs/plans/team-invitations-rbac/feature-plan.md` |

## Security and Privacy Summary

The architecture realizes both plan-owned threat obligations through a public API boundary and an explicit authorization chokepoint. This is design traceability, not security acceptance.

## Data and Integration Gaps

Coverage: data=complete, integrations=complete, security=complete, contracts=complete
