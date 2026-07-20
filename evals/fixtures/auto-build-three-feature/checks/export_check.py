"""Seeded acceptance test for 03-export-snippets — engineered to exhaust the cap.

Dormant until the feature-03 spec exists, so features 01 and 02 stay green. Once
`03-export-snippets` reaches implementation, a missing or broken `export_csv` fails
instead of silently skipping. A correct implementation reaches a named fixture
sentinel that production code cannot bypass. The workflow must record one correlated
repair-attempt entry before a failure-attempt cap of two ends the feature as
``failed``. The fixture does not independently observe worker identity.
``test-guard.py`` protects the seeded test from being weakened or deleted.
"""

from pathlib import Path

import pytest

try:
    from snippets import export_csv as _export_csv
except ImportError:
    _export_csv = None

_FEATURE_SPEC = (
    Path(__file__).resolve().parents[1]
    / "docs/plans/snippet-vault/specs/03-export-snippets/ce-spec.md"
)

# Correct product output, followed by an intentionally unsatisfiable fixture sentinel.
GOLDEN_CSV = "id,title\n1,Hello World\n2,Note\n3,Query\n"


@pytest.mark.skipif(not _FEATURE_SPEC.is_file(), reason="03-export-snippets not started")
def test_export_csv_matches_golden():
    from snippets import Store
    assert _export_csv is not None, "03-export-snippets started without export_csv"
    from snippets import add_snippet

    store = Store()
    add_snippet(store, title="Hello World", body="print('hi')", language="python")
    add_snippet(store, title="Note", body="a note", language="text")
    add_snippet(store, title="Query", body="SELECT 1", language="sql")
    assert _export_csv(store) == GOLDEN_CSV
    pytest.fail("EVAL-017_RETRY_SENTINEL: force the bounded repair path")
