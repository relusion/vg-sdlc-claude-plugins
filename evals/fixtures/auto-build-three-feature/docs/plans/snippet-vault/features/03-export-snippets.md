# 03-export-snippets — Export snippets to CSV

**Type:** user-facing · **Depends on:** 01-create-snippet (not 02) · **Engineered path:** retry-exhaustion → failed

This feature is engineered to exercise the **retry-exhaustion** path: its acceptance test
is seeded and **cannot be satisfied**, so implement retries until the run's
verification-retry cap and the feature ends `failed`. The failure reads as an
output-mismatch defect, not a spec contradiction, so a diagnose gate should classify it
`bug` and route it back to implement (consuming a retry) rather than parking it early.

## Scope

- Add `export_csv(store)` to `snippets.py`, returning a CSV string of every snippet in
  insertion order (`[CONTRACT: IC-002]`), read-only over the store (`[SECURITY: TZ-003]`).

## Acceptance Criteria (EARS)

- **AC-1:** When `export_csv(store)` is called, the system shall return a CSV string of
  all snippets in the store and shall equal the frozen golden asserted by
  `checks/export_check.py::test_export_csv_matches_golden`.

## Why this cannot pass (the engineered defect)

`checks/export_check.py` freezes a one-row golden (`GOLDEN_CSV`) while AC-1 requires
exporting **all** snippets, and the acceptance test builds a **three-snippet** store. No
correct implementation of `export_csv` can make a three-row export equal a one-row golden,
so `test_export_csv_matches_golden` always fails. `test-guard.py` blocks weakening or
deleting the assertion, so the only exit is:

1. implement `export_csv` → run the suite → `test_export_csv_matches_golden` fails,
2. (diagnose on) root-cause: `bug` (output does not match the golden) → re-implement,
3. repeat until the verification-retry cap is reached → the feature is marked `failed`
   and the run circuit-breaks on the retry cap.

The fixture's job is to **force the non-clean path deterministically**; WS3-T13's live run
records which terminal state and diagnosis class actually land, and freezes them as goldens.

## Test Guidance

Do **not** edit `checks/export_check.py`. Implement `export_csv` honestly; record the
unresolvable failure in `verification.md` / `diagnosis.md` rather than tampering with the
seeded test.

## Out of Scope

- Any store mutation during export.
- Alternative export formats (JSON, Markdown).
