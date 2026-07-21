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
    def test_readiness_separates_local_configuration_from_host_enforcement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(json.dumps({
                "scripts": {"test": "vitest"}
            }), encoding="utf-8")
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "merge-bar.yml").write_text(
                "steps:\n"
                "  - uses: relusion/vg-sdlc-claude-plugins/action/merge-bar@"
                + "a" * 40 + "\n",
                encoding="utf-8",
            )
            (root / ".github" / "CODEOWNERS").write_text("* @owners\n", encoding="utf-8")

            written = run_profile(root, "--write", "--json")
            self.assertEqual(written.returncode, 0, written.stderr)
            res = run_profile(root, "--readiness", "--json")
            self.assertEqual(res.returncode, 0, res.stderr)
            readiness = json.loads(res.stdout)["readiness"]

            self.assertEqual(readiness["core_workflows"]["status"], "ready")
            self.assertEqual(
                readiness["team_quality_bar"]["status"],
                "local-ready-host-unverified",
            )
            checks = {item["id"]: item for item in readiness["checks"]}
            self.assertEqual(checks["merge-bar-configuration"]["status"], "pass")
            self.assertEqual(checks["host-merge-policy"]["status"], "external-unverified")
            self.assertIn("not a compliance attestation", " ".join(readiness["limitations"]))

    def test_readiness_names_actionable_local_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            res = run_profile(root, "--readiness", "--json")
            self.assertEqual(res.returncode, 0, res.stderr)
            readiness = json.loads(res.stdout)["readiness"]
            self.assertEqual(readiness["core_workflows"]["status"], "action-required")
            self.assertIn("starter-artifacts", readiness["core_workflows"]["blocking_checks"])
            self.assertIn("test-command", readiness["core_workflows"]["blocking_checks"])
            self.assertIn(
                "merge-bar-configuration",
                readiness["team_quality_bar"]["blocking_checks"],
            )

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
