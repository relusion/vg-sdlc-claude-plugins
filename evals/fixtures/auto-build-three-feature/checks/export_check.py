"""Seeded acceptance test for 03-export-snippets — engineered to exhaust the retry cap.

Dormant until `export_csv` exists: features 01 and 02 never import it, so their
pipeline stays green and the seeded suite passes from the first spawn. Once
`03-export-snippets` implements `export_csv`, this test activates and asserts the
export equals ``GOLDEN_CSV`` — a one-row golden that a correct export of the seeded
three-snippet store can never match (wrong row count, wrong header). No implementation
can satisfy it, so /ce-implement retries until the run's verification-retry cap and the
feature ends ``failed``. It reads as an output-mismatch defect (not a spec contradiction),
which biases the diagnose gate toward a ``bug`` class and the retry path rather than an
early spec-gap park. ``test-guard.py`` blocks weakening or deleting the assertion, so the
only exit is retry-exhaustion — the behavior WS3-T13's live run records as a golden.
"""

import pytest

try:
    from snippets import export_csv  # noqa: F401

    _HAS_EXPORT = True
except Exception:  # noqa: BLE001 — absence is the dormant state, not an error
    _HAS_EXPORT = False

# Intentionally unsatisfiable — see the module docstring.
GOLDEN_CSV = "id,title\n1,Hello World\n"


@pytest.mark.skipif(not _HAS_EXPORT, reason="export_csv not implemented until 03-export-snippets")
def test_export_csv_matches_golden():
    from snippets import Store, add_snippet, export_csv

    store = Store()
    add_snippet(store, title="Hello World", body="print('hi')", language="python")
    add_snippet(store, title="Note", body="a note", language="text")
    add_snippet(store, title="Query", body="SELECT 1", language="sql")
    assert export_csv(store) == GOLDEN_CSV
