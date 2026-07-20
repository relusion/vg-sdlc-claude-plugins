---
name: ce-patch
description: |
  Make one low-risk change on a bounded, test-first lane that touches at most two candidate files and ends at one human acceptance gate. Any uncertain, sensitive, dependency, durable-state, schema, public-contract, destructive, colliding, or wider change routes to /core-engineering:ce-plan; this skill never commits, pushes, opens a PR, or merges.
  Triggers: a typo, localized bug fix, or small behavior change with a known test. Multi-file, contract, schema, dependency, security-sensitive, or exploratory work → /core-engineering:ce-plan.
argument-hint: "[change description] [--express]"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion
disable-model-invocation: true
---

# Patch

**Invocation input:** Change requested: $ARGUMENTS

Make one genuinely small change with a short, predictable workflow. `/core-engineering:ce-patch`
has one lane: a mechanical admission screen, a red-to-green edit within at most two
candidate files, an external diff check, and one human acceptance gate. `--express`
is accepted as a backward-compatible alias; it does not select different behavior.

This skill creates no plan, spec, task, eligibility, or verification bundle. Its only
durable workflow record is one append-only line written after the human accepts.

## Runtime Inputs

- **Change request (required):** the behavior or text to change.
- **Candidate files (discovered or supplied):** at most two repository-relative
  paths, including any test file the change needs.
- **Repository evidence (read-only):** the candidate files, their direct callers or
  consumers (one hop), relevant test/build commands, `git status`, and other plans'
  `tasks.json` ownership declarations under `docs/plans/`.
- **Diff base:** the current git commit captured before any patch-owned edit.

The repository must be a git worktree, the candidate set must be enumerable, and a
meaningful failing-then-passing check must fit inside the two-file boundary. If any of
those facts cannot be established, route to `/core-engineering:ce-plan` without editing code.

## Execution Contract

1. **Screen before writing.** Run `patch-lint.py` over a transient candidate stub.
   Exit `1` (policy refusal) or `2` (inconclusive/error) both route directly to
   `/core-engineering:ce-plan`. There is no manual bypass and no larger `/core-engineering:ce-patch` fallback.
2. **Freeze the Scope Lock.** The candidate set contains at most two files and
   includes tests. It may narrow, never widen. Needing another file stops the run and
   routes to `/core-engineering:ce-plan`.
3. **Keep admission conservative.** Reject cross-plan ownership collisions,
   dependency manifests, reviewer-trigger surfaces, public contracts, durable state,
   schemas, destructive operations, and any unresolved product or architecture
   question. Uncertainty is a refusal, not permission to infer.
4. **Prove red to green once.** Run the narrowest relevant test before implementation
   and capture the expected failure. Make one bounded implementation pass, rerun the
   same command once, then run each proportionate lint/build check once. A check that
   remains red, fails for another reason, or cannot run routes directly to `/core-engineering:ce-plan`;
   this lane has no automated repair loop.
5. **Check the actual diff externally.** A separate `patch-lint.py --post` process
   re-runs admission and verifies that the diff stays inside the frozen set and adds
   no durable-state, destructive, or public-contract surface. Any non-zero result
   routes to `/core-engineering:ce-plan`; do not talk a heuristic finding into a pass.
6. **Use exactly one human gate.** After the diff and evidence are ready, print
   `Gate 1 of 1 — Patch acceptance`. The human chooses Accept, Revise, Discard, or
   Route to `/core-engineering:ce-plan`. Silence is not approval.
7. **Write one record only after Accept.** Append one JSON object to
   `docs/plans/express-log.jsonl`. Do not create `eligibility.json`, `ce-spec.md`,
   `tasks.json`, `verification.md`, a patch plan directory, or a `plans.json` entry.
8. **Leave version control human-owned.** Never commit, push, open a pull request,
   merge, deploy, or alter shared history. Leave an accepted diff in the working tree.

## Admission Screen

`patch-lint.py` checks a transient JSON stub with the candidate paths and request:

| Check | Refusal condition |
|---|---|
| **E1 — bounded files** | zero files, duplicate/unsafe paths, or more than two candidate files |
| **E2 — ownership** | a candidate file is named by another plan's `tasks.json`, or ownership data cannot be read confidently |
| **E3 — reviewer trigger** | auth, secrets, payments, deletion, persistence, localization, accessibility, or similar sensitive surface |
| **E4 — dependency surface** | a dependency manifest or lock file is in scope |
| **E5 — contract/state safety** | request or paths indicate a public API/CLI/config contract, schema, durable state, migration, or destructive operation |

The screen is a conservative floor, not proof that a change is harmless. Before
running it, the orchestrator also reads the named files and one-hop consumers. If
that inspection leaves an open question or suggests a wider runtime blast radius,
route to `/core-engineering:ce-plan` even when the script would pass.

## Scope Lock

The stub's `files` array is frozen when admission passes:

- edits and tests stay within those paths;
- the append-only workflow log is the sole exempt bookkeeping file;
- an unexpected generated file, formatter change, or out-of-set edit is a breach;
- on breach, stop and preserve the current diff for the `/core-engineering:ce-plan` handoff. Never
  silently revert user work or shrink the requested behavior to fit.

## Human-in-the-Loop — minimal

There is one material gate, after implementation and the post-diff check. The gate
must show:

- the requested change and frozen candidate files;
- the actual diff;
- the red and green commands/results;
- admission and post-check results;
- explicit statements that no reviewer-trigger/public-contract/durable-state surface
  or open product/architecture question was found;
- any limitation in the evidence.

Then ask:

| Option | Result |
|---|---|
| **Accept** | keep the diff and append one accepted-change ledger line |
| **Revise** | revise within the same frozen set, then repeat red/green and post-check |
| **Discard** | after confirming the exact patch-owned changes, remove only those changes; write no ledger line |
| **Route to `/core-engineering:ce-plan`** | keep the diff visible, write no ledger line, and emit a bounded handoff |

The gate locator is literal: print `Gate N of M` as `Gate 1 of 1 — Patch acceptance`.
Discard is destructive to the patch-owned edit and therefore requires the explicit
Discard choice; it must never remove pre-existing user changes.

## How to Run This Workflow

This skill is staged. Resolve `${CLAUDE_SKILL_DIR}`, then load:

| File | Purpose |
|---|---|
| `${CLAUDE_SKILL_DIR}/stages.md` | admission, red/green implementation, diff check, gate, and handoff |
| `${CLAUDE_SKILL_DIR}/artifact-reference.md` | transient stub and accepted ledger schemas |

To begin, load `${CLAUDE_SKILL_DIR}/stages.md` and start at Stage 0. Treat
`--express` in `$ARGUMENTS` as a no-op alias and follow the same stages.

## Escalation

Every admission refusal, inconclusive validator result, missing red test,
implementation error, still-red intended check, regression/lint/build failure, scope
breach, sensitive or contract-bearing signal, post-check finding, and unresolved
question routes directly to `/core-engineering:ce-plan`. The handoff is response text, not a new patch
artifact: include the request, candidate paths, evidence gathered, exact failed check,
test state, and whether a partial diff exists. Stop; do not invoke `/core-engineering:ce-plan`
automatically and do not continue editing.

## Honest Limitations

- Path and diff patterns are high-recall heuristics. They can over-route safe changes
  and can miss an unfamiliar sensitive or persistence idiom. One-hop repository
  inspection and human acceptance remain required.
- A two-file cap is deliberately blunt. A production change plus a new test often
  consumes the entire allowance; generated snapshots or fixtures require `/core-engineering:ce-plan`.
- Red-to-green evidence proves only the exercised behavior. Shared mistakes in the
  test and implementation can still pass.
- `express-log.jsonl` is an activity record, not a specification, review approval,
  compliance attestation, or release record.
- Repeated tiny patches can still hide a larger change. Teams should review the log
  for clustered edits and route recurring work through `/core-engineering:ce-plan`.
