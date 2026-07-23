# Patch Artifact Reference

`/core-engineering:ce-patch` uses one transient input and one optional durable record. It never creates
a patch plan directory, eligibility lease, spec, task file, verification file,
`plans.json` entry, or patch metrics bundle.

## Transient `express.json`

After the scoped probe and before any code edit, write this object to a temporary
directory outside the repository:

```json
{
  "files": ["path/to/target", "path/to/test-if-behavior"],
  "desc": "one-line requested change"
}
```

Rules:

- `files` contains one or two unique, repository-relative paths.
- The array is the frozen Scope Lock and includes every edited file. Behavior
  mode includes its focused test; content mode may contain only the target when
  its deterministic check is external. Do not mutate it after admission.
- `desc` is the user's request, kept on one line so the safety screen can inspect it.
- Delete the temporary stub when the run accepts, discards, or routes to `/core-engineering:ce-plan`.

## Accepted-Change Ledger

The only durable workflow record is:

```text
docs/plans/express-log.jsonl
```

Append one JSON object only after `Gate 1 of 1 — Patch acceptance` receives an
explicit **Accept** choice:

```json
{
  "ts": "<ISO-8601 timestamp>",
  "desc": "<one-line requested change>",
  "files": ["path/to/target", "path/to/test-if-behavior"],
  "base_ref": "<git commit captured before editing>",
  "evidence": {
    "mode": "behavior | content",
    "before": {
      "command": "<exact read-only command>",
      "result": "<expected failure or demonstrated old state>"
    },
    "after": {
      "command": "<exact verification command>",
      "result": "<green result or demonstrated requested state>"
    }
  },
  "checks": {
    "admission": "pass",
    "post_diff": "pass"
  },
  "decision": "accept",
  "decided_by": "human"
}
```

The line must be valid single-line JSON. Preserve existing lines byte-for-byte and
append; never rewrite the ledger to format or sort it.

For behavior mode, `before` and `after` are the focused red/green test. For
content mode, they are the predefined deterministic state checks; do not add a
fictional test result.

No line is written for a refused, inconclusive, revised-in-progress, discarded, or
routed change. The ledger records accepted usage; it is not proof of review quality,
compliance, deployment, or release readiness.
