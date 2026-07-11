#!/usr/bin/env python3
"""test-guard.py — the on-disk gate that keeps the TDD loop honest.

The single best-documented failure mode of a coding agent in a red→green loop is the
"genie": told to make a failing test pass, it edits the *test* to pass instead of the
*code* — deleting it, ripping out an assertion, skipping it, or stubbing it to assert
nothing. (Anthropic's own Claude Code best-practices flow — write failing tests, commit
them, then implement *without modifying the tests* — and Kent Beck's "genie" warning both
name exactly this.) A self-policing context cannot be trusted to confess it; so, like
spec-lint.py and patch-lint.py, this is an **external script run by a process that did
not write the code**, comparing the test files against ground truth on disk.

It compares the test files at TWO points and FAILS if they got weaker between them.
There are two ways to obtain the earlier ("strong") version, because they catch
different things — one script, two modes, mutually exclusive:

  --snapshot <dir>   The PRIMARY genie catcher, used per-task by /ce-implement. <dir> is a
                     copy of the touched test files taken the moment they were confirmed
                     RED (failing), mirroring repo-relative paths. test-guard diffs that
                     snapshot against the current (green) working tree. This is the ONLY
                     mechanism that catches the *within-task* genie — a test authored
                     strong at red and weakened to pass at green — because the red form
                     is never committed anywhere. Works under any VC policy, incl. `none`.
                     On PASS (with --task) it appends a
                     `{task_id, verdict, ts, snapshot_sha256}` entry to the feature-level
                     `.test-guard/<feature-id>/passes.json` ledger that --verify-passes
                     later audits — the marker that survives this dir's own deletion.

  --base <ref>       The cross-task NET, used at auto-build's orchestrator gate. Diffs the
    [--head <ref>]   test files between a committed baseline (e.g. the parent of a
                     feature's checkpoint commit) and HEAD / the working tree. Catches a
                     LATER task deleting or gutting an EARLIER task's already-committed
                     test. It CANNOT catch the within-task genie (the strong red test was
                     never committed, so there is nothing to compare a weakened new test
                     against) — that is what --snapshot is for. Needs a committed base;
                     no base → exit 2.

A THIRD mode audits the PASS-marker ledger those --snapshot runs leave behind — it
neither diffs tests nor detects weakening, it closes the HONOR gap:

  --verify-passes    Run at feature verification (/ce-implement Stage 2 and auto-build
    --spec-dir DIR   step 5a, before `.test-guard/<id>/` is deleted). Every `done` task in
                     DIR/tasks.json whose `verifies` includes an `auto` test case MUST
                     have left a PASS marker in `.test-guard/<feature-id>/passes.json`
                     (written by that task's --snapshot PASS). A done+auto task with NO
                     marker reached done without ever proving its tests — the honor gap
                     the --snapshot gate alone cannot see (a task that skipped the
                     snapshot is simply never checked). It is reported as a hard failure
                     (exit 1) naming the task, so it becomes a loud degradation line in
                     verification.md rather than a silently unguarded task. The ledger is
                     the SOURCE OF TRUTH for "did this task prove its tests"; tasks.json's
                     `test_run_digest` is derived from each entry's `snapshot_sha256`.
                     Reuses spec-lint's tag parser to find the `auto` TCs; reads only
                     gitignored `.test-guard/` state, so it is in-loop, never a merge gate.

WHAT IT DETECTS (high-recall, low-precision, language-naive heuristics — a hit is a
MATERIAL FINDING the human / diagnose-gate adjudicates, never an automatic verdict):

  HARD (a hit -> exit 1):
    T1  a test file present in the earlier version is gone / emptied of all tests.
    T2  net assertions removed — the count of assert/expect/should/… calls dropped.
    T3  a skip/xfail marker was ADDED, or a trivially-true assertion was ADDED
        (assert True, expect(true).toBe(true), …) — a green that proves nothing.

  ADVISORY (warnings only; never change the exit code):
    A0  (git mode) no test files changed between base and head by the test-file
        heuristic — nothing to guard; surfaced so a task that wrote no tests is
        never a silent pass (pass --test-glob if the repo names tests unusually).
    A1  the test-declaration count dropped with NO T1/T2/T3 signal — possibly a
        legitimate refactor (merging/parametrizing), possibly erosion; surfaced, not
        gated (the balanced false-positive policy: a bare count drop alone is advisory).
    A2  a finding was DOWNGRADED to advisory by a `test-guard: allow <reason>` marker
        in the new file (the reason is recorded — an intentional, justified no-op).
    A3  an `allow` marker with NO reason was found and therefore IGNORED (a bare marker
        must not silently disable the gate — its findings stay HARD).

WHAT IT DOES NOT DETECT (out of scope — these are review territory; stated so the
gate is never mistaken for a proof): logical inversions (assert x == y -> assert x != y),
threshold loosening (x > 5 -> x >= 5), mock-strength erosion (assert_called_once ->
assert_called), or a test and its implementation sharing the same blind spot.

Exit codes (identical contract to spec-lint / patch-lint, so callers gate the same way):
    0  PASS  — no hard failures (advisory warnings may still print)
    1  FAIL  — at least one hard failure; the caller disposes per the skill's gate prose
    2  ERROR — inputs missing / unparseable, snapshot dir absent, git unavailable for
               --base, or (--verify-passes) spec-lint unloadable / passes.json unreadable;
               the caller falls back to the manual test-integrity check (loudly)
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


class TestGuardError(Exception):
    """Inputs cannot be loaded / a dependency is missing -> exit 2, caller falls back."""


# The PASS-marker ledger the honor gate reads. Version the schema so WS3-T3's
# tasks.json `test_run_digest` derivation (which reads `snapshot_sha256` out of
# each entry) can key off a stable shape. `.test-guard/<feature-id>/passes.json`
# is the SOURCE OF TRUTH for "did this task prove its tests"; it survives the
# per-task snapshot-dir deletion because it is a sibling of the task dirs.
PASSES_SCHEMA = "test-guard/passes@1"

# spec-lint is the single source for the spec/tasks loader + the modality/
# verification tag parser (--verify-passes needs to know which TCs are `auto`).
# Imported by path, exactly as patch-lint imports it: from the ce-implement
# canonical AND the ce-auto-build fork, parents[2] is `skills/`, so the hop
# resolves identically to skills/ce-spec/scripts/spec-lint.py either way.
SPEC_LINT_PATH = (
    Path(__file__).resolve().parents[2] / "ce-spec" / "scripts" / "spec-lint.py"
)


# --- test-file identification (git mode only; --snapshot trusts the curated dir) ----
# High-recall, low-precision, language-naive — ACKNOWLEDGED, like patch-lint's H8 block.
# Override with one or more --test-glob if a repo names tests unconventionally.
#
# A test is ALWAYS executable source. These extensions never hold one — but a
# spec-driven repo keeps prose specs under docs/plans/*/specs/ and data fixtures
# as .json/.yaml, and the directory branch below (…|(tests?|__tests__|spec|specs)/)
# would otherwise read `docs/plans/<f>/specs/ce-spec.md` or `api/specs/openapi.yaml`
# as a test file. Editing such a file (whose prose carries words like "require"
# and "verify") would then look like removed assertions and fail the merge bar on
# an ordinary doc edit — the bar crying wolf on the framework's own layout. Gate
# the whole heuristic on the file NOT being one of these non-code extensions.
# Trade-off: a repo whose TESTS are data files (a Tavern .yaml suite, a JSON
# test-case corpus) must name them with --test-glob to bring them back under the
# genie catcher — the exemption favors never false-redding a spec-driven repo's
# own tasks.json / openapi.yaml over auto-detecting the rare data-native test.
NON_CODE_EXT = frozenset({
    ".md", ".markdown", ".rst", ".txt", ".adoc",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".csv", ".tsv", ".lock", ".xml", ".html", ".htm", ".svg",
})
TEST_FILE = re.compile(
    r"(^|/)(test_[^/]*\.py|[^/]*_test\.py"
    r"|[^/]*\.(test|spec)\.[jt]sx?|[^/]*\.(test|spec)\.[jt]s"
    r"|[^/]*_test\.go|[^/]*_spec\.rb|test_[^/]*\.rb"
    r"|[^/]*Tests?\.(java|cs|kt|swift|scala))$"
    r"|(^|/)(tests?|__tests__|spec|specs)/",
    re.I,
)

# --- the weakening signals (counted on each version; deltas drive the verdict) ------

ASSERTION = re.compile(
    r"\b(assert|assert_\w+|assertEquals?|assertTrue|assertFalse|assertThat|assertNull"
    r"|assertNotNull|assertRaises|assertEqual|assertIn|assertIs|should\w*|verify"
    r"|EXPECT_\w+|ASSERT_\w+|XCTAssert\w*|require)\b"
    r"|\bexpect\s*\(",
    re.I,
)
TEST_DECL = re.compile(
    r"\bdef\s+test\w*\s*\("              # python
    r"|\bfunc\s+Test\w+\s*\("           # go
    r"|^\s*(it|test|describe|context)\s*\("  # js/ts/rspec/jest
    r"|@Test\b|@ParameterizedTest\b|\[Test\]|\[Fact\]|\[Theory\]"  # junit / xunit / nunit
    r"|@pytest\.mark\.parametrize"
    r"|\bt\.Run\s*\(",                  # go subtests
    re.M | re.I,
)
SKIP_MARKER = re.compile(
    r"@pytest\.mark\.skip\b|@pytest\.mark\.xfail\b|@unittest\.skip\w*|@skip\b"
    r"|\bpytest\.skip\s*\(|\bself\.skipTest\s*\("
    r"|\b(it|test|describe|context)\.(skip|todo)\b|\bxit\s*\(|\bxdescribe\s*\("
    r"|\.skip\s*\(|\bt\.Skip\s*\(|\bt\.Skipf\s*\("
    r"|@Ignore\b|\[Ignore\]|@Disabled\b|\[Skip\b",
    re.I,
)
TRIVIAL_ASSERT = re.compile(
    r"\bassert\s+(True|true|1)\s*(#|$|\))"
    r"|\bassert\s+1\s*==\s*1\b|\bassert\s+True\s*==\s*True\b"
    r"|\bexpect\s*\(\s*(true|1)\s*\)\s*\.toBe(Truthy)?\s*\(\s*(true|1)?\s*\)"
    r"|\bassertTrue\s*\(\s*true\s*\)|\bXCTAssertTrue\s*\(\s*true\s*\)"
    r"|\bassert\.(IsTrue|True)\s*\(\s*true\s*\)|\bAssert\.True\s*\(\s*true\s*\)",
    re.I,
)
# `test-guard: allow <reason>` in any common comment idiom; reason = trailing text.
ALLOW_MARKER = re.compile(
    r"(?:#|//|/\*|--|;)\s*test-guard:\s*allow\b[ \t]*(?P<reason>.*)",
    re.I,
)


def count(pat: re.Pattern, text: str) -> int:
    """Number of lines that contain >= 1 match (line-granular keeps the heuristic stable
    under reformatting and avoids double-counting multiple hits on one line)."""
    return sum(1 for ln in text.splitlines() if pat.search(ln))


def allow_reason(text: str) -> str | None:
    """Return the allow-marker's reason: a non-empty string if justified, '' if the
    marker is present but bare (-> ignored, A3), or None if no marker at all."""
    m = ALLOW_MARKER.search(text)
    if not m:
        return None
    return (m.group("reason") or "").strip()


# --- the detection over an (old, new) pair ------------------------------------------

def detect(path: str, old: str | None, new: str | None) -> tuple[list, list]:
    """Compare one test file's earlier (`old`) and current (`new`) content.
    `new is None` => the file is gone now. Returns (hard, advisory)."""
    hard: list[str] = []
    advisory: list[str] = []

    old_tests = count(TEST_DECL, old or "")

    # T1 — the file (or all its tests) vanished.
    if new is None:
        if old_tests > 0 or count(ASSERTION, old or "") > 0:
            hard.append(f"T1 {path}: test file deleted — it held {old_tests} test(s) earlier (genie: delete-the-test).")
        return hard, advisory
    if old_tests > 0 and count(TEST_DECL, new) == 0 and count(ASSERTION, new) == 0:
        hard.append(f"T1 {path}: all {old_tests} test(s) removed from the file — emptied of tests.")
        return hard, advisory

    # Signal deltas (new minus old): negative asserts = removed; positive skip/trivial = added.
    assert_delta = count(ASSERTION, new) - count(ASSERTION, old or "")
    skip_delta = count(SKIP_MARKER, new) - count(SKIP_MARKER, old or "")
    trivial_delta = count(TRIVIAL_ASSERT, new) - count(TRIVIAL_ASSERT, old or "")
    test_delta = count(TEST_DECL, new) - old_tests

    file_hard: list[str] = []
    if assert_delta < 0:
        file_hard.append(f"T2 {path}: {-assert_delta} assertion(s) removed (the test now checks less).")
    if skip_delta > 0:
        file_hard.append(f"T3 {path}: {skip_delta} skip/xfail marker(s) added (the test no longer runs).")
    if trivial_delta > 0:
        file_hard.append(f"T3 {path}: {trivial_delta} trivially-true assertion(s) added (a green that proves nothing).")

    # The balanced false-positive policy: a bare test-count drop with no other signal is
    # ADVISORY (legitimate refactors merge/parametrize tests); paired with a hard signal
    # it is context for that finding, not a separate gate.
    if test_delta < 0 and not file_hard:
        advisory.append(f"A1 {path}: {-test_delta} fewer test declaration(s) and no other weakening signal — confirm it is a refactor, not erosion.")

    # The escape hatch: a justified `test-guard: allow <reason>` downgrades THIS file's
    # hard findings to advisory (intentional, recorded). A bare marker is ignored (A3) so
    # it cannot silently neuter the gate.
    reason = allow_reason(new)
    if file_hard and reason:
        for f in file_hard:
            advisory.append(f"A2 {f}  [downgraded by allow-marker: {reason}]")
    elif file_hard and reason == "":
        hard.extend(file_hard)
        advisory.append(f"A3 {path}: a `test-guard: allow` marker with no reason was found and IGNORED — give a reason or the findings stand.")
    else:
        hard.extend(file_hard)

    return hard, advisory


# --- git plumbing (subprocess only, mirroring patch-lint) ---------------------------

def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if out.returncode != 0:
        raise TestGuardError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout


def _git_toplevel(start: Path) -> Path | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True,
        )
        if out.returncode == 0:
            return Path(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _show(repo: Path, ref: str, path: str) -> str | None:
    """Content of `path` at `ref`, or None if it did not exist there."""
    out = subprocess.run(
        ["git", "-C", str(repo), "show", f"{ref}:{path}"],
        capture_output=True, text=True,
    )
    return out.stdout if out.returncode == 0 else None


def _read(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return None


def is_test_file(path: str, globs: list[str]) -> bool:
    if globs:
        from fnmatch import fnmatch
        return any(fnmatch(path, g) or fnmatch(Path(path).name, g) for g in globs)
    # A prose/data file under a specs/ or tests/ directory is never a test — skip
    # it so the directory heuristic cannot false-red an ordinary doc edit. An
    # explicit --test-glob still wins above (an adopter who really tests via a
    # non-code extension can say so).
    if Path(path).suffix.lower() in NON_CODE_EXT:
        return False
    return bool(TEST_FILE.search(path))


# --- the two modes ------------------------------------------------------------------

def run_snapshot(snapshot_dir: Path, repo: Path) -> tuple[list, list]:
    """Compare every file under the red snapshot to its current working-tree counterpart.
    The snapshot dir mirrors repo-relative paths and is CURATED by the skill (only the
    task's touched test files), so we compare every file in it regardless of name."""
    if not snapshot_dir.is_dir():
        raise TestGuardError(f"snapshot dir not found: {snapshot_dir}")
    files = [p for p in snapshot_dir.rglob("*") if p.is_file()]
    if not files:
        raise TestGuardError(
            f"snapshot dir {snapshot_dir} is empty — no red baseline was captured; "
            f"fall back to the manual test-integrity check."
        )
    hard: list[str] = []
    advisory: list[str] = []
    for snap in sorted(files):
        rel = snap.relative_to(snapshot_dir).as_posix()
        old = _read(snap)
        cur = repo / rel
        new = _read(cur) if cur.is_file() else None
        h, a = detect(rel, old, new)
        hard += h
        advisory += a
    return hard, advisory


def _sha256_of_snapshot(snapshot_dir: Path) -> str:
    """A deterministic `sha256:<hex>` fingerprint of the red snapshot's file SET —
    each file's repo-relative path plus its raw bytes, ordered by path. This is what
    the PASS marker records as `snapshot_sha256`, and WS3-T3 projects verbatim into
    tasks.json's `test_run_digest`: two runs over the identical red baseline produce
    the same digest, and any change to the guarded test set changes it."""
    h = hashlib.sha256()
    files = sorted(
        (p for p in snapshot_dir.rglob("*") if p.is_file()),
        key=lambda p: p.relative_to(snapshot_dir).as_posix(),
    )
    for p in files:
        h.update(p.relative_to(snapshot_dir).as_posix().encode("utf-8"))
        h.update(b"\0")
        try:
            h.update(p.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
        h.update(b"\0")
    return f"sha256:{h.hexdigest()}"


def write_pass_marker(feature_dir: Path, feature_id: str, task_id: str, digest: str) -> Path | None:
    """Append one PASS entry to `<feature_dir>/passes.json` (append-only ledger, atomic
    tmp+rename). Called on a --snapshot PASS with a --task id. This ledger is the
    SOURCE OF TRUTH the --verify-passes honor gate audits and WS3-T3 derives
    `test_run_digest` from, and it SURVIVES the per-task snapshot-dir deletion because
    it sits one level up, beside the task dirs.

    Best-effort: any IO/parse failure warns LOUDLY to stderr and returns None — it
    NEVER changes the gate's exit code (the gate's verdict is test-integrity, not
    bookkeeping). A task whose marker failed to write simply resurfaces later as a
    --verify-passes gap, never a silent pass."""
    passes_path = feature_dir / "passes.json"
    entry = {
        "task_id": task_id,
        "verdict": "pass",
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "snapshot_sha256": digest,
    }
    try:
        feature_dir.mkdir(parents=True, exist_ok=True)
        ledger = {"schema": PASSES_SCHEMA, "feature_id": feature_id, "passes": []}
        if passes_path.is_file():
            try:
                existing = json.loads(passes_path.read_text(encoding="utf-8"))
                if isinstance(existing, dict) and isinstance(existing.get("passes"), list):
                    ledger = existing
                    ledger.setdefault("schema", PASSES_SCHEMA)
                    ledger.setdefault("feature_id", feature_id)
            except (OSError, json.JSONDecodeError) as e:
                print(
                    f"test-guard [snapshot]: WARNING — passes.json at {passes_path} is "
                    f"unreadable ({e}); rebuilding the ledger. Prior markers for OTHER "
                    f"tasks may be lost — they will resurface as --verify-passes gaps, "
                    f"never a silent pass.",
                    file=sys.stderr,
                )
        ledger["passes"].append(entry)
        tmp = passes_path.with_name(passes_path.name + ".tmp")
        tmp.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
        tmp.replace(passes_path)
        return passes_path
    except OSError as e:
        print(
            f"test-guard [snapshot]: WARNING — could not write the PASS marker to "
            f"{passes_path} ({e}); the test-integrity verdict is unaffected, but this "
            f"task will resurface as a --verify-passes gap.",
            file=sys.stderr,
        )
        return None


def run_git(repo: Path, base: str, head: str | None, globs: list[str]) -> tuple[list, list]:
    """Diff test files between a committed `base` and `head` (default: working tree)."""
    try:
        _git(repo, "rev-parse", "--verify", "--quiet", base + "^{commit}")
    except TestGuardError:
        raise TestGuardError(
            f"base ref `{base}` does not resolve — it may have been squashed/rebased; "
            f"re-derive it from disk, or fall back to the manual check."
        )
    diff_args = ["diff", "--name-status", base] + ([head] if head else [])
    hard: list[str] = []
    advisory: list[str] = []
    saw_test = False
    for line in _git(repo, *diff_args).splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status, path = parts[0], parts[-1]
        if not is_test_file(path, globs):
            continue
        saw_test = True
        old = _show(repo, base, path)
        if status.startswith("D"):           # deleted in head
            new = None
        elif head:
            new = _show(repo, head, path)
        else:
            cur = repo / path
            new = _read(cur) if cur.is_file() else None
        h, a = detect(path, old, new)
        hard += h
        advisory += a
    if not saw_test:
        advisory.append(
            "A0: no test files changed between base and head (by the test-file heuristic) "
            "— nothing to guard. If the repo names tests unconventionally, pass --test-glob."
        )
    return hard, advisory


# --- the honor gate: audit the PASS-marker ledger -----------------------------------

def load_spec_lint():
    """Import the canonical spec-lint by path — the single source for the spec/tasks
    loader (incl. the legacy spec.md fallback) and the modality/verification tag
    parser. Mirrors patch-lint's `load_spec_lint`: an import failure is a fallback
    condition (exit 2 → the caller reviews the ledger by hand), never a hard FAIL."""
    if not SPEC_LINT_PATH.is_file():
        raise TestGuardError(
            f"spec-lint.py not found at {SPEC_LINT_PATH} — cannot derive which `done` "
            f"tasks carry `auto` test cases; fall back to a manual read of tasks.json."
        )
    try:
        spec = importlib.util.spec_from_file_location("spec_lint_for_test_guard", SPEC_LINT_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001 — any import failure is a fallback condition
        raise TestGuardError(f"could not import spec-lint.py: {e}") from e
    return mod


def run_verify_passes(spec_dir: Path, repo: Path, feature_override: str | None) -> tuple[list, list, str]:
    """The honor gate. Every `done` task in `spec_dir/tasks.json` whose `verifies`
    includes an `auto` test case MUST have left a PASS marker in
    `.test-guard/<feature-id>/passes.json` (written by that task's --snapshot PASS).
    A done+auto task with no marker reached done without test-integrity evidence — a
    hard failure, never a silent unguarded pass. Returns (hard, advisory, feature_id)."""
    sl = load_spec_lint()
    ns = argparse.Namespace(spec_dir=str(spec_dir), spec=None, tasks=None)
    try:
        spec_path, tasks_path = sl.resolve_inputs(ns)
        spec_text, tasks = sl.load(spec_path, tasks_path)
        parsed = sl.parse_spec(spec_text)
    except Exception as e:  # noqa: BLE001 — spec-lint raises SpecLintError; honor exit-2
        raise TestGuardError(f"could not load spec/tasks from {spec_dir}: {e}") from e

    auto_tcs = {tc_id for tc_id, tc in parsed["test_cases"].items()
                if tc.get("verification") == "auto"}
    feature_id = feature_override or tasks.get("feature_id") or spec_path.resolve().parent.name

    passes_path = repo / ".test-guard" / feature_id / "passes.json"
    recorded: set = set()
    if passes_path.is_file():
        try:
            ledger = json.loads(passes_path.read_text(encoding="utf-8"))
            entries = (ledger.get("passes") if isinstance(ledger, dict) else []) or []
            for e in entries:
                if isinstance(e, dict) and e.get("task_id"):
                    recorded.add(e["task_id"])
        except (OSError, json.JSONDecodeError) as e:
            raise TestGuardError(
                f"passes.json at {passes_path} is unreadable ({e}) — cannot verify the "
                f"test-integrity ledger; fall back to a manual snapshot review."
            ) from e

    hard: list[str] = []
    advisory: list[str] = []
    checked = 0
    for t in tasks.get("tasks", []):
        if not isinstance(t, dict) or t.get("status") != "done":
            continue
        verifies = t.get("verifies") or []
        if not isinstance(verifies, list) or not any(v in auto_tcs for v in verifies):
            continue  # manual-only (or no-auto) done task — nothing to prove, skip
        checked += 1
        tid = t.get("id") or "<unnamed task>"
        if tid not in recorded:
            hard.append(
                f"PG1 {tid}: reached done without test-integrity evidence — no PASS marker "
                f"in {passes_path} for a task carrying auto test case(s). The red snapshot "
                f"was never captured (the honor gap) or the marker was lost; re-run "
                f"test-guard --snapshot for the task, or treat it as unguarded (loud)."
            )
    if checked == 0:
        advisory.append(
            "A4 verify-passes: no `done` task carries an `auto` test case — nothing for "
            "the PASS-marker ledger to guard (manual-only, or no completed auto task yet)."
        )
    return hard, advisory, feature_id


# --- reporting (mirrors patch-lint's emit) ------------------------------------------

def emit(scope: str, label: str, hard: list, advisory: list, as_json: bool,
         marker: str | None = None) -> int:
    status = "fail" if hard else "pass"
    if as_json:
        payload = {
            "status": status,
            "mode": scope,
            "label": label,
            "hard_failures": hard,
            "advisory": advisory,
        }
        if marker:
            payload["pass_marker"] = marker
        print(json.dumps(payload, indent=2))
        return 1 if hard else 0
    print(f"test-guard [{scope}]: {label}")
    if hard:
        print(f"\n  FAIL — {len(hard)} test-integrity failure(s):")
        for f in hard:
            print(f"    x {f}")
    else:
        print(f"\n  PASS — no test weakening detected for [{scope}].")
    if marker:
        print(f"  PASS marker recorded: {marker}")
    if advisory:
        print(f"\n  advisory ({len(advisory)} — review, non-blocking):")
        for a in advisory:
            print(f"    ! {a}")
    print()
    return 1 if hard else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="On-disk gate against agent-weakened tests in the TDD loop.")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--snapshot", metavar="DIR",
                      help="red-snapshot mode: dir of test files captured at red (mirrors repo-relative paths)")
    mode.add_argument("--base", metavar="REF",
                      help="git mode: committed baseline ref to diff test files against")
    mode.add_argument("--verify-passes", action="store_true",
                      help="honor-gate mode: verify every done task with an auto test case left a PASS marker (needs --spec-dir)")
    p.add_argument("--head", metavar="REF",
                   help="git mode: head ref (default: the working tree)")
    p.add_argument("--repo", metavar="PATH", help="repo root (default: git toplevel of cwd)")
    p.add_argument("--task", help="task id — report label AND the PASS-marker key (snapshot mode)")
    p.add_argument("--feature", help="feature id — report label (git mode) / marker feature-id override")
    p.add_argument("--spec-dir", metavar="DIR",
                   help="verify-passes mode: the feature's spec directory (specs/<id>)")
    p.add_argument("--test-glob", action="append", default=[], metavar="PAT",
                   help="override the test-file heuristic (repeatable; git mode)")
    p.add_argument("--json", action="store_true", help="machine-readable result")
    args = p.parse_args(argv)

    if args.head and not args.base:
        p.error("--head is only valid with --base (git mode)")
    if args.verify_passes and not args.spec_dir:
        p.error("--verify-passes requires --spec-dir specs/<id>")

    if args.snapshot:
        scope = "snapshot"
    elif args.verify_passes:
        scope = "verify-passes"
    else:
        scope = "git"
    label = args.task or args.feature or scope

    marker: str | None = None
    try:
        repo = Path(args.repo) if args.repo else (_git_toplevel(Path.cwd()) or Path.cwd())
        if args.snapshot:
            hard, advisory = run_snapshot(Path(args.snapshot), repo)
            # On PASS with a task id, record the honor-gate marker (best-effort; a
            # write failure warns loudly but never changes the exit code).
            if not hard and args.task:
                snap = Path(args.snapshot)
                feature_dir = snap.parent
                feature_id = args.feature or feature_dir.name
                written = write_pass_marker(feature_dir, feature_id, args.task,
                                            _sha256_of_snapshot(snap))
                marker = str(written) if written else None
        elif args.verify_passes:
            hard, advisory, feature_id = run_verify_passes(Path(args.spec_dir), repo, args.feature)
            label = feature_id
        else:
            if _git_toplevel(repo) is None:
                raise TestGuardError("not inside a git repository — cannot run the --base diff gate")
            hard, advisory = run_git(repo, args.base, args.head, args.test_glob)
    except TestGuardError as e:
        if args.json:
            print(json.dumps({"status": "error", "mode": scope, "message": str(e)}))
        else:
            print(f"test-guard [{scope}]: ERROR — could not run: {e}", file=sys.stderr)
            print("  -> fall back to the manual test-integrity check (loudly).", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 — any unexpected failure honors the exit-2 contract,
        # never leaks a traceback that exits 1 and impersonates a hard FAIL to a gating caller.
        if args.json:
            print(json.dumps({"status": "error", "mode": scope, "message": f"unexpected: {e}"}))
        else:
            print(f"test-guard [{scope}]: ERROR — unexpected failure: {e}", file=sys.stderr)
            print("  -> fall back to the manual test-integrity check (loudly).", file=sys.stderr)
        return 2

    return emit(scope, label, hard, advisory, args.json, marker=marker)


if __name__ == "__main__":
    sys.exit(main())
