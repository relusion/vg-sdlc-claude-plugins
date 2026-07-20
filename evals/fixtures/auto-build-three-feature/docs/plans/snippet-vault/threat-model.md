# Threat Model — snippet-vault

A read-only re-projection of the plan's trust boundaries and data classes.

security_obligations:
  - feature: 01-create-snippet
    threat_ids: [TZ-001]
  - feature: 02-share-snippet
    threat_ids: [TZ-002]
  - feature: 03-export-snippets
    threat_ids: [TZ-003]

## Trust Boundaries

- **TB-1:** The in-process API surface (`snippets.py`). All input arrives as function
  arguments; there is no network boundary in this plan.
- **TB-2 (deferred):** Any share link introduced by `02-share-snippet` would create a
  new external read surface — who may follow a link is an unresolved product decision
  (see the feature file), so the boundary is a park, not a settled control.

## Threat Zones

| ID | Zone | Data class | Obligation |
|---|---|---|---|
| TZ-001 | Snippet creation (`01`) | user content (title, body) | Reject an empty or whitespace-only title before mutating the store. |
| TZ-002 | Share surface (`02`) | shared reference | Access control for a shared snippet is **undecided** — a blocking product call, parked for the owner. |
| TZ-003 | Export (`03`) | bulk user content | Export is read-only over the store; it must not mutate or leak fields the store does not hold. |
