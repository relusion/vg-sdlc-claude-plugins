# Project Brief — Team Invitations with RBAC

## Project Description

Team administrators invite a person by email, choose an existing team role, and
see the pending invitation. The recipient accepts the invitation once and becomes
a team member with the selected role.

## Success Criteria

- Under normal load, invitation creation completes at **p95 under 500 ms**.
- **Unauthorized invitation attempts return HTTP 403 and create no invitation.**
- **Invitation acceptance is idempotent per invitation token.**

## Scope

- Role and authorization foundation.
- Invitation creation, listing, and acceptance.
- Email delivery is outside this fixture; the API returns the token to a test
  harness standing in for a notification adapter.

## Constraints

- Extend the repository's existing Python service and PostgreSQL deployment.
- Keep product, security-risk, and deployment approval human-owned.
