"""Baseline suite — green before any feature is built, so 01 builds clean.

Tests only the seeded scaffold (an empty store), so the pre-existing suite passes
from the first spawn. `01-create-snippet` extends this file test-first with its own
add-snippet cases.
"""

from snippets import Store, list_snippets


def test_new_store_is_empty():
    assert list_snippets(Store()) == []


def test_list_snippets_returns_a_copy():
    store = Store()
    view = list_snippets(store)
    view.append("mutated")
    assert list_snippets(store) == []
