import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/skills/ce-auto-build/scripts/worktree-merge.py"


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, timeout=30,
    )


def run_script(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, timeout=60,
    )


def init_repo(root: Path) -> None:
    git(root, "init", "-q")
    # Deterministic protected branch across git versions/config.
    git(root, "checkout", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "T")
    (root / "base.txt").write_text("line1\nline2\nline3\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")


class WorktreeMerge(unittest.TestCase):
    def test_clean_merge_stages_uncommitted_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            # Run branch (what auto-build checks out) + a feature branch that
            # touches a DIFFERENT file — a clean merge.
            git(root, "checkout", "-q", "-b", "auto-build/x")
            git(root, "checkout", "-q", "-b", "feat-a")
            (root / "a.txt").write_text("A\n", encoding="utf-8")
            git(root, "add", "-A")
            git(root, "commit", "-q", "-m", "feat-a")
            git(root, "checkout", "-q", "auto-build/x")

            res = run_script("merge", "--from-branch", "feat-a",
                             "--into", "auto-build/x", "--root", str(root), "--json")
            self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
            data = json.loads(res.stdout)
            self.assertEqual(data["status"], "merged")
            self.assertTrue(data["staged"])
            # Merge is staged but NOT committed: HEAD still at the pre-merge commit,
            # and a.txt is staged.
            log = git(root, "log", "--oneline").stdout
            self.assertNotIn("Merge", log)
            staged = git(root, "diff", "--cached", "--name-only").stdout
            self.assertIn("a.txt", staged)

    def test_conflict_returns_exit_1_with_paths_and_aborts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            git(root, "checkout", "-q", "-b", "auto-build/x")
            # Diverge base.txt on both branches -> conflict.
            (root / "base.txt").write_text("line1\nRUN\nline3\n", encoding="utf-8")
            git(root, "add", "-A")
            git(root, "commit", "-q", "-m", "run-edit")
            git(root, "checkout", "-q", "-b", "feat-b", "main")
            (root / "base.txt").write_text("line1\nFEAT\nline3\n", encoding="utf-8")
            git(root, "add", "-A")
            git(root, "commit", "-q", "-m", "feat-edit")
            git(root, "checkout", "-q", "auto-build/x")

            res = run_script("merge", "--from-branch", "feat-b",
                             "--into", "auto-build/x", "--root", str(root), "--json")
            self.assertEqual(res.returncode, 1, res.stderr + res.stdout)
            data = json.loads(res.stdout)
            self.assertEqual(data["status"], "conflict")
            self.assertIn("base.txt", data["conflicts"])
            self.assertTrue(data["aborted"])
            # Tree is clean again (abort ran) — no MERGE_HEAD, no unmerged paths.
            self.assertEqual(git(root, "status", "--porcelain").stdout.strip(), "")
            self.assertFalse((root / ".git" / "MERGE_HEAD").exists())

    def test_merge_into_protected_main_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            git(root, "checkout", "-q", "-b", "feat-c", "main")
            (root / "c.txt").write_text("C\n", encoding="utf-8")
            git(root, "add", "-A")
            git(root, "commit", "-q", "-m", "feat-c")
            git(root, "checkout", "-q", "main")

            res = run_script("merge", "--from-branch", "feat-c",
                             "--into", "main", "--root", str(root), "--json")
            self.assertEqual(res.returncode, 2, res.stderr + res.stdout)
            data = json.loads(res.stdout)
            self.assertEqual(data["status"], "refused")
            self.assertIn("protected", data["reason"])
            # No merge happened.
            self.assertEqual(git(root, "status", "--porcelain").stdout.strip(), "")

    def test_merge_refuses_dirty_target_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            git(root, "checkout", "-q", "-b", "auto-build/x")
            git(root, "checkout", "-q", "-b", "feat-d")
            (root / "d.txt").write_text("D\n", encoding="utf-8")
            git(root, "add", "-A")
            git(root, "commit", "-q", "-m", "feat-d")
            git(root, "checkout", "-q", "auto-build/x")
            # Dirty the target tree.
            (root / "dirt.txt").write_text("dirt\n", encoding="utf-8")

            res = run_script("merge", "--from-branch", "feat-d",
                             "--into", "auto-build/x", "--root", str(root), "--json")
            self.assertEqual(res.returncode, 2, res.stderr + res.stdout)
            data = json.loads(res.stdout)
            self.assertEqual(data["status"], "refused")
            self.assertIn("dirty", data["reason"])

    def test_merge_refuses_wrong_current_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            git(root, "checkout", "-q", "-b", "auto-build/x")
            git(root, "checkout", "-q", "-b", "feat-e")
            (root / "e.txt").write_text("E\n", encoding="utf-8")
            git(root, "add", "-A")
            git(root, "commit", "-q", "-m", "feat-e")
            # Stay on feat-e (NOT auto-build/x) but claim --into auto-build/x.
            res = run_script("merge", "--from-branch", "feat-e",
                             "--into", "auto-build/x", "--root", str(root), "--json")
            self.assertEqual(res.returncode, 2, res.stderr + res.stdout)
            data = json.loads(res.stdout)
            self.assertEqual(data["status"], "refused")
            self.assertIn("wrong branch", data["reason"])

    def test_create_and_list_and_remove(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            wt = root / "wt-feat"
            res = run_script("create", "--branch", "feat-wt", "--path", str(wt),
                             "--root", str(root), "--json")
            self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
            data = json.loads(res.stdout)
            self.assertEqual(data["status"], "created")
            self.assertTrue(wt.is_dir())

            res_l = run_script("list", "--root", str(root), "--json")
            self.assertEqual(res_l.returncode, 0, res_l.stderr)
            listed = json.loads(res_l.stdout)
            paths = [w["path"] for w in listed["worktrees"]]
            self.assertTrue(any("wt-feat" in p for p in paths))

            res_r = run_script("remove", "--path", str(wt),
                               "--root", str(root), "--json")
            self.assertEqual(res_r.returncode, 0, res_r.stderr + res_r.stdout)
            self.assertEqual(json.loads(res_r.stdout)["status"], "removed")

    def test_create_refuses_nonempty_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            wt = root / "occupied"
            wt.mkdir()
            (wt / "stuff.txt").write_text("x\n", encoding="utf-8")
            res = run_script("create", "--branch", "feat-occ", "--path", str(wt),
                             "--root", str(root), "--json")
            self.assertEqual(res.returncode, 2, res.stderr + res.stdout)
            self.assertEqual(json.loads(res.stdout)["status"], "refused")

    def test_no_subcommand_exits_two(self):
        res = run_script()
        self.assertEqual(res.returncode, 2)


if __name__ == "__main__":
    unittest.main()
