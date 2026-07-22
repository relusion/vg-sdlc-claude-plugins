# Interaction Contract: team-invitations-rbac

## Behavioural-Protocol Invariants

| IC-NNN | Edge / shared noun | Medium | Idempotency | Concurrency | Producer / Consumer |
|---|---|---|---|---|---|
| IC-001 | shared noun: `membership` | PostgreSQL transaction | Invitation acceptance is idempotent per invitation token. | unique membership per team and user | 02-team-invitations / 01-roles-authz-foundation |

## Per-Feature Interaction Obligations

```yaml
interaction_obligations:
  - feature: 01-roles-authz-foundation
    ic_ids: [IC-001]
    kinds: [idempotency, concurrency]
  - feature: 02-team-invitations
    ic_ids: [IC-001]
    kinds: [idempotency, concurrency]
```
