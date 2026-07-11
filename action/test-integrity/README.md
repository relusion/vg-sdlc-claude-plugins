# test-integrity — the standalone genie-catcher as a composite GitHub Action

Runs one gate — [`test-guard.py`](../../plugins/core-engineering/skills/ce-implement/scripts/test-guard.py) —
against every pull request and fails the check when a test was **weakened**
between the base ref and HEAD. It catches, by name, the single best-documented
failure mode of a coding agent in a red→green loop:

> **an agent that makes tests pass by weakening tests.**

Told to make a failing test pass, an agent may edit the *test* to pass instead
of the *code* — deleting it, emptying it, ripping out an assertion, adding a
`skip`, or stubbing it trivially-true (`assert True`). A self-policing context
cannot be trusted to confess it, so this runs as an **external script over the
committed diff** — the same test-integrity gate the toolkit's `/ce-implement`
loop and merge bar enforce, unbundled for teams that want only the genie-catch.

Agent-agnostic, stdlib-only Python, offline, zero Claude Code installed: a PR
authored by any coding agent — or a human — gets the identical red/green
verdict.

## When to reach for this instead of the full merge bar

Pick `test-integrity` when you want the genie-catch **without** adopting specs,
plans, or a merge policy — one gate, one input, no `.github/merge-bar/`
scaffolding. If you also want spec-traceability and undeclared-dependency
gating as one machine verdict, adopt [`action/merge-bar`](../merge-bar/README.md)
instead (it runs this same test-guard as its test-integrity conjunct). This
action is the thin front door to the one control the field does not otherwise
ship.

## Adopt it — three workflow lines

Create `.github/workflows/test-integrity.yml` in your repo:

```yaml
name: test-integrity
on: pull_request
permissions:
  contents: read
jobs:
  test-integrity:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
        with: { fetch-depth: 0 } # the diff gate needs the base ref, not a shallow tip
      - uses: relusion/vg-sdlc-claude-plugins/action/test-integrity@<PIN-ME-40-HEX-COMMIT-SHA>
```

The three load-bearing lines are the two `uses:` lines plus `fetch-depth: 0`;
the rest is a standard workflow skeleton.

**Fill the pin before you run it.** Replace `<PIN-ME-40-HEX-COMMIT-SHA>` with
the **full 40-hex commit SHA** of a vg-sdlc-claude-plugins release commit you
have reviewed. When release notes publish a recommended pin, verify the
referenced commit and use that SHA. If you start from a tag, independently
verify the provenance or signature your policy requires, resolve it with
`git rev-parse '<tag>^{commit}'`, and pin the resulting commit. Do not assume
a tag is signed, and never put a tag or branch name in `uses:`: those refs are
movable, commit SHAs are not, and the action refuses a movable ref at run time.

> **Pin source:** the trust decision is the reviewed release commit. A tag may
> help discover or authenticate that commit, but the action consumes the
> immutable 40-hex SHA and works at any reviewed commit.

Then make the `test-integrity` status check **required** in branch protection,
**alongside your own build/test job** (see the scope statement below), and
protect `.github/**` with CODEOWNERS or a repository ruleset — on
`pull_request` your calling workflow file runs from the PR merge ref, so without
this a PR can rewrite the workflow that invokes the action.

## What it detects

Between the base ref and HEAD, over every file the test-file heuristic
recognizes:

| Code | Hard failure (exit 1) |
|---|---|
| **T1** | a test file present at base is gone or emptied of all tests |
| **T2** | net assertions removed — the count of `assert`/`expect`/`should`/… dropped |
| **T3** | a `skip`/`xfail` marker was **added**, or a trivially-true assertion (`assert True`, `expect(true).toBe(true)`) was **added** — a green that proves nothing |

Advisory (never changes the exit code): a bare test-count drop with no other
signal (a possible legitimate refactor), a `test-guard: allow <reason>`
downgrade, or "no test files changed" (pass `test-glob` if your repo names
tests unconventionally).

## What it proves / what it does NOT — integrity, never sufficiency

A green verdict proves test **integrity**: no test was deleted, emptied,
de-asserted, skipped, or stubbed trivially-true relative to the base. It is
explicitly **not** a proof of:

* **sufficiency** — a weak-but-unweakened suite passes; this gate never judges
  whether the tests are *good*, only whether they got *worse*.
* **function** — the action **never builds the project and never runs the test
  suite.** It is **not a replacement for running your tests.** Keep your own
  build/test job as a second required status check.

The heuristics are high-recall, low-precision, and language-naive — a hit is a
**material finding** for a human to adjudicate, not an automatic verdict. Out of
scope by construction (these are code-review territory): logical inversions
(`==` → `!=`), threshold loosening (`> 5` → `>= 5`), mock-strength erosion
(`assert_called_once` → `assert_called`), and a test sharing a blind spot with
its implementation.

## The exit / status contract

`test-guard.py`'s exit code drives both the step result and the `status` output:

| Exit | `status` | Meaning | Step |
|---|---|---|---|
| **0** | `pass` | no hard failure (advisory warnings may still print) | green |
| **1** | `fail` | at least one T1/T2/T3 hard failure | **red** — the check fails |
| **2** | `error` | inputs missing/unparseable, base ref unresolvable, or git unavailable | **red** — fall back to a manual test-integrity review |

## Inputs

| Input | Default | Notes |
|---|---|---|
| `base-ref` | `${{ github.base_ref }}` | resolved as `origin/<base-ref>`; set explicitly for non-`pull_request` events |
| `repo-path` | `${{ github.workspace }}` | repository under judgment; override when your checkout used `path:` (also how the self-test drives a fixture repo) |
| `test-glob` | `''` | optional single glob overriding the test-file heuristic; set it when a green run reports "no test files changed" because your repo names tests unconventionally |

## Outputs

| Output | Value |
|---|---|
| `status` | `pass` / `fail` / `error`, from the verdict JSON |
| `verdict-path` | absolute path of the `test-integrity-verdict.json` produced — upload it with `actions/upload-artifact` as evidence |

## Why one SHA pin is the whole verification story

A `uses:` pin fetches this **entire repository** at that immutable commit, so
the action and the `test-guard.py` it runs arrive **atomically under one SHA** —
there is nothing left to checksum. The action **references** the toolkit's
canonical `test-guard.py`; it is never a forked copy that could drift.

## The PR must not grade itself

* `--head` defaults to `HEAD` (committed state), so nothing untracked in the
  runner can leak into the diff the gate judges.
* the action ref is rejected at run time unless it is a full 40-hex commit SHA,
  so a movable tag/branch pin fails loudly instead of silently drifting.
* **NOT covered here:** the calling workflow file runs from the PR merge ref, so
  a PR can still edit the workflow that invokes this action. Protect `.github/**`
  with CODEOWNERS or a repository ruleset (required companion control — see
  [docs/TEAM-ROLLOUT.md](../../docs/TEAM-ROLLOUT.md) and
  [docs/ENTERPRISE-HARDENING.md](../../docs/ENTERPRISE-HARDENING.md)).

## Self-test

[`.github/workflows/action-selftest.yml`](../../.github/workflows/action-selftest.yml)
in this repository runs the action (as `uses: ./action/test-integrity`) against
a throwaway fixture repo on every PR in **both** verdict directions: an honest
change that strengthens a test comes back green, and a committed cheat that guts
the test comes back red and fails the step — so the action's plumbing is proven
continuously at every commit an adopter might pin.
