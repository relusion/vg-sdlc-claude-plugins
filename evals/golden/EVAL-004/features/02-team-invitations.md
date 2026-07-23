# 02-team-invitations — Team invitations

**Specification route:** explicit

### Structured Metadata

```yaml
id: 02-team-invitations
title: Team invitations
type: user-facing
final_complexity: Moderate
risk_profile: low
dependencies:
  hard:
    - 01-roles-authz-foundation
  soft: []
```

`invite(caller_id, invitee, role)` and `accept_invitation(token, user_id)`,
gated by feature 01's `authorize()`. Accept is idempotent per invitation token.
