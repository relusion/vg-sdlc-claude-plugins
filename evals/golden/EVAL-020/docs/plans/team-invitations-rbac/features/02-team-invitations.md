# 02-team-invitations — Team invitations

**Specification route:** explicit

### Structured Metadata

```yaml
id: 02-team-invitations
title: Team invitations
type: user-facing
status: planned
final_complexity: Moderate
risk_profile: low
boundary_owner: []
dependencies:
  hard:
    - 01-roles-authz-foundation
  soft: []
open_unknowns: []
```

### Scope

- Authorized admins create and list pending invitations.
- Recipients accept an invitation token once and gain the selected role.
- Replayed acceptance returns the existing membership without duplicating it.

### Excluded

- Email delivery.
- Custom roles and invitation reminders.

### Public / Data / Integration Surfaces

- HTTPS create, list, and accept endpoints.
- `invitation` `[system-or-append-only]` `[personal]` in PostgreSQL.
- In-process authorization and membership interfaces from feature 01.

### Dependencies

- Hard: `01-roles-authz-foundation` — authorization and membership ownership.

### Validation Target

- Authorized creation, denied unauthorized creation, and idempotent acceptance.

### Run

```bash
/core-engineering:ce-spec 02-team-invitations
```
