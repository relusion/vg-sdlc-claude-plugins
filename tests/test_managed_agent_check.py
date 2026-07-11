"""Tests for scripts/managed_agent_check.py, the CMA cookbook drift gate."""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "managed_agent_check.py"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=120,
    )


def copy_repo(tmp: Path) -> Path:
    dst = tmp / "repo"
    for sub in ("managed-agent-cookbooks", "plugins", "docs", "scripts"):
        shutil.copytree(REPO / sub, dst / sub, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(REPO / "README.md", dst / "README.md")
    shutil.copy2(REPO / "CLAUDE.md", dst / "CLAUDE.md")
    return dst


class ManagedAgentCheck(unittest.TestCase):
    def test_this_repo_managed_agent_surface_passes(self):
        res = run()
        self.assertEqual(res.returncode, 0, f"stdout={res.stdout}\nstderr={res.stderr}")
        self.assertIn("managed-agent: OK", res.stdout)

    def test_missing_cookbook_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            shutil.rmtree(repo / "managed-agent-cookbooks" / "quality-gate")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("missing expected cookbook", res.stderr)
            self.assertIn("quality-gate", res.stderr)

    def test_manifest_name_must_match_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            manifest = repo / "managed-agent-cookbooks" / "quality-gate" / "agent.yaml"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace("name: quality-gate", "name: quality", 1),
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("must match directory", res.stderr)

    def test_orchestrator_allowlist_must_include_cookbook(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            orchestrate = repo / "scripts" / "orchestrate.py"
            orchestrate.write_text(
                orchestrate.read_text(encoding="utf-8").replace('"release-coordinator",', ""),
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("ALLOWED_TARGETS missing", res.stderr)
            self.assertIn("release-coordinator", res.stderr)


if __name__ == "__main__":
    unittest.main()
