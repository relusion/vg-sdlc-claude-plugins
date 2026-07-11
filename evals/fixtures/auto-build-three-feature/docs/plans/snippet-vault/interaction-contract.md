# Interaction Contract — snippet-vault

Cross-feature protocol invariants. A read-only re-projection of the plan.

| ID | Invariant | Owner | Consumers |
|---|---|---|---|
| IC-001 | The `Store` holds `Snippet` records with fields `{id, title, body, language}`; ids are assigned monotonically and never reused. | 01-create-snippet | 02-share-snippet, 03-export-snippets |
| IC-002 | `list_snippets(store)` returns snippets in insertion order and never a live reference to the store's internal list. | 01-create-snippet | 03-export-snippets |
| IC-003 | Adding a share must not change the `Snippet` shape IC-001 defines (a share is a separate reference, not a new persisted field) — a persisted-field change would be a breaking SHARED-shape reconciliation and a park. | 02-share-snippet | 03-export-snippets |
