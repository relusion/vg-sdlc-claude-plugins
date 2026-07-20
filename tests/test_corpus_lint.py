import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class CorpusLint(unittest.TestCase):
    def _copy_repo(self, tmp: Path) -> Path:
        dst = tmp / "repo"
        for sub in ("scripts", "plugins", "docs"):
            shutil.copytree(REPO / sub, dst / sub)
        shutil.copy2(REPO / "README.md", dst / "README.md")
        shutil.copy2(REPO / "CLAUDE.md", dst / "CLAUDE.md")
        return dst

    def _lint(self, repo: Path):
        return subprocess.run(
            [sys.executable, str(repo / "scripts" / "corpus_lint.py"), "--root", str(repo)],
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_clean_copy_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            res = self._lint(repo)
            self.assertEqual(res.returncode, 0, res.stderr)

    def test_stale_public_alias_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            skill = repo / "plugins/core-engineering/skills/ce-probe-sec/SKILL.md"
            skill.write_text(skill.read_text(encoding="utf-8") + "\nUse `sec-probe`.\n")
            res = self._lint(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("stale public alias", res.stderr)
            self.assertIn("/core-engineering:ce-probe-sec", res.stderr)

    def test_unknown_ce_skill_reference_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            readme = repo / "README.md"
            readme.write_text(
                readme.read_text(encoding="utf-8")
                + "\nTry /core-engineering:ce-missing.\n"
            )
            res = self._lint(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("unknown skill '/core-engineering:ce-missing'", res.stderr)

    def test_bare_plugin_skill_reference_fails_with_namespaced_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            readme = repo / "README.md"
            readme.write_text(readme.read_text(encoding="utf-8") + "\nTry /ce-plan.\n")
            res = self._lint(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("unsupported bare plugin skill '/ce-plan'", res.stderr)
            self.assertIn("/core-engineering:ce-plan", res.stderr)

    def test_wrong_plugin_namespace_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            readme = repo / "README.md"
            readme.write_text(
                readme.read_text(encoding="utf-8")
                + "\nTry /product-discovery:ce-plan.\n"
            )
            res = self._lint(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("belongs to plugin 'core-engineering'", res.stderr)

    def test_missing_escalation_heading_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            skill = repo / "plugins/core-engineering/skills/ce-debug/SKILL.md"
            skill.write_text(
                skill.read_text(encoding="utf-8").replace("## Escalation", "## Routing", 1),
                encoding="utf-8",
            )
            res = self._lint(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("missing required heading '## Escalation'", res.stderr)

    def test_missing_skill_companion_reference_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            skill = repo / "plugins/core-engineering/skills/ce-spec/SKILL.md"
            skill.write_text(
                skill.read_text(encoding="utf-8")
                + "\nLoad `${CLAUDE_SKILL_DIR}/not-a-real-file.md`.\n",
                encoding="utf-8",
            )
            res = self._lint(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("not-a-real-file.md does not exist", res.stderr)

    def test_repo_only_contributor_doc_reference_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            skill = repo / "plugins/core-engineering/skills/ce-probe-sec/SKILL.md"
            skill.write_text(
                skill.read_text(encoding="utf-8")
                + "\nSee `docs/contributing/HITL-GATE-STANDARD.md`.\n",
                encoding="utf-8",
            )
            res = self._lint(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("repo-only contributor doc", res.stderr)
            self.assertIn("HITL-GATE-STANDARD.md", res.stderr)


if __name__ == "__main__":
    unittest.main()
