# 01-invite-user Spec

## Acceptance Criteria

## AC-001
WHEN a team admin submits an email address and role
THE system SHALL create a pending invitation for that team.

## AC-002 [SECURITY: TZ-001]
WHEN a non-admin attempts to create a team invitation
THE system SHALL reject the request.

## AC-003 [SURFACE: pending invitations list]
WHEN an invitation is created
THE pending invitations list SHALL show the email, role, and pending status without clipping.

## Test Cases

## TC-001
modality: sdk
verification: auto
(proves AC-001)
Call the invitation creation function as an admin and assert a pending invitation is returned.

## TC-002
modality: sdk
verification: auto
(proves AC-002)
Call the invitation creation function as a non-admin and assert authorization is rejected.

## TC-003
modality: browser
verification: manual:harness-gap
(proves AC-003)
Render the pending invitations list and inspect the assembled surface for clipping or overlap.

## Tasks

## T-001
Implement invitation creation and authorization checks.

## T-002
Render pending invitations in the team member list.

## Traceability Matrix

| AC | TC | Task |
|---|---|---|
| AC-001 | TC-001 | T-001 |
| AC-002 | TC-002 | T-001 |
| AC-003 | TC-003 | T-002 |
