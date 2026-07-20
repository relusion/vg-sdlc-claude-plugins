## VC Policy

| Field | Value |
|---|---|
| Repository | The eval runner provides a copied working tree |
| Branching model | Human-owned; auto-build does not create or switch branches |
| Commit granularity | None during auto-build |
| Push | Never — the human owns what enters shared history |

Auto-build may edit only the copied fixture and its plan evidence. It must not
initialize version control, create branches or commits, push, open or merge a pull
request, or deploy. The Stage-3 report leaves the complete diff for human review.
