"""Behavioral tests for implement-scope-guard.py (the Spec Lock's file boundary)
and the spec-lint H6 `tasks[].files` consistency check that makes it enforceable.

The guard fails any touched file outside the union of selected tasks[].files
(+ sanctioned bookkeeping). Two modes: in-loop (working-tree diff, one or more
explicit specs) and CI (committed base..head diff, all specs under a materialized
head tree). Posture: fail-closed when specs declare files, advisory-only on legacy
file-less specs.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GUARD = REPO / "plugins/core-engineering/skills/ce-implement/scripts/implement-scope-guard.py"
GUARD_COPY = REPO / "plugins/core-engineering/skills/ce-auto-build/scripts/implement-scope-guard.py"
SPEC_LINT = REPO / "plugins/core-engineering/skills/ce-spec/scripts/spec-lint.py"

GIT_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t.co",
    GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t.co",
    GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
)

SPEC_MD = "## TC-1 (proves AC-1)\nmodality: cli\nverification: auto\n"


def _git(repo, *args, check=True):
    return subprocess.run(["git", "-C", str(repo), *args], check=check,
                          capture_output=True, text=True, env=GIT_ENV, timeout=60)


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _tasks(*task_objs) -> str:
    return json.dumps({"feature_id": "01-feat", "tasks": list(task_objs)})


def _run_guard(*args) -> tuple[dict, int]:
    proc = subprocess.run([sys.executable, str(GUARD), *args, "--json"],
                          capture_output=True, text=True, timeout=60)
    try:
        payload = json.loads(proc.stdout)
    except ValueError:
        payload = {"_stdout": proc.stdout, "_stderr": proc.stderr}
    return payload, proc.returncode


class _RepoBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name) / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-q", "-b", "main")
        self.spec_dir = "docs/plans/demo/specs/01-feat"
        _write(self.repo / self.spec_dir / "ce-spec.md", SPEC_MD)

    def _set_tasks(self, tasks_json: str):
        _write(self.repo / self.spec_dir / "tasks.json", tasks_json)

    def _commit(self, msg="c"):
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", msg)
        return _git(self.repo, "rev-parse", "HEAD").stdout.strip()


@unittest.skipUnless(shutil.which("git"), "guard tests need git")
class InLoopMode(_RepoBase):
    def setUp(self):
        super().setUp()
        self._set_tasks(_tasks({"id": "T-1", "files": ["src/a.py"], "verifies": ["TC-1"]}))
        _write(self.repo / "src/a.py", "x = 1\n")
        self.base = self._commit("base")

    def _guard(self):
        return _run_guard("--spec-dir", str(self.repo / self.spec_dir),
                          "--base", self.base, "--repo", str(self.repo))

    def test_declared_file_change_passes(self):
        _write(self.repo / "src/a.py", "x = 2\n")
        payload, rc = self._guard()
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["hard_failures"], [])

    def test_repeated_spec_dirs_union_a_cumulative_sequential_diff(self):
        second = self.repo / "docs/plans/demo/specs/02-feat"
        _write(second / "ce-spec.md", SPEC_MD)
        _write(second / "tasks.json",
               _tasks({"id": "T-2", "files": ["src/b.py"], "verifies": ["TC-1"]}))
        _write(self.repo / "src/a.py", "x = 2\n")
        _write(self.repo / "src/b.py", "y = 1\n")
        payload, rc = _run_guard(
            "--spec-dir", str(self.repo / self.spec_dir),
            "--spec-dir", str(second),
            "--base", self.base, "--repo", str(self.repo),
        )
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["hard_failures"], [])
        _write(self.repo / "src/c.py", "z = 1\n")
        payload, rc = _run_guard(
            "--spec-dir", str(self.repo / self.spec_dir),
            "--spec-dir", str(second),
            "--base", self.base, "--repo", str(self.repo),
        )
        self.assertEqual(rc, 1, payload)
        self.assertTrue(any("src/c.py" in item for item in payload["hard_failures"]))

    def test_undeclared_tracked_change_is_a_spec_conflict(self):
        _write(self.repo / "src/a.py", "x = 2\n")
        _write(self.repo / "src/b.py", "y = 1\n")  # untracked, outside the set
        payload, rc = self._guard()
        self.assertEqual(rc, 1, payload)
        self.assertEqual(payload["status"], "fail")
        self.assertTrue(any("src/b.py" in h and "Spec Conflict" in h
                            for h in payload["hard_failures"]), payload["hard_failures"])

    def test_untracked_new_file_is_caught(self):
        # No tracked change at all — only an untracked stray file. gather must see it.
        _write(self.repo / "totally/rogue.py", "z = 1\n")
        payload, rc = self._guard()
        self.assertEqual(rc, 1, payload)
        self.assertTrue(any("totally/rogue.py" in h for h in payload["hard_failures"]))

    def test_bookkeeping_writes_are_allowed(self):
        # docs/adr promotion, .test-guard snapshots, and the plan/spec subtree.
        _write(self.repo / "docs/adr/0001-x.md", "adr\n")
        _write(self.repo / ".test-guard/01-feat/snap", "snap\n")
        _write(self.repo / self.spec_dir / "verification.md", "v\n")
        _write(self.repo / "docs/plans/demo/.metrics.jsonl", "{}\n")
        payload, rc = self._guard()
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["hard_failures"], [])

    def test_bare_file_at_sanctioned_dir_name_is_a_spec_conflict(self):
        # Finding 11: a FILE whose whole repo-relative path EQUALS a sanctioned
        # directory name (docs/adr, .test-guard) is outside the sanctioned subtree
        # (docs/adr/** / .test-guard/**) — it must go red. The dropped
        # `path == pre.rstrip('/')` disjunct used to pass it as in-scope.
        for bare in ("docs/adr", ".test-guard"):
            with self.subTest(bare=bare):
                _write(self.repo / bare, "not a directory\n")
                payload, rc = self._guard()
                self.assertEqual(rc, 1, payload)
                self.assertTrue(any(bare in h and "Spec Conflict" in h
                                    for h in payload["hard_failures"]),
                                payload["hard_failures"])
                (self.repo / bare).unlink()  # reset for the next sanctioned name

    def test_files_inside_sanctioned_subtrees_still_pass(self):
        # The prefix-only match must still ALLOW legit in-subtree bookkeeping files
        # (the startswith arm), so the fix does not over-flag.
        _write(self.repo / "docs/adr/0002-y.md", "adr\n")
        _write(self.repo / ".test-guard/01-feat/snap2", "snap\n")
        payload, rc = self._guard()
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["hard_failures"], [])

    def test_legacy_spec_without_files_is_advisory_not_fail(self):
        self._set_tasks(_tasks({"id": "T-1", "verifies": ["TC-1"]}))
        _write(self.repo / "src/anything.py", "a = 1\n")  # would fail if enforced
        payload, rc = self._guard()
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["hard_failures"], [])
        self.assertEqual(len(payload["advisory"]), 1)
        self.assertIn("legacy", payload["advisory"][0].lower())

    def test_unresolvable_base_errors_exit_2(self):
        payload, rc = _run_guard("--spec-dir", str(self.repo / self.spec_dir),
                                 "--base", "deadbeef", "--repo", str(self.repo))
        self.assertEqual(rc, 2, payload)
        self.assertEqual(payload["status"], "error")

    def test_missing_spec_dir_errors_exit_2(self):
        payload, rc = _run_guard("--spec-dir", str(self.repo / "docs/plans/nope"),
                                 "--base", self.base, "--repo", str(self.repo))
        self.assertEqual(rc, 2, payload)
        self.assertEqual(payload["status"], "error")

    def test_malformed_tasks_json_errors_exit_2(self):
        _write(self.repo / self.spec_dir / "tasks.json", "{ not json")
        payload, rc = self._guard()
        self.assertEqual(rc, 2, payload)
        self.assertEqual(payload["status"], "error")


@unittest.skipUnless(shutil.which("git"), "guard tests need git")
class CiMode(_RepoBase):
    def _guard(self, base, head):
        return _run_guard("--all-specs", "--head-tree", str(self.repo),
                          "--base", base, "--head", head, "--repo", str(self.repo))

    def test_committed_violation_goes_red(self):
        self._set_tasks(_tasks({"id": "T-1", "files": ["src/a.py"], "verifies": ["TC-1"]}))
        _write(self.repo / "src/a.py", "x = 1\n")
        base = self._commit("base")
        _write(self.repo / "src/rogue.py", "r = 1\n")
        head = self._commit("rogue")
        payload, rc = self._guard(base, head)
        self.assertEqual(rc, 1, payload)
        self.assertEqual(payload["status"], "fail")
        self.assertTrue(any("src/rogue.py" in h for h in payload["hard_failures"]))

    def test_clean_committed_change_passes(self):
        self._set_tasks(_tasks({"id": "T-1", "files": ["src/a.py"], "verifies": ["TC-1"]}))
        _write(self.repo / "src/a.py", "x = 1\n")
        base = self._commit("base")
        _write(self.repo / "src/a.py", "x = 2\n")
        head = self._commit("edit")
        payload, rc = self._guard(base, head)
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["hard_failures"], [])

    def test_union_across_multiple_specs(self):
        self._set_tasks(_tasks({"id": "T-1", "files": ["src/a.py"], "verifies": ["TC-1"]}))
        second = "docs/plans/demo/specs/02-feat"
        _write(self.repo / second / "ce-spec.md", SPEC_MD)
        _write(self.repo / second / "tasks.json",
               _tasks({"id": "T-9", "files": ["src/b.py"], "verifies": ["TC-1"]}))
        _write(self.repo / "src/a.py", "1\n")
        _write(self.repo / "src/b.py", "2\n")
        base = self._commit("base")
        # Both declared files change -> union covers both -> PASS.
        _write(self.repo / "src/a.py", "11\n")
        _write(self.repo / "src/b.py", "22\n")
        head = self._commit("edit")
        payload, rc = self._guard(base, head)
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["hard_failures"], [])

    def test_legacy_all_filesless_specs_are_advisory(self):
        self._set_tasks(_tasks({"id": "T-1", "verifies": ["TC-1"]}))
        _write(self.repo / "src/a.py", "1\n")
        base = self._commit("base")
        _write(self.repo / "src/whatever.py", "w = 1\n")
        head = self._commit("edit")
        payload, rc = self._guard(base, head)
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["hard_failures"], [])
        self.assertTrue(payload["advisory"])

    def test_missing_head_tree_errors_exit_2(self):
        self._set_tasks(_tasks({"id": "T-1", "files": ["src/a.py"], "verifies": ["TC-1"]}))
        _write(self.repo / "src/a.py", "1\n")
        base = self._commit("base")
        payload, rc = _run_guard("--all-specs", "--base", base, "--head", "HEAD",
                                 "--repo", str(self.repo))
        self.assertEqual(rc, 2, payload)
        self.assertEqual(payload["status"], "error")


class GuardShape(unittest.TestCase):
    def test_fork_copy_is_byte_identical(self):
        self.assertEqual(GUARD.read_bytes(), GUARD_COPY.read_bytes())

    def test_no_args_is_a_clean_exit_2_usage_error(self):
        # portability_check runs the script with no args; argparse's required
        # mutually-exclusive mode group must exit 2 (usage), never a traceback.
        proc = subprocess.run([sys.executable, str(GUARD)],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("Traceback", proc.stderr)


def _load_spec_lint():
    spec = importlib.util.spec_from_file_location("spec_lint_ws4t5", SPEC_LINT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class SpecLintH6(unittest.TestCase):
    """The prerequisite: spec-lint enforces tasks[].files consistency so the guard
    is not vacuous, WITHOUT breaking patch-lint's run_checks import."""

    def _lint_json(self, tasks_json: str) -> tuple[dict, int]:
        with tempfile.TemporaryDirectory() as tmp:
            sd = Path(tmp) / "specs" / "01-feat"
            _write(sd / "ce-spec.md", SPEC_MD)
            _write(sd / "tasks.json", tasks_json)
            proc = subprocess.run([sys.executable, str(SPEC_LINT), str(sd), "--json"],
                                  capture_output=True, text=True, timeout=30)
        return json.loads(proc.stdout), proc.returncode

    def test_all_tasks_with_files_pass(self):
        payload, rc = self._lint_json(_tasks(
            {"id": "T-1", "files": ["src/a.py"], "verifies": ["TC-1"]}))
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["status"], "pass")

    def test_partial_files_hard_fails_h6(self):
        payload, rc = self._lint_json(_tasks(
            {"id": "T-1", "files": ["src/a.py"], "verifies": ["TC-1"]},
            {"id": "T-2", "verifies": ["TC-1"]}))
        self.assertEqual(rc, 1, payload)
        self.assertEqual(payload["status"], "fail")
        self.assertTrue(any(h.startswith("H6 T-2") for h in payload["hard_failures"]),
                        payload["hard_failures"])

    def test_empty_files_list_counts_as_missing(self):
        payload, rc = self._lint_json(_tasks(
            {"id": "T-1", "files": ["src/a.py"], "verifies": ["TC-1"]},
            {"id": "T-2", "files": [], "verifies": ["TC-1"]}))
        self.assertEqual(rc, 1, payload)
        self.assertTrue(any(h.startswith("H6 T-2") for h in payload["hard_failures"]))

    def test_legacy_all_filesless_is_silent(self):
        # No task has files -> H6 N/A, no advisory, still passes (WS6-T1 tests rely
        # on this: a file-less spec must not gain a new advisory line).
        payload, rc = self._lint_json(_tasks({"id": "T-1", "verifies": ["TC-1"]}))
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["advisory"], [])

    def test_run_checks_import_default_ignores_files(self):
        # patch-lint calls sl.run_checks(parsed, tasks) with no enforce_files —
        # partial files must NOT hard-fail through that path.
        sl = _load_spec_lint()
        parsed = sl.parse_spec(SPEC_MD)
        tasks = {"feature_id": "f", "tasks": [
            {"id": "T-1", "files": ["src/a.py"], "verifies": ["TC-1"]},
            {"id": "T-2", "verifies": ["TC-1"]}]}
        hard, _adv = sl.run_checks(parsed, tasks)  # default enforce_files=False
        self.assertFalse(any(h.startswith("H6") for h in hard), hard)
        hard_on, _ = sl.run_checks(parsed, tasks, enforce_files=True)
        self.assertTrue(any(h.startswith("H6") for h in hard_on), hard_on)


if __name__ == "__main__":
    unittest.main()
