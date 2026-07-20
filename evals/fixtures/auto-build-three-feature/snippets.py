"""In-memory snippet vault — the seed the snippet-vault plan builds on.

Seeded scaffold only: the Store container and a read helper.
`01-create-snippet` implements `add_snippet`; `03-export-snippets`
implements `export_csv`. Kept tiny and dependency-free so the plan's three
features are the only moving parts an auto-build run has to reason about.
"""

from __future__ import annotations

from dataclasses import dataclass, field

@dataclass
class Snippet:
    id: int
    title: str
    body: str
    language: str


@dataclass
class Store:
    snippets: list = field(default_factory=list)
    _next_id: int = 1


def list_snippets(store: Store) -> list:
    """Return the store's snippets in insertion order (a read-only view)."""
    return list(store.snippets)
