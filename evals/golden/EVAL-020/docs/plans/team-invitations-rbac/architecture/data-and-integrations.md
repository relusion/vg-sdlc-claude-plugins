# Data and Integrations: team-invitations-rbac

## Data Ownership and Lifecycle

| ID | Durable noun / data set | Data class | Source of truth | Writers | Readers | Retain / Export / Erase | Plan trace | Features | Evidence state | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| DATA-001 | membership | personal | C-004 | C-002, C-003 | C-002, C-003 | owned-by:01-roles-authz-foundation / owned-by:01-roles-authz-foundation / owned-by:01-roles-authz-foundation | feature-plan.md#durable-state-closure | 01-roles-authz-foundation, 02-team-invitations | inferred | `docs/plans/team-invitations-rbac/feature-plan.md`, `docs/plans/team-invitations-rbac/interaction-contract.md` |
| DATA-002 | invitation | personal | C-004 | C-002 | C-002 | owned-by:02-team-invitations / owned-by:02-team-invitations / owned-by:02-team-invitations | feature-plan.md#durable-state-closure | 02-team-invitations | inferred | `docs/plans/team-invitations-rbac/feature-plan.md`, `docs/plans/team-invitations-rbac/features/02-team-invitations.md` |

## Integration Flows

| Flow | Producer | Consumer | Protocol / medium | Data | Data entities | Source of truth | Failure behavior | Contract refs | Plan trace | Features | Evidence state | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| IF-001 | C-001 | C-002 | HTTPS | invitation command; invitation token | DATA-002 | C-004 | Caller receives an explicit HTTP failure and no success is implied | TZ-002 | feature-plan.md#journey-map | 02-team-invitations | recorded | `docs/plans/team-invitations-rbac/feature-plan.md`, `docs/plans/team-invitations-rbac/threat-model.md` |
| IF-002 | C-002 | C-003 | in-process call | caller id; team id; capability; membership command | DATA-001 | C-004 | Authorization denial stops before persistence | TZ-001, TZ-002 | feature-plan.md#dependency-flow | 01-roles-authz-foundation, 02-team-invitations | recorded | `docs/plans/team-invitations-rbac/feature-plan.md`, `src/auth.py` |
| IF-003 | C-002 | C-004 | PostgreSQL transaction | invitation record; membership record | DATA-001, DATA-002 | C-004 | The transaction rolls back; replay returns the existing membership | IC-001, TZ-002 | feature-plan.md#durable-state-closure | 01-roles-authz-foundation, 02-team-invitations | inferred | `docs/plans/team-invitations-rbac/interaction-contract.md`, `deploy/compose.yaml` |

## Flow Details

### IF-001 — Invitation API boundary

**Evidence state:** recorded.

The client sends create, list, or acceptance input over the plan's public HTTPS
surface. C-002 validates the input and returns an explicit response.

### IF-002 — Authorization and membership boundary

**Evidence state:** recorded. **Source of truth:** C-004.

C-002 calls C-003 in-process before protected writes. A denial ends the workflow and
preserves the existing invitation and membership state.

### IF-003 — Transactional persistence

**Evidence state:** inferred.

C-002 persists invitation state and uses the membership invariant owned by C-003. The
IC-001 idempotency key is the invitation token, with uniqueness for team and user.

## Consistency, Idempotency, and Concurrency

IC-001 is copied from the plan-owned interaction contract. Invitation acceptance is
idempotent per token, and membership uniqueness is enforced for a team/user pair. The
architecture does not introduce an exactly-once network claim or a second source of truth.

## Security and Privacy Re-Projection

TZ-001 requires the central authorization chokepoint for membership and role operations.
TZ-002 covers validation, authorization, and invitation-token handling at the HTTPS
boundary. Both `membership` and `invitation` retain the plan-owned `personal` data class;
this package does not reassign either value.

## Data and Integration Gaps

None for the planned synchronous service and PostgreSQL boundary. Email delivery remains
excluded and therefore has no architecture flow.
