## VC Policy

| Field | Value |
|---|---|
| Repository | git (initialize the copied fixture if no `.git` is present) |
| Branching model | isolated-branch |
| Branch pattern | `auto-build/<slug>/<date>` |
| Commit granularity | per-feature (Checkpoint Mode) |
| Push | never — the human owns what enters shared history |

Auto-build may make per-feature commits to an isolated `auto-build/snippet-vault/<date>`
branch as an audit/rollback trail. It must never commit to the human's branch, push, open
a PR, merge, or deploy. If the working copy is not a git repository, initialize one for the
isolated branch, or degrade Checkpoint Mode to `none` and record it as a degradation.
