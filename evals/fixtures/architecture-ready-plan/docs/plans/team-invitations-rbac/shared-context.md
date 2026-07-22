# Shared Context: team-invitations-rbac

## Codebase Profile

```yaml
codebase_profile:
  stack:
    language: Python
    framework: framework-neutral service functions
    deployment_target: Docker Compose application plus PostgreSQL
  public_interaction_surfaces:
    api_endpoints:
      - POST /teams/{team_id}/invitations
      - GET /teams/{team_id}/invitations
      - POST /invitations/{token}/accept
  data_surfaces:
    persistence_style: PostgreSQL transactions
    tables_or_collections: [memberships, invitations]
  integration_boundaries:
    - browser or API client to application service over HTTPS
  cross_cutting_layers: [authorization, persistence]
  baseline_delivery_health:
    deployment_target: deploy/compose.yaml
```

## Project Docs

- `docs/briefs/team-invitations-rbac.md`
- `docs/adr/0001-single-service-runtime.md`

## Known Pitfalls

- Invitation-token replay must not duplicate membership rows.
- Authorization is checked before invitation data is written.

## Architecture Disposition

| Decision | Triggers | Convergence | Iterations | Basis | Accepted decisions | Downstream consequence |
|---|---|---|---:|---|---|---|
| required | explicit-architecture-deliverable; trust-residency-or-sensitive-boundary; shared-data-ownership-or-migration | converged | 1 | Authorization, membership writes, and invitation acceptance require one reviewed cross-feature baseline. | `docs/adr/0001-single-service-runtime.md` | Publish a current approved architecture package before spec or auto-build. |

## Resolved Project Decisions

| # | Decision | Resolution | Origin | Detail |
|---|---|---|---|---|
| RPD-1 | Runtime boundary | One application runtime with logical components | plan team-invitations-rbac | ADR-0001 |
