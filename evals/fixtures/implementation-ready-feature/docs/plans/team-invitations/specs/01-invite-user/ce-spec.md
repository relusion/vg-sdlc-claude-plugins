# 01-invite-user Spec

## Acceptance Criteria

### AC-1 - Admin creates a pending invitation
WHEN an admin creates an invitation with a team id, email address, and allowed role
THE system SHALL create a pending invitation with a stable id, team id, email, role, and `pending` status.

### AC-2 - Non-admins are denied [SECURITY: TZ-001]
WHEN a non-admin attempts to create an invitation
THE system SHALL reject the request before writing an invitation.

### AC-3 - Roles are constrained to the allowed set
WHEN an invitation is created with a role outside `admin`, `member`, or `viewer`
THE system SHALL reject the request.

### AC-4 - Pending invitations are listable [CONTRACT: IC-001]
WHEN pending invitations exist for multiple teams
THE system SHALL list only the pending invitations for the requested team.

## Test Cases

### TC-1 (proves AC-1) - modality: sdk - verification: auto
Call `create_invitation("team_1", "new@example.com", "viewer", actor_role="admin")`
and assert the returned invitation has a stable id, `team_1`, `new@example.com`,
`viewer`, and `pending`.

### TC-2 (proves AC-2) - modality: sdk - verification: auto
Call `create_invitation(..., actor_role="member")`, assert `PermissionError`, and
assert no invitation was stored.

### TC-3 (proves AC-3) - modality: sdk - verification: auto
Call `create_invitation(..., role="owner", actor_role="admin")` and assert
`ValueError`.

### TC-4 (proves AC-4) - modality: sdk - verification: auto
Create pending invitations for `team_1` and `team_2`, then assert
`list_pending_invitations("team_1")` returns only the pending invitation for
`team_1`.

## Design

Update `src/invitations.py` only. Keep the in-memory `INVITATIONS` store.
Add `ALLOWED_ROLES = {"admin", "member", "viewer"}`.
Change `create_invitation` to require keyword-only `actor_role`.
Raise `PermissionError` for non-admin actors before validation or writes.
Raise `ValueError` for disallowed roles.
Add `list_pending_invitations(team_id)`.

## Tasks

### T-1 - Add tests for the approved behavior (verifies: TC-1, TC-2, TC-3, TC-4)
Update `checks/invitations_check.py` test-first with TC-1 through TC-4.

### T-2 - Enforce authorization and role validation (verifies: TC-1, TC-2, TC-3)
Update `src/invitations.py` to require `actor_role`, enforce admin-only creation,
validate allowed roles, and preserve the pending invitation shape.

### T-3 - Add pending invitation listing (verifies: TC-4)
Add `list_pending_invitations(team_id)` returning pending invitations scoped to
the requested team.

## Traceability Matrix

| AC | Test cases | Tasks |
|---|---|---|
| AC-1 | TC-1 | T-1, T-2 |
| AC-2 | TC-2 | T-1, T-2 |
| AC-3 | TC-3 | T-1, T-2 |
| AC-4 | TC-4 | T-1, T-3 |

## Architecture Context

```json architecture-context
{
  "architecture_revision": null,
  "feature_id": "01-invite-user",
  "feature_mapping_sha256": null,
  "mapped_ids": {
    "actors": [],
    "components": [],
    "contracts": [],
    "data": [],
    "decisions": [],
    "deployments": [],
    "drivers": [],
    "dynamic": [],
    "flows": [],
    "gaps": [],
    "operations": [],
    "quality": [],
    "questions": [],
    "relationships": [],
    "risks": [],
    "security": [],
    "transitions": []
  },
  "mode": "not-required",
  "package_path": null,
  "package_receipt_sha256": null,
  "plan_contract_sha256": "ec23915b4b2c25ad5935892d7b3dacbe66dc370ed0f9883e16e84530ac5c5eff",
  "plan_revision": 1,
  "project_slug": "team-invitations",
  "reason": "This one-feature fixture has no cross-feature architecture driver.",
  "schema_version": 2
}
```
