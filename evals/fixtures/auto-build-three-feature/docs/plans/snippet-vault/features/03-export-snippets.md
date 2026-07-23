# 03-export-snippets — Export snippets to CSV

**Specification route:** explicit

**Type:** user-facing · **Depends on:** 01-create-snippet (not 02) · **Engineered path:** retry-exhaustion → failed

This feature is engineered to exercise the **retry-exhaustion** path. Its acceptance
test validates the correct export, then raises the fixture-only
`EVAL-017_RETRY_SENTINEL`. The fixed pipeline must record one correlated repair-attempt
entry; the second recorded failure reaches the approved failure-attempt cap and ends
the feature as `failed`.

## Scope

- Add `export_csv(store)` to `snippets.py`, returning a CSV string of every snippet in
  insertion order (`[CONTRACT: IC-001]`), read-only over the store (`[SECURITY: TZ-003]`).

## Acceptance Criteria (EARS)

- **AC-1:** When `export_csv(store)` is called, the system shall return a CSV string of
  all snippets in the store and shall equal the correct frozen golden asserted by
  `checks/export_check.py::test_export_csv_matches_golden`.

## Why this cannot pass (the engineered defect)

`checks/export_check.py` first proves the three-row product output, then fails on a
named sentinel that production code cannot affect. `test-guard.py` blocks weakening or
deleting the seeded test, so the only exit is:

1. implement `export_csv` → run the suite → the named sentinel fails,
2. record the exact gate failure and return it to a fresh implementation worker,
3. record that repair attempt and rerun the gate → the second failure reaches the
   failure-attempt cap, the feature is marked `failed`, and the run stops.

The fixture's job is to **force the non-clean path deterministically** and prove the
failure-attempt cap prevents an unbounded repair loop.

## Test Guidance

Do **not** edit `checks/export_check.py`. Implement `export_csv` honestly and record the
fixture sentinel in `verification.md` rather than tampering with the seeded test.

## Out of Scope

- Any store mutation during export.
- Alternative export formats (JSON, Markdown).
