# 01-roles-authz-foundation — Roles and authorization foundation

**Specification route:** explicit

### Structured Metadata

```yaml
id: 01-roles-authz-foundation
title: Roles and authorization foundation
type: foundation
status: planned
final_complexity: Moderate
risk_profile: medium
boundary_owner: [security, persistence]
dependencies:
  hard: []
  soft: []
open_unknowns: []
```

### Scope

- Define the allowed team roles.
- Provide the `authorize(caller_id, team_id, capability)` chokepoint.
- Own membership persistence and idempotent membership creation.

### Excluded

- Organization-wide policy administration.
- Custom roles.

### Public / Data / Integration Surfaces

- `membership` `[system-or-append-only]` `[personal]` in PostgreSQL.
- In-process authorization interface consumed by invitation operations.

### Validation Target

- Unauthorized callers cannot mutate team membership or invitations.

### Run

```bash
/core-engineering:ce-spec 01-roles-authz-foundation
```
