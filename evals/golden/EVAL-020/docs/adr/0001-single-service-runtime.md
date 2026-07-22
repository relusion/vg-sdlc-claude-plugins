# ADR-0001 — Keep RBAC and Invitations in One Service Runtime

Status: accepted

## Context

The plan adds two tightly related features to a small Python service. Both use the
same PostgreSQL database and are deployed together today.

## Decision

Keep authorization, membership, and invitation responsibilities in one application
runtime, with logical component boundaries and a shared PostgreSQL data store.

## Consequences

- Authorization remains an explicit chokepoint that invitation operations call.
- A later service split requires a new plan and ADR.
- One deployment can affect both feature areas, so verification covers their shared
  transaction boundary.
