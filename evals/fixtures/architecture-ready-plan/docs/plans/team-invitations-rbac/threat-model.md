# Threat Model: team-invitations-rbac

## Trust Boundaries

| Boundary | Entry point | Untrusted input | Auth required |
|---|---|---|---|
| HTTPS API | invitation create/list/accept endpoints | team id, email, role, token | admin for create/list; token for accept |

## Secrets & Data-Classes

| Durable noun | Data-class | Owning feature |
|---|---|---|
| membership | personal | 01-roles-authz-foundation |
| invitation | personal | 02-team-invitations |

## Security Targets

Unauthorized invitation attempts return HTTP 403 and create no invitation.

## Per-Feature Security Obligations

```yaml
security_obligations:
  - feature: 01-roles-authz-foundation
    threat_ids: [TZ-001]
    surface_kinds: [authz, validation]
  - feature: 02-team-invitations
    threat_ids: [TZ-002]
    surface_kinds: [authz, secrets, validation]
```

### TZ-001 — Central authorization chokepoint

Membership and role operations deny callers without the required team capability.

### TZ-002 — Invitation boundary and bearer token

Invitation inputs are validated, tokens are not logged, and creation is authorized
before persistence.
