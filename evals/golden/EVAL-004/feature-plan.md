# Feature Plan: team-invitations-rbac

> Minimized golden copy of a real `/ce-plan` output, kept in-repo as a
> deterministic `plan-lint.py` replay gate (EVAL-004). Trimmed to the
> structural surface the lint reads; see EXAMPLES.md for provenance.

Two features, shipped in dependency order:

1. `01-roles-authz-foundation` — roles + the `authorize()` chokepoint and the
   shared `membership` store.
2. `02-team-invitations` — `invite` / `accept_invitation`, gated by feature
   `01-roles-authz-foundation`.

The `02→01` edge is a synchronous in-process call; the only cross-feature
durable noun is `membership` (see interaction-contract.md, IC-001).
