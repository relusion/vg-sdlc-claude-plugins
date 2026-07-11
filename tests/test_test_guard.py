"""Tests for skills/ce-implement/scripts/test-guard.py.

The regression that matters most for the merge bar: an ordinary prose edit to a
spec-driven repo's own `docs/plans/*/specs/*/spec.md` must NOT be read as a
weakened test and fail the bar. spec.md lives under a `specs/` directory (which
the test-file directory heuristic matches) and its prose carries words like
"require"/"verify" (which the assertion heuristic counts) — before the
non-code-extension guard, rewording it dropped the "assertion" count and raised
a hard T2 finding. This suite pins that closed while proving real test
weakening is still caught.
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/skills/ce-implement/scripts/test-guard.py"

_spec = importlib.util.spec_from_file_location("test_guard_mod", SCRIPT)
tg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tg)

GIT_ENV = dict(
    os.environ,
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
    GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
    GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t",
)


class IsTestFileHeuristic(unittest.TestCase):
    def test_prose_spec_under_specs_dir_is_not_a_test(self):
        self.assertFalse(tg.is_test_file("docs/plans/auth/specs/01-login/spec.md", []))
        self.assertFalse(tg.is_test_file("docs/plans/auth/specs/01-login/tasks.json", []))
        self.assertFalse(tg.is_test_file("api/specs/openapi.yaml", []))
        self.assertFalse(tg.is_test_file("specs/pricing.md", []))

    def test_real_test_files_still_detected(self):
        self.assertTrue(tg.is_test_file("tests/test_login.py", []))
        self.assertTrue(tg.is_test_file("src/foo.test.ts", []))
        self.assertTrue(tg.is_test_file("pkg/foo_test.go", []))
        self.assertTrue(tg.is_test_file("tests/helpers.py", []))  # dir heuristic, code ext

    def test_explicit_glob_still_wins_over_extension(self):
        self.assertTrue(tg.is_test_file("cases/login.md", ["*.md"]))


class GitModeMergeBar(unittest.TestCase):
    def _repo(self, tmp):
        root = Path(tmp)
        subprocess.run(["git", "-C", str(root), "init", "-q"], env=GIT_ENV, check=True)
        return root

    def _commit(self, root, msg):
        subprocess.run(["git", "-C", str(root), "add", "-A"], env=GIT_ENV, check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", msg],
                       env=GIT_ENV, check=True)

    def _run(self, root):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--base", "HEAD~1", "--head", "HEAD",
             "--repo", str(root), "--json"],
            capture_output=True, text=True, env=GIT_ENV,
        )

    def test_spec_prose_reword_stays_green(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._repo(tmp)
            spec = root / "docs/plans/auth/specs/01-login/spec.md"
            spec.parent.mkdir(parents=True)
            spec.write_text(
                "# Login\n\nThe system SHALL require a verified email.\n"
                "It SHALL verify the password and should reject empty input.\n",
                encoding="utf-8")
            self._commit(root, "add spec")
            # Reword prose — drops every word the assertion heuristic counts
            # (require/verify/should). This must NOT be read as removed assertions.
            spec.write_text(
                "# Login\n\nThe system needs a confirmed email.\n"
                "It checks the password and rejects empty input.\n",
                encoding="utf-8")
            self._commit(root, "reword spec")
            res = self._run(root)
            self.assertEqual(res.returncode, 0,
                             f"spec reword false-redded the bar:\n{res.stdout}\n{res.stderr}")
            self.assertIn('"status": "pass"', res.stdout)

    def test_real_test_weakening_still_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._repo(tmp)
            t = root / "tests/test_login.py"
            t.parent.mkdir(parents=True)
            t.write_text(
                "def test_login():\n"
                "    assert login('a','b') is True\n"
                "    assert audit_logged() is True\n",
                encoding="utf-8")
            self._commit(root, "add test")
            t.write_text(
                "def test_login():\n"
                "    assert login('a','b') is True\n",  # one assertion removed
                encoding="utf-8")
            self._commit(root, "weaken test")
            res = self._run(root)
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("T2", res.stdout)


class SnapshotPassMarker(unittest.TestCase):
    """--snapshot PASS (with --task) appends a source-of-truth ledger entry to
    .test-guard/<feature-id>/passes.json — the marker WS4-T4 adds and WS3-T3 derives
    tasks.json's `test_run_digest` from."""

    def _snapshot(self, root, feature="01-login", task="T-1", weaken=False):
        wt = root / "tests/test_x.py"
        wt.parent.mkdir(parents=True, exist_ok=True)
        strong = "def test_x():\n    assert f() == 1\n    assert g() == 2\n"
        wt.write_text("def test_x():\n    assert f() == 1\n" if weaken else strong,
                      encoding="utf-8")
        snap = root / ".test-guard" / feature / task / "tests"
        snap.mkdir(parents=True)
        (snap / "test_x.py").write_text(strong, encoding="utf-8")  # red baseline
        return root / ".test-guard" / feature / task

    def _run(self, snapdir, root, task="T-1"):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--snapshot", str(snapdir),
             "--task", task, "--repo", str(root), "--json"],
            capture_output=True, text=True, env=GIT_ENV,
        )

    def test_pass_writes_marker_with_derivable_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapdir = self._snapshot(root)
            res = self._run(snapdir, root)
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            passes = root / ".test-guard/01-login/passes.json"
            self.assertTrue(passes.is_file(), "passes.json not written on PASS")
            ledger = json.loads(passes.read_text())
            self.assertEqual(ledger["feature_id"], "01-login")
            self.assertEqual(len(ledger["passes"]), 1)
            entry = ledger["passes"][0]
            self.assertEqual(entry["task_id"], "T-1")
            self.assertEqual(entry["verdict"], "pass")
            self.assertRegex(entry["ts"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
            # WS3-T3 projects this straight into tasks.json test_run_digest.
            self.assertRegex(entry["snapshot_sha256"], r"^sha256:[0-9a-f]{64}$")

    def test_fail_writes_no_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapdir = self._snapshot(root, weaken=True)  # green drops an assertion
            res = self._run(snapdir, root)
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertFalse((root / ".test-guard/01-login/passes.json").exists(),
                             "a weakened (FAIL) task must not record a PASS marker")

    def test_reruns_append_not_clobber(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapdir = self._snapshot(root)
            self._run(snapdir, root)
            self._run(snapdir, root)
            ledger = json.loads((root / ".test-guard/01-login/passes.json").read_text())
            self.assertEqual(len(ledger["passes"]), 2, "append-only ledger expected")


class VerifyPassesHonorGate(unittest.TestCase):
    """--verify-passes fails a `done` task carrying an `auto` test case that left no
    PASS marker — the honor gap a task skipping the snapshot would otherwise slip."""

    def _spec(self, root, feature="01-login"):
        d = root / "specs" / feature
        d.mkdir(parents=True)
        (d / "ce-spec.md").write_text(
            "## TC-1\nmodality: cli\nverification: auto\n\n"
            "## TC-2\nmodality: manual\nverification: manual:judgment\n",
            encoding="utf-8")
        (d / "tasks.json").write_text(json.dumps({
            "feature_id": feature,
            "tasks": [
                {"id": "T-1", "status": "done", "verifies": ["TC-1"]},   # done + auto
                {"id": "T-2", "status": "done", "verifies": ["TC-2"]},   # done, manual-only
                {"id": "T-3", "status": "todo", "verifies": ["TC-1"]},   # not done yet
            ],
        }), encoding="utf-8")
        return d

    def _marker(self, root, feature="01-login", task="T-1"):
        p = root / ".test-guard" / feature / "passes.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({
            "schema": "test-guard/passes@1", "feature_id": feature,
            "passes": [{"task_id": task, "verdict": "pass",
                        "ts": "2026-07-04T00:00:00Z",
                        "snapshot_sha256": "sha256:" + "0" * 64}],
        }), encoding="utf-8")

    def _run(self, root, spec_dir):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--verify-passes",
             "--spec-dir", str(spec_dir), "--repo", str(root), "--json"],
            capture_output=True, text=True, env=GIT_ENV,
        )

    def test_done_auto_task_without_marker_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec_dir = self._spec(root)
            res = self._run(root, spec_dir)          # no passes.json at all
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("PG1", res.stdout)
            self.assertIn("T-1", res.stdout)
            self.assertNotIn("T-2", res.stdout)      # manual-only done task skipped
            self.assertNotIn("T-3", res.stdout)      # not-done task skipped

    def test_marker_present_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec_dir = self._spec(root)
            self._marker(root)
            res = self._run(root, spec_dir)
            self.assertEqual(res.returncode, 0, res.stdout)
            self.assertIn('"status": "pass"', res.stdout)


if __name__ == "__main__":
    unittest.main()
