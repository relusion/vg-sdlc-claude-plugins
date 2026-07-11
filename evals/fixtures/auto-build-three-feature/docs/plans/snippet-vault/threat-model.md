# Threat Model — snippet-vault

A read-only re-projection of the plan's trust boundaries and data classes.

## Trust Boundaries

- **TB-1:** The in-process API surface (`snippets.py`). All input arrives as function
  arguments; there is no network boundary in this plan.
- **TB-2 (deferred):** Any share link introduced by `02-share-snippet` would create a
  new external read surface — who may follow a link is an unresolved product decision
  (see the feature file), so the boundary is a park, not a settled control.

## Threat Zones

| ID | Zone | Data class | Obligation |
|---|---|---|---|
| TZ-001 | Snippet creation (`01`) | user content (title, body) | Validate: non-empty title, `body` ≤ `MAX_BODY`, `language ∈ ALLOWED_LANGUAGES`. Never execute a snippet body. |
| TZ-002 | Share surface (`02`) | shared reference | Access control for a shared snippet is **undecided** — a blocking product call, parked for the owner. |
| TZ-003 | Export (`03`) | bulk user content | Export is read-only over the store; it must not mutate or leak fields the store does not hold. |
