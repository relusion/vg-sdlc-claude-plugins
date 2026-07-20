# Patch Artifact Reference

`/ce-patch` uses one transient input and one optional durable record. It never creates
a patch plan directory, eligibility lease, spec, task file, verification file,
`plans.json` entry, or patch metrics bundle.

## Transient `express.json`

After the scoped probe and before any code edit, write this object to a temporary
directory outside the repository:

```json
{
  "files": ["path/to/implementation", "path/to/test"],
  "desc": "one-line requested change"
}
```

Rules:

- `files` contains one or two unique, repository-relative paths.
- The array is the frozen Scope Lock and includes every code/test file the change may
  touch. Do not mutate it after admission.
- `desc` is the user's request, kept on one line so the safety screen can inspect it.
- Delete the temporary stub when the run accepts, discards, or routes to `/ce-plan`.

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
  "files": ["path/to/implementation", "path/to/test"],
  "base_ref": "<git commit captured before editing>",
  "tests": {
    "command": "<exact focused test command>",
    "red": true,
    "green": true
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

No line is written for a refused, inconclusive, revised-in-progress, discarded, or
routed change. The ledger records accepted usage; it is not proof of review quality,
compliance, deployment, or release readiness.
