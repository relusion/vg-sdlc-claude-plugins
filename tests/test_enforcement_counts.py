"""Integration tests for check.py §15 — derived enforcement counts.

The three enforcement counts the product docs quote must be derived, never
asserted: check.py re-derives them every run and compares against the
committed docs/enforcement-counts.json; `--write-counts` refreshes that file
and the three doc claim sites together.
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COUNTS_REL = Path("docs") / "enforcement-counts.json"
COUNTS_KEYS = ("repo_checks", "authoring_checks", "tests")

try:
    import yaml  # noqa: F401
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False


def copy_repo(tmp: Path) -> Path:
    dst = tmp / "repo"
    # check.py needs .claude-plugin (marketplace) plus everything the delegated
    # checkers walk; never the gitignored evals/runs/ (a fresh checkout has none).
    for sub in (".github", "action", "scripts", "plugins", "managed-agent-cookbooks",
                ".claude-plugin", "docs", "templates", "tests"):
        shutil.copytree(REPO / sub, dst / sub,
                        ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(REPO / "evals", dst / "evals",
                    ignore=shutil.ignore_patterns("__pycache__", "runs"))
    for name in ("README.md", "CLAUDE.md", "CONTRIBUTING.md", "COMMERCIAL.md",
                 "SECURITY.md", "THIRD_PARTY_NOTICES.md", "LICENSE"):
        shutil.copy2(REPO / name, dst / name)
    return dst


def run_check(repo: Path, *args):
    return subprocess.run(
        [sys.executable, str(repo / "scripts" / "check.py"),
         "--no-install-hooks", *args],
        capture_output=True, text=True, timeout=300,
    )


@unittest.skipUnless(HAVE_YAML, "check.py integration needs pyyaml")
class EnforcementCounts(unittest.TestCase):
    def test_stale_counts_file_fails(self):
        # counts.json asserting yesterday's numbers is exactly the drift class
        # WS1-T5 exists to kill: check.py must re-derive and go red.
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            counts_file = repo / COUNTS_REL
            data = json.loads(counts_file.read_text(encoding="utf-8"))
            data["authoring_checks"] += 1
            counts_file.write_text(json.dumps(data, indent=2) + "\n",
                                   encoding="utf-8")
            res = run_check(repo)
            self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
            self.assertIn("authoring_checks", res.stderr)
            self.assertIn("--write-counts", res.stderr)

    def test_missing_counts_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            (repo / COUNTS_REL).unlink()
            res = run_check(repo)
            self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
            self.assertIn("enforcement-counts.json", res.stderr)
            self.assertIn("--write-counts", res.stderr)

    def test_write_counts_converges_drifted_copy_to_green(self):
        # The one-command remediation: stale counts.json + a stale doc claim →
        # `--write-counts` rewrites all four sites and the tree is green again.
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            counts_file = repo / COUNTS_REL
            fresh = json.loads(counts_file.read_text(encoding="utf-8"))
            stale = dict(fresh)
            stale["repo_checks"] = fresh["repo_checks"] - 1
            stale["tests"] = fresh["tests"] + 3
            counts_file.write_text(json.dumps(stale, indent=2) + "\n",
                                   encoding="utf-8")
            readme = repo / "README.md"
            text = readme.read_text(encoding="utf-8")
            drifted = re.sub(r"(\d+) repo checks",
                             lambda m: f"{int(m.group(1)) + 7} repo checks",
                             text, count=1)
            self.assertNotEqual(text, drifted,
                                "fixture drift: no count claim in README")
            readme.write_text(drifted, encoding="utf-8")

            res = run_check(repo, "--write-counts")
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            self.assertIn("--write-counts:", res.stdout)

            # The copy is byte-equivalent to the repo, so the derived truth it
            # writes back must equal the committed numbers — determinism proof.
            written = json.loads(counts_file.read_text(encoding="utf-8"))
            for key in COUNTS_KEYS:
                self.assertEqual(written[key], fresh[key], key)
            match = re.search(r"(\d+) repo checks",
                              readme.read_text(encoding="utf-8"))
            self.assertEqual(int(match.group(1)), fresh["repo_checks"])

            res = run_check(repo)
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)


if __name__ == "__main__":
    unittest.main()
