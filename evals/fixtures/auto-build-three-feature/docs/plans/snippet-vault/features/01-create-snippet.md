# 01-create-snippet — Create a snippet

**Type:** foundation · **Depends on:** none · **Engineered path:** clean build

Fully specified, no open questions. This is the clean-build feature: a spawned
spec + implement pass should carry it to `done` with every acceptance criterion met
and no park.

## Scope

- Add `add_snippet(store, title, body, language)` to `snippets.py`.
- Assign a monotonically increasing `id` (starting at 1, never reused) and append a
  `Snippet` record to the store.
- Return the created `Snippet`.

## Acceptance Criteria (EARS)

- **AC-1:** When `add_snippet` is called with a non-empty `title`, a `body` no longer
  than `MAX_BODY`, and a `language` in `ALLOWED_LANGUAGES`, the system shall append a
  `Snippet` with the next id and return it. `[CONTRACT: IC-001]`
- **AC-2:** When `title` is empty or whitespace-only, the system shall raise `ValueError`
  and add nothing. `[SECURITY: TZ-001]`
- **AC-3:** When `body` exceeds `MAX_BODY`, the system shall raise `ValueError` and add
  nothing. `[SECURITY: TZ-001]`
- **AC-4:** When `language` is not in `ALLOWED_LANGUAGES`, the system shall raise
  `ValueError` and add nothing.

## Test Guidance

Extend `checks/snippets_check.py` test-first with one case per AC. The seeded baseline
(`test_new_store_is_empty`) must keep passing.

## Out of Scope

- Sharing (02) and export (03).
- Editing or deleting snippets.
- Any persistence — the store is in memory (see `shared-context.md`).
