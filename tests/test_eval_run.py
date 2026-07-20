"""Tests for scripts/eval_run.py, the Claude Code eval runner wrapper."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "eval_run.py"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=120,
    )


def copy_eval_repo(tmp: Path) -> Path:
    dst = tmp / "repo"
    for sub in ("scripts", "plugins", "evals"):
        shutil.copytree(REPO / sub, dst / sub, ignore=shutil.ignore_patterns("__pycache__"))
    return dst


class EvalRun(unittest.TestCase):
    def test_dry_run_single_scenario_writes_metadata_without_model_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            res = run("--scenario", "EVAL-003", "--out-dir", str(out))
            self.assertEqual(res.returncode, 0, f"stdout={res.stdout}\nstderr={res.stderr}")
            self.assertIn("would run", res.stdout)
            self.assertNotIn("--bare", res.stdout)
            self.assertNotIn("--max-budget-usd None", res.stdout)
            metadata = json.loads((out / "metadata.json").read_text())
            self.assertTrue(metadata["dry_run"])
            self.assertFalse(metadata["bare"])
            self.assertEqual(metadata["records"][0]["id"], "EVAL-003")
            self.assertTrue((out / "work" / "EVAL-003" / "README.md").is_file())
            self.assertFalse((out / "EVAL-003.md").exists())

    def test_bare_opt_in_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            res = run("--scenario", "EVAL-003", "--bare", "--out-dir", str(out))
            self.assertEqual(res.returncode, 0, f"stdout={res.stdout}\nstderr={res.stderr}")
            self.assertIn("--bare", res.stdout)
            metadata = json.loads((out / "metadata.json").read_text())
            self.assertTrue(metadata["bare"])
            self.assertIn("--bare", metadata["records"][0]["claude_command"])

    def test_requires_selection(self):
        res = run()
        self.assertEqual(res.returncode, 2)
        self.assertIn("choose --scenario", res.stderr)

    def test_execute_requires_budget_before_calling_claude(self):
        res = run("--scenario", "EVAL-003", "--execute", "--claude-bin", "definitely-not-claude")
        self.assertEqual(res.returncode, 2)
        self.assertIn("--execute requires --max-budget-usd", res.stderr)

    def test_execute_refuses_below_recommended_budget(self):
        res = run(
            "--scenario",
            "EVAL-008",
            "--execute",
            "--max-budget-usd",
            "1",
            "--claude-bin",
            "definitely-not-claude",
        )
        self.assertEqual(res.returncode, 2)
        self.assertIn("below the selected scenario recommendation", res.stderr)
        self.assertIn("--max-budget-usd 3", res.stderr)

    def test_profile_smoke_selects_read_only_smoke_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            res = run("--profile", "smoke", "--out-dir", str(out))
            self.assertEqual(res.returncode, 0, res.stderr)
            metadata = json.loads((out / "metadata.json").read_text())
            self.assertEqual(
                [record["id"] for record in metadata["records"]],
                ["EVAL-001", "EVAL-002", "EVAL-003", "EVAL-011", "EVAL-012", "EVAL-018"],
            )
            self.assertTrue(all(record["profile"] == "smoke" for record in metadata["records"]))

    def test_profile_benchmark_selects_cross_stack_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            res = run("--profile", "benchmark", "--out-dir", str(out))
            self.assertEqual(res.returncode, 0, res.stderr)
            metadata = json.loads((out / "metadata.json").read_text())
            self.assertEqual(
                [record["id"] for record in metadata["records"]],
                ["EVAL-013", "EVAL-014", "EVAL-015"],
            )
            self.assertTrue(all(record["profile"] == "benchmark" for record in metadata["records"]))
            self.assertTrue((out / "work" / "EVAL-013" / "src" / "api" / "routes.ts").is_file())

    def test_unknown_scenario_fails_cleanly(self):
        res = run("--scenario", "EVAL-999")
        self.assertEqual(res.returncode, 2)
        self.assertIn("unknown scenario id", res.stderr)

    def test_fixture_copy_is_replaced_between_dry_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            res1 = run("--scenario", "EVAL-003", "--out-dir", str(out))
            self.assertEqual(res1.returncode, 0, res1.stderr)
            marker = out / "work" / "EVAL-003" / "marker.txt"
            marker.write_text("stale")
            res2 = run("--scenario", "EVAL-003", "--out-dir", str(out))
            self.assertEqual(res2.returncode, 0, res2.stderr)
            self.assertFalse(marker.exists())

    def test_live_fixture_is_a_clean_git_worktree_before_claude_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "run"
            fake = root / "fake-claude"
            fake.write_text(
                "#!/bin/sh\n"
                "test \"$(git rev-parse --show-toplevel)\" = \"$PWD\" || exit 20\n"
                "test -z \"$(git status --porcelain --untracked-files=all)\" || exit 21\n"
                "git log -1 --format='%an <%ae>'\n"
            )
            fake.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{root}:{env.get('PATH', '')}"
            env["GIT_DIR"] = str(root / "wrong-git-dir")
            env["GIT_WORK_TREE"] = str(root / "wrong-work-tree")
            res = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--scenario",
                    "EVAL-003",
                    "--execute",
                    "--max-budget-usd",
                    "1.00",
                    "--claude-bin",
                    "fake-claude",
                    "--skip-check",
                    "--out-dir",
                    str(out),
                ],
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            self.assertEqual(res.returncode, 0, f"stdout={res.stdout}\nstderr={res.stderr}")
            output = (out / "EVAL-003.md").read_text()
            self.assertIn("Claude Code Eval <claude-code-eval@example.invalid>", output)

    def test_bad_fixture_in_catalog_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            scenarios = repo / "evals" / "scenarios.json"
            data = json.loads(scenarios.read_text())
            data["scenarios"][0]["fixture"] = "missing-fixture"
            scenarios.write_text(json.dumps(data), encoding="utf-8")
            res = run("--root", str(repo), "--scenario", "EVAL-001")
            self.assertEqual(res.returncode, 2)
            self.assertIn("fixture not found", res.stderr)

    def test_budget_exceeded_failure_is_labeled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "run"
            fake = root / "fake-claude"
            fake.write_text("#!/bin/sh\necho 'Error: Exceeded USD budget (0.25)'\nexit 1\n")
            fake.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{root}:{env.get('PATH', '')}"
            res = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--scenario",
                    "EVAL-003",
                    "--execute",
                    "--max-budget-usd",
                    "0.25",
                    "--allow-low-budget",
                    "--claude-bin",
                    "fake-claude",
                    "--out-dir",
                    str(out),
                ],
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            self.assertEqual(res.returncode, 1)
            self.assertIn("budget exceeded", res.stderr)
            metadata = json.loads((out / "metadata.json").read_text())
            self.assertEqual(metadata["records"][0]["failure_kind"], "budget-exceeded")
            self.assertIn("Exceeded USD budget", metadata["records"][0]["failure_message"])

    def test_auth_failure_is_labeled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "run"
            fake = root / "fake-claude"
            fake.write_text("#!/bin/sh\necho 'Not logged in · Please run /login'\nexit 1\n")
            fake.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{root}:{env.get('PATH', '')}"
            res = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--scenario",
                    "EVAL-003",
                    "--execute",
                    "--max-budget-usd",
                    "1.00",
                    "--bare",
                    "--claude-bin",
                    "fake-claude",
                    "--out-dir",
                    str(out),
                ],
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            self.assertEqual(res.returncode, 1)
            self.assertIn("authentication failed", res.stderr)
            self.assertIn("without --bare", res.stderr)
            metadata = json.loads((out / "metadata.json").read_text())
            self.assertEqual(metadata["records"][0]["failure_kind"], "auth-error")
            self.assertIn("Not logged in", metadata["records"][0]["failure_message"])


if __name__ == "__main__":
    unittest.main()
