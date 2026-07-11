# Interaction Contract: team-invitations-rbac

> Minimized golden re-projection (read-only), kept for the EVAL-004 plan-lint
> replay gate — H8 requires a multi-feature plan to carry this file, non-empty.

## Behavioural-Protocol Invariants

| IC-NNN | Shared noun | Idempotency | Producer / Consumer |
|---|---|---|---|
| IC-001 | `membership` | `accept_invitation` idempotent per invitation token | 01-roles-authz-foundation (owns store) / 02-team-invitations (writes via accept) |
