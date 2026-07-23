# 01-roles-authz-foundation — Roles & authorization foundation

**Specification route:** explicit

### Structured Metadata

```yaml
id: 01-roles-authz-foundation
title: Roles & authorization foundation
type: foundation
final_complexity: Moderate
risk_profile: medium
boundary_owner: [security]
dependencies:
  hard: []
  soft: []
```

Introduces roles, `add_member`, and the `authorize(caller_id, capability)`
chokepoint every later feature gates on. Owns the shared `membership` store.
