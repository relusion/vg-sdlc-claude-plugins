# Patch Workflow — Stages

Run this file after reading `SKILL.md`. Load
`${CLAUDE_SKILL_DIR}/artifact-reference.md` before creating the transient
candidate stub or appending the accepted ledger line.

## Stage 0 — Probe and Admission

### 0.1 Establish a safe baseline

1. Confirm the target is a git worktree and record `git rev-parse HEAD` as
   `base_ref`.
2. Inspect `git status --short`. Preserve all pre-existing user changes. If a
   candidate file is already modified and patch ownership cannot be separated with
   confidence, stop and route to `/core-engineering:ce-plan`.
3. Read the requested file(s), their direct callers/consumers (one hop), and the
   relevant test/build configuration. Do not create a repository-wide profile.
4. Enumerate the complete candidate set. Behavior mode includes its focused
   test file; content mode may use an external check and one target file. The
   set must contain one or two repository-relative paths. If it is unknown,
   wider, or likely to grow, route to `/core-engineering:ce-plan`.
5. Check for product or architecture unknowns and runtime blast radius that path
   heuristics cannot see. Any uncertainty routes to `/core-engineering:ce-plan`.

No code or durable workflow artifact may be written during this probe.

### 0.2 Run the mechanical admission screen

Create a temporary directory outside the repository and write `express.json` using
the schema in `artifact-reference.md`. The stub is transient input, not a product
artifact. Run from the repository root:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/patch-lint.py" <tmp>/express.json
```

Disposition is fixed:

- **PASS (0):** freeze the stub's candidate paths and continue.
- **FAIL (1):** show the named E-check and route directly to `/core-engineering:ce-plan`.
- **ERROR (2):** admission is inconclusive; show the error and route directly to
  `/core-engineering:ce-plan`.

The first non-zero admission result is terminal. Do not try alternate candidate
stubs, continue into later stages, or add hypothetical blockers after the handoff
evidence is complete.

There is no manual fallback and no full patch lane. Delete the transient stub after
the run ends.

## Stage 1 — Select Mode and Capture Before

Choose exactly one mode:

- **Behavior/code:** run the narrowest automated test and capture the expected
  failing assertion/diagnostic. The failure must demonstrate the requested gap.
- **Prose/content/internal config:** run a deterministic read-only command that
  demonstrates the exact current defect, such as `rg -nF` for a typo, a parser
  query for the old value, or a focused lint diagnostic. Define the paired
  after condition before editing. Do not create a fake failing test.

Capture the exact command, expected before state, and output. A missing tool,
unrelated result, already-correct state, or required file outside the frozen set
makes the lane inconclusive; route before editing.

## Stage 2 — Implement and Reach Green

Make only the requested change within the frozen candidate set. Follow repository
conventions and keep unrelated user changes intact.

1. Make one bounded edit. In behavior mode, rerun the same test to green. In
   content mode, run the predefined after check and confirm the desired
   textual/parsed state. A wrong, unchanged, ambiguous, or could-not-run result
   routes directly to `/core-engineering:ce-plan`; do not start a repair loop.
2. Run each proportionate lint, type, build, or nearby regression check once. Any
   failure or could-not-run result routes directly to `/core-engineering:ce-plan`.
3. Inspect `git diff --name-only` before continuing. Needing or touching any file
   outside the frozen set is a Scope Lock breach; stop and route to `/core-engineering:ce-plan`.

Do not change the candidate stub to legitimize a wider diff.

## Stage 3 — External Diff Check

Run a new validator process over the actual working-tree diff:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/patch-lint.py" \
  <tmp>/express.json --post --base <base_ref>
```

The post-check re-runs admission, then checks:

- **H8:** no durable-state or schema write;
- **H9:** every changed file is in the frozen set;
- **H10:** no destructive/irreversible operation;
- **H11:** no new public API, route, CLI option, or other contract surface.

Only exit `0` proceeds. Exit `1` or `2` routes directly to `/core-engineering:ce-plan`. Show the exact
finding and leave any partial diff visible; do not auto-revert it, waive it, or add a
file to the candidate set after the fact.

## Stage 4 — Gate 1 of 1: Patch Acceptance

Print `Gate 1 of 1 — Patch acceptance` and render one compact evidence bundle:

- request and frozen files;
- evidence mode;
- actual diff;
- `Before command/result:` with the demonstrated defect;
- `After command/result:` with the demonstrated requested state;
- proportionate regression checks;
- E1–E5 and H8–H11 results;
- explicit no-sensitive-surface and no-open-unknown statements;
- known evidence limitations.

Ask the human to choose:

| Choice | Action |
|---|---|
| **Accept** | keep the diff; append one line to `docs/plans/express-log.jsonl` |
| **Revise** | stay inside the frozen set; repeat Stages 1–4 |
| **Discard** | confirm and remove only patch-owned changes; append nothing |
| **Route to `/core-engineering:ce-plan`** | keep the diff visible; append nothing; emit the handoff below |

Do not interpret silence or an unrelated reply as acceptance.

### Accept

Append exactly one JSON object using the schema in `artifact-reference.md`. Create
`docs/plans/` or the log only if needed. Do not write any other patch artifact. Report
the changed files and commands run, then leave the diff uncommitted.

### Revise

If the revision still fits the frozen request and paths, return to Stage 1 and
repeat the selected mode's before/after proof. Otherwise route to
`/core-engineering:ce-plan`.

### Discard

Show the exact patch-owned changes that will be removed and require the explicit
Discard choice. Restore only those edits. If a file contained pre-existing user work,
do not use a whole-file restore; stop and ask the human how to preserve it.

### Route to `/core-engineering:ce-plan`

Emit a text handoff with:

```text
Next: /core-engineering:ce-plan <original request>
Candidate files: <paths>
Reason: <failed or uncertain E/H check, scope breach, or open question>
Evidence: <repository reads and before/after commands/results>
Working tree: <no patch edit | partial diff remains in paths>
```

Stop after the handoff. Do not invoke the next skill automatically.

## Closing

```text
Patched: <short request> — <one or two candidate files>
Verified: <mode>: <before command> → <after command>; <other checks>
Record: docs/plans/express-log.jsonl (one accepted line)
Version control: not committed — reviewed diff left in the working tree
```

Pushing, pull requests, merging, releasing, and deployment remain human-owned.
