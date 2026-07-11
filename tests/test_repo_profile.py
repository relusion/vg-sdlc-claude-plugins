import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/skills/ce-init/scripts/repo-profile.py"


def run_profile(root: Path, *args: str):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        capture_output=True,
        text=True,
        timeout=120,
    )


class RepoProfile(unittest.TestCase):
    def test_detects_common_repo_signals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(json.dumps({
                "scripts": {"test": "vitest", "lint": "eslint .", "build": "vite build"}
            }), encoding="utf-8")
            (root / "pnpm-lock.yaml").write_text("lockfileVersion: '9'\n", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "auth.ts").write_text("export const login = true;\n", encoding="utf-8")
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")
            (root / "Dockerfile").write_text("FROM node:22\n", encoding="utf-8")

            res = run_profile(root, "--json")
            self.assertEqual(res.returncode, 0, res.stderr)
            data = json.loads(res.stdout)
            self.assertEqual(data["package_managers"][0]["manager"], "pnpm")
            self.assertIn("typescript", data["languages"]["counts"])
            self.assertEqual(data["commands"]["test"][0]["command"], "pnpm test")
            self.assertEqual(data["ci"][0]["provider"], "github-actions")
            self.assertIn("src/auth.ts", data["surfaces"]["security"])
            self.assertIn("Dockerfile", data["surfaces"]["infra"])

    def test_write_creates_missing_artifacts_and_skips_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
            (root / "tests").mkdir()

            res = run_profile(root, "--write", "--json")
            self.assertEqual(res.returncode, 0, res.stderr)
            data = json.loads(res.stdout)
            self.assertIn("docs/plans/repo-profile.json", data["artifact_writes"]["written"])
            self.assertTrue((root / "docs/plans/vc-policy.md").is_file())

            vc = root / "docs/plans/vc-policy.md"
            vc.write_text("# Human Policy\n", encoding="utf-8")
            res2 = run_profile(root, "--write", "--json")
            self.assertEqual(res2.returncode, 0, res2.stderr)
            data2 = json.loads(res2.stdout)
            self.assertIn("docs/plans/vc-policy.md", data2["artifact_writes"]["skipped_existing"])
            self.assertEqual(vc.read_text(encoding="utf-8"), "# Human Policy\n")


if __name__ == "__main__":
    unittest.main()
