import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

MANIFEST = "plugins/core-engineering/fork-manifest.json"
CANONICAL = "plugins/core-engineering/skills/ce-implement/scripts/dep-guard.py"
COPY = "plugins/core-engineering/skills/ce-verify/scripts/dep-guard.py"

try:
    import yaml  # noqa: F401
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False


class ForkSync(unittest.TestCase):
    def _copy_repo(self, tmp: Path) -> Path:
        dst = tmp / "repo"
        for sub in ("scripts", "plugins"):
            shutil.copytree(
                REPO / sub, dst / sub, ignore=shutil.ignore_patterns("__pycache__")
            )
        return dst

    def _run(self, repo: Path, *args: str):
        return subprocess.run(
            [sys.executable, str(repo / "scripts" / "fork_sync.py"), "--root", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_clean_repo_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            res = self._run(repo)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("in sync", res.stdout)

    def test_drifted_copy_fails_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            copy = repo / COPY
            copy.write_text(copy.read_text(encoding="utf-8") + "\n# drift\n")
            res = self._run(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("drift", res.stderr)
            self.assertIn(COPY, res.stderr)

    def test_write_repairs_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            copy = repo / COPY
            copy.write_text(copy.read_text(encoding="utf-8") + "\n# drift\n")
            res = self._run(repo, "--write")
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("synced", res.stdout)
            self.assertEqual(
                copy.read_bytes(), (repo / CANONICAL).read_bytes()
            )
            self.assertEqual(self._run(repo).returncode, 0)

    def test_missing_copy_detected_and_restored(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            (repo / COPY).unlink()
            res = self._run(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("missing copy", res.stderr)
            res = self._run(repo, "--write")
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertTrue((repo / COPY).is_file())

    def test_missing_canonical_is_structural_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            (repo / CANONICAL).unlink()
            res = self._run(repo)
            self.assertEqual(res.returncode, 2)
            self.assertIn("canonical missing", res.stderr)

    def test_malformed_manifest_is_structural_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            (repo / MANIFEST).write_text("{not json", encoding="utf-8")
            res = self._run(repo)
            self.assertEqual(res.returncode, 2)
            self.assertIn("unreadable manifest", res.stderr)

    def test_duplicate_copy_entry_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            manifest_path = repo / MANIFEST
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            for fork in data["forks"]:
                if fork["canonical"] == CANONICAL:
                    fork["copies"].append(COPY)
            manifest_path.write_text(json.dumps(data), encoding="utf-8")
            res = self._run(repo)
            self.assertEqual(res.returncode, 2)
            self.assertIn("duplicate copy", res.stderr)

    def test_hand_edit_hint_names_the_canonical_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            copy = repo / COPY
            copy.write_text(copy.read_text(encoding="utf-8") + "\n# drift\n")
            res = self._run(repo)
            self.assertIn("edit the CANONICAL", res.stderr)

    # --- WS4-T10: a canonical may live at repo-root scripts/ (gate_runner.py) ---
    # while copies stay plugins-only. These exercise the bad_path() relaxation.

    def _add_fork(self, repo: Path, canonical: str, copies: list[str]) -> None:
        manifest_path = repo / MANIFEST
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        data["forks"].append({"canonical": canonical, "copies": copies,
                              "why": "test fixture"})
        manifest_path.write_text(json.dumps(data), encoding="utf-8")

    def test_scripts_prefixed_canonical_is_accepted_and_synced(self):
        # A repo-root scripts/ CANONICAL (the packaging shape gate_runner.py needs:
        # it lives OUTSIDE the plugin) is permitted; --write forks a plugins/ copy.
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            canonical = repo / "scripts" / "synthetic-gate.py"
            canonical.write_text("#!/usr/bin/env python3\n# synthetic\n")
            copy_rel = "plugins/core-engineering/skills/ce-ask/scripts/synthetic-gate.py"
            self._add_fork(repo, "scripts/synthetic-gate.py", [copy_rel])
            res = self._run(repo, "--write")
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertEqual((repo / copy_rel).read_bytes(), canonical.read_bytes())
            self.assertEqual(self._run(repo).returncode, 0)

    def test_scripts_prefixed_copy_is_rejected(self):
        # The relaxation is canonical-only: a COPY must still live under plugins/
        # (it ships beside a skill, reachable via CLAUDE_SKILL_DIR).
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            canonical = repo / "scripts" / "neg-canonical.py"
            canonical.write_text("#!/usr/bin/env python3\n# neg\n")
            self._add_fork(repo, "scripts/neg-canonical.py", ["scripts/neg-copy.py"])
            res = self._run(repo)
            self.assertEqual(res.returncode, 2)
            self.assertIn("a forked copy lives under plugins/", res.stderr)

    def test_shipped_gate_runner_fork_is_registered_and_identical(self):
        # Regression lock for WS4-T10's Done-when: the merge-bar runner is forked
        # into ce-auto-build and stays byte-identical to the repo-root canonical.
        data = json.loads((REPO / MANIFEST).read_text(encoding="utf-8"))
        entry = next((f for f in data["forks"]
                      if f["canonical"] == "scripts/gate_runner.py"), None)
        self.assertIsNotNone(entry, "scripts/gate_runner.py fork must be registered")
        copy_rel = "plugins/core-engineering/skills/ce-auto-build/scripts/gate_runner.py"
        self.assertIn(copy_rel, entry["copies"])
        self.assertEqual((REPO / copy_rel).read_bytes(),
                         (REPO / "scripts/gate_runner.py").read_bytes())


@unittest.skipUnless(HAVE_YAML, "check.py §5c integration needs pyyaml")
class CheckPyUnregisteredFork(unittest.TestCase):
    """Prove check.py §5c fires — mutate a repo copy, run check.py, expect FAIL.

    §5 only guards files REGISTERED in fork-manifest.json; §5c closes the
    append-by-memory hole where a contributor hand-copies a canonical into a
    new skill's scripts/ dir without registering it. A clean copy must PASS
    first, so a red result on the mutation is a real catch.
    """

    def _copy_repo(self, tmp: Path) -> Path:
        dst = tmp / "repo"
        for sub in (
            ".github", "action", "scripts", "plugins", "managed-agent-cookbooks",
            ".claude-plugin", "docs", "evals", "templates", "tests"
        ):
            shutil.copytree(
                REPO / sub, dst / sub, ignore=shutil.ignore_patterns("__pycache__")
            )
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
            capture_output=True, text=True, timeout=120,
        )

    def test_clean_copy_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            res = self._check(repo)
            self.assertEqual(res.returncode, 0, res.stderr)

    def test_hand_copied_canonical_into_another_skill_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            canonical = repo / "plugins/core-engineering/skills/ce-spec/scripts/spec-lint.py"
            rogue = repo / "plugins/core-engineering/skills/ce-ask/scripts/spec-lint.py"
            shutil.copy2(canonical, rogue)
            res = self._check(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("unregistered fork", res.stderr)
            self.assertIn(
                "plugins/core-engineering/skills/ce-ask/scripts/spec-lint.py",
                res.stderr,
            )
            self.assertIn("fork-manifest.json", res.stderr)
            self.assertIn("fork_sync.py --write", res.stderr)

    def test_same_named_but_different_script_also_fails(self):
        # Path-based, not content-based: a legitimately different script that
        # reuses a canonical's basename must be renamed (the ambiguity IS the
        # hazard), so byte-inequality is no exemption.
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            rogue = repo / "plugins/core-engineering/skills/ce-ask/scripts/dep-guard.py"
            rogue.write_text("#!/usr/bin/env python3\n# unrelated homonym\n")
            res = self._check(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("unregistered fork", res.stderr)
            self.assertIn("or rename it", res.stderr)

    def test_novel_basename_is_not_flagged(self):
        # False-positive control: a new script whose basename matches no
        # canonical is none of §5c's business.
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            novel = repo / "plugins/core-engineering/skills/ce-ask/scripts/ask-helper.py"
            novel.write_text("#!/usr/bin/env python3\n# novel helper\n")
            res = self._check(repo)
            self.assertEqual(res.returncode, 0, res.stderr)


if __name__ == "__main__":
    unittest.main()
