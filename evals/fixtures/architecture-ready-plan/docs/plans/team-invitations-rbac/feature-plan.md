# Feature Plan: team-invitations-rbac

## Overview

Extend the existing Python service with a reusable role and authorization foundation,
then add invitation creation, listing, and idempotent acceptance.

## Project Context

The source brief is `docs/briefs/team-invitations-rbac.md`.

## Journey Map

**Journey: Invite and join a team** · primary modality: http

| Step | Surface | Owned By | Reachability | Modality | Expected observable |
|---|---|---|---|---|---|
| 1 | `POST /teams/{team_id}/invitations` | 02-team-invitations | authorization foundation available | http | HTTP 201 with a stable invitation id and token |
| 2 | `GET /teams/{team_id}/invitations` | 02-team-invitations | invitation persisted | http | pending invitation appears once |
| 3 | `POST /invitations/{token}/accept` | 02-team-invitations | membership writer available | http | membership exists with the invited role; replay is unchanged |

## Durable-State Closure

| Noun | Access-mode | Data-class | revisit | amend | retire | retain | export | erase |
|---|---|---|---|---|---|---|---|---|
| membership | system-or-append-only | personal | owned-by:01-roles-authz-foundation | excluded:role changes are separately planned | owned-by:01-roles-authz-foundation | owned-by:01-roles-authz-foundation | owned-by:01-roles-authz-foundation | owned-by:01-roles-authz-foundation |
| invitation | system-or-append-only | personal | owned-by:02-team-invitations | excluded:pending invitations are replaced, not edited | owned-by:02-team-invitations | owned-by:02-team-invitations | owned-by:02-team-invitations | owned-by:02-team-invitations |

## Dependency Flow

```text
01-roles-authz-foundation
    |
    v
02-team-invitations
```

The dependency is a synchronous in-process authorization call plus transactionally
consistent writes to the shared PostgreSQL deployment.

## Feature Table

| # | Feature | Type | Final Complexity | Risk | Hard Deps | File |
|---:|---|---|---|---|---|---|
| 1 | 01-roles-authz-foundation | foundation | Moderate | medium | — | `features/01-roles-authz-foundation.md` |
| 2 | 02-team-invitations | user-facing | Moderate | low | 01-roles-authz-foundation | `features/02-team-invitations.md` |

## Execution Checklist

- [ ] 01-roles-authz-foundation
- [ ] 02-team-invitations

## Notes

- plan-tier: light; candidate review folded into final approval.
- Email delivery and production-region selection are outside this fixture.
