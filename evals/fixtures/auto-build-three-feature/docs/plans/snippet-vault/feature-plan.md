# Feature Plan: snippet-vault

A small in-memory snippet vault. Three features, engineered to exercise the three
terminal paths of a `/core-engineering:ce-auto-build` run — one clean, one park, one retry-exhaustion.

## Journey Map / Consumability Trace

A developer creates a snippet (title, body, language), optionally shares it by link,
and can export the whole vault to CSV. Everything is in memory; there is no database.

## Features

| # | ID | Title | Depends on | Engineered path |
|---|---|---|---|---|
| 1 | 01-create-snippet | Create a snippet | — | clean build |
| 2 | 02-share-snippet | Share a snippet by link | 01-create-snippet | PARK (blocking product decision) |
| 3 | 03-export-snippets | Export snippets to CSV | 01-create-snippet | retry-exhaustion → failed |

`03-export-snippets` depends only on `01-create-snippet`, **not** on `02-share-snippet`,
so a parked 02 never blocks 03 — the run reaches all three terminal states.

## Build Checklist

- [ ] 01-create-snippet
- [ ] 02-share-snippet
- [ ] 03-export-snippets

## Durable-State Closure

No durable state: the `Store` lives in memory for the process lifetime. Persistence is
explicitly out of scope for this plan (a persistence decision would itself be a park).
