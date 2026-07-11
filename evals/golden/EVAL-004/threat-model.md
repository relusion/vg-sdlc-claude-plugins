# Threat Model: team-invitations-rbac

> Minimized golden re-projection (read-only), kept for the EVAL-004 plan-lint
> replay gate — H8 requires a multi-feature plan to carry this file, non-empty.

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
