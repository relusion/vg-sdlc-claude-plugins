"""Integration tests for check.py's README skill-catalog drift gate."""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

try:
    import yaml  # noqa: F401
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False


@unittest.skipUnless(HAVE_YAML, "check.py integration needs pyyaml")
class CatalogCheck(unittest.TestCase):
    def _copy_repo(self, tmp: Path) -> Path:
        dst = tmp / "repo"
        for sub in (
            ".github", "action", "scripts", "plugins",
            ".claude-plugin", "docs", "evals", "templates", "tests"
        ):
            shutil.copytree(REPO / sub, dst / sub)
        shutil.copy2(REPO / "README.md", dst / "README.md")
        shutil.copy2(REPO / "CLAUDE.md", dst / "CLAUDE.md")
        shutil.copy2(REPO / "CONTRIBUTING.md", dst / "CONTRIBUTING.md")
        shutil.copy2(REPO / "COMMERCIAL.md", dst / "COMMERCIAL.md")
        shutil.copy2(REPO / "SECURITY.md", dst / "SECURITY.md")
        shutil.copy2(REPO / "THIRD_PARTY_NOTICES.md", dst / "THIRD_PARTY_NOTICES.md")
        shutil.copy2(REPO / "LICENSE", dst / "LICENSE")
        return dst

    def _check(self, repo: Path):
        return subprocess.run(
            [sys.executable, str(repo / "scripts" / "check.py"), "--no-install-hooks"],
            capture_output=True, text=True, timeout=60,
        )

    def test_clean_copy_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            res = self._check(repo)
            self.assertEqual(res.returncode, 0, res.stderr)

    def test_stale_readme_skill_count_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            count = len(list((repo / "plugins/core-engineering/skills").glob("*/SKILL.md")))
            readme = repo / "README.md"
            text = readme.read_text(encoding="utf-8")
            self.assertIn(f"{count} skills", text, "fixture drift: README count already stale")
            readme.write_text(text.replace(f"{count} skills", "23 skills", 1), encoding="utf-8")
            res = self._check(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn(f"current skill count '{count} skills'", res.stderr)

    def test_stale_readme_agent_count_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            readme = repo / "README.md"
            readme.write_text(
                readme.read_text(encoding="utf-8").replace(
                    "2 plugin-shipped custom agents", "1 plugin-shipped custom agent", 1),
                encoding="utf-8",
            )
            res = self._check(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn(
                "current agent count '2 plugin-shipped custom agents'",
                res.stderr,
            )

    def test_missing_readme_catalog_skill_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            readme = repo / "README.md"
            readme.write_text(
                readme.read_text(encoding="utf-8").replace(
                    ", `/ce-probe-infra`", "", 1),
                encoding="utf-8",
            )
            res = self._check(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("skill catalog missing skill(s)", res.stderr)
            self.assertIn("/ce-probe-infra", res.stderr)

    def test_agent_filename_must_match_frontmatter_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            agent = repo / "plugins/core-engineering/agents/spec-author.md"
            agent.write_text(
                agent.read_text(encoding="utf-8").replace(
                    "name: spec-author", "name: wrong-author", 1),
                encoding="utf-8",
            )
            res = self._check(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("name 'wrong-author' must match filename 'spec-author'", res.stderr)

    def test_plugin_agents_are_leaf_agents(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            agent = repo / "plugins/core-engineering/agents/spec-impl.md"
            agent.write_text(
                agent.read_text(encoding="utf-8").replace(
                    "tools: Read, Write, Edit, Glob, Grep, Bash, Skill",
                    "tools: Read, Write, Edit, Glob, Grep, Bash, Skill, Task",
                    1,
                ),
                encoding="utf-8",
            )
            res = self._check(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("plugin-shipped agents must be leaf agents", res.stderr)

    def test_core_engineering_skill_names_must_be_prefixed(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            skill = repo / "plugins/core-engineering/skills/unprefixed"
            skill.mkdir()
            (skill / "SKILL.md").write_text(
                "---\nname: unprefixed\ndescription: x\n---\n# Unprefixed\n",
                encoding="utf-8",
            )
            res = self._check(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("must start with 'ce-'", res.stderr)


if __name__ == "__main__":
    unittest.main()
