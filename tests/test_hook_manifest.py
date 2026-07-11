"""Tests for the hook self-integrity primitive (WS4-T12).

Covers the three done-when cases — a matching manifest passes, a tampered hook
is flagged, a missing manifest degrades loudly — across both halves: the
commit-time `scripts/hook_manifest.py` (--write / --check) and the runtime
SessionStart hook `hooks/hook-integrity.py`. The runtime hook is exercised by
copying the REAL script into a sandbox hooks dir (so its `__file__`-anchored
manifest lookup resolves there), proving the shipped logic, not a re-implement.
The committed manifest is also asserted fresh so a hook edit that skipped
`--write` cannot slip through green.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOOK_MANIFEST = REPO / "scripts" / "hook_manifest.py"
HOOK_INTEGRITY = REPO / "plugins" / "core-engineering" / "hooks" / "hook-integrity.py"
REAL_HOOKS_DIR = REPO / "plugins" / "core-engineering" / "hooks"
MANIFEST_NAME = "integrity-manifest.json"


def run_manifest(*args):
    return subprocess.run(
        [sys.executable, str(HOOK_MANIFEST), *args],
        capture_output=True, text=True, timeout=60)


def run_hook(hooks_dir: Path):
    """Run the copied hook-integrity.py inside *hooks_dir* with empty stdin,
    under a scrubbed env (no CLAUDE_* / harness), as SessionStart would."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_")}
    return subprocess.run(
        [sys.executable, str(hooks_dir / "hook-integrity.py")],
        input="", capture_output=True, text=True, timeout=60, env=env)


def make_sandbox(tmp: Path) -> Path:
    """A hooks dir with the real hook-integrity.py, two fake guards, a hooks.json,
    and a non-tracked guarded-secrets.json (to prove .json exclusion)."""
    hooks = tmp / "hooks"
    hooks.mkdir()
    shutil.copy(HOOK_INTEGRITY, hooks / "hook-integrity.py")
    (hooks / "env-guard.py").write_text("# fake guard\nprint('env')\n", encoding="utf-8")
    (hooks / "git-guard.py").write_text("# fake guard\nprint('git')\n", encoding="utf-8")
    (hooks / "hooks.json").write_text('{"hooks": {}}\n', encoding="utf-8")
    (hooks / "guarded-secrets.json").write_text('{"patterns": []}\n', encoding="utf-8")
    return hooks


class TestHookManifestCLI(unittest.TestCase):
    def test_write_then_check_passes(self):
        """A freshly written manifest checks clean (matching manifest passes)."""
        with tempfile.TemporaryDirectory() as td:
            hooks = make_sandbox(Path(td))
            w = run_manifest("--write", "--hooks-dir", str(hooks))
            self.assertEqual(w.returncode, 0, w.stderr)
            manifest = json.loads((hooks / MANIFEST_NAME).read_text())
            # tracks the .py files + hooks.json, excludes the non-hooks .json
            # and the manifest itself.
            self.assertEqual(
                set(manifest["hooks"]),
                {"env-guard.py", "git-guard.py", "hook-integrity.py", "hooks.json"},
            )
            self.assertNotIn("guarded-secrets.json", manifest["hooks"])
            self.assertNotIn(MANIFEST_NAME, manifest["hooks"])
            c = run_manifest("--check", "--hooks-dir", str(hooks))
            self.assertEqual(c.returncode, 0, c.stderr)

    def test_check_defaults_without_flag(self):
        """No mode flag defaults to --check."""
        with tempfile.TemporaryDirectory() as td:
            hooks = make_sandbox(Path(td))
            run_manifest("--write", "--hooks-dir", str(hooks))
            c = run_manifest("--hooks-dir", str(hooks))
            self.assertEqual(c.returncode, 0, c.stderr)

    def test_tampered_hook_flagged(self):
        """An edited hook after --write makes --check red and names the file."""
        with tempfile.TemporaryDirectory() as td:
            hooks = make_sandbox(Path(td))
            run_manifest("--write", "--hooks-dir", str(hooks))
            (hooks / "env-guard.py").write_text("# TAMPERED\n", encoding="utf-8")
            c = run_manifest("--check", "--hooks-dir", str(hooks))
            self.assertEqual(c.returncode, 1)
            self.assertIn("env-guard.py", c.stderr)
            self.assertIn("mismatch", c.stderr)

    def test_missing_hook_flagged(self):
        """A hook recorded in the manifest but deleted on disk is flagged."""
        with tempfile.TemporaryDirectory() as td:
            hooks = make_sandbox(Path(td))
            run_manifest("--write", "--hooks-dir", str(hooks))
            (hooks / "git-guard.py").unlink()
            c = run_manifest("--check", "--hooks-dir", str(hooks))
            self.assertEqual(c.returncode, 1)
            self.assertIn("git-guard.py", c.stderr)

    def test_unmanifested_hook_flagged(self):
        """A new hook added after --write (absent from the manifest) is flagged."""
        with tempfile.TemporaryDirectory() as td:
            hooks = make_sandbox(Path(td))
            run_manifest("--write", "--hooks-dir", str(hooks))
            (hooks / "rogue-guard.py").write_text("print('rogue')\n", encoding="utf-8")
            c = run_manifest("--check", "--hooks-dir", str(hooks))
            self.assertEqual(c.returncode, 1)
            self.assertIn("rogue-guard.py", c.stderr)

    def test_missing_manifest_degrades_loudly(self):
        """--check with no manifest present is a loud non-zero, not a silent pass."""
        with tempfile.TemporaryDirectory() as td:
            hooks = make_sandbox(Path(td))  # no --write, so no manifest
            c = run_manifest("--check", "--hooks-dir", str(hooks))
            self.assertEqual(c.returncode, 1)
            self.assertIn("missing", c.stderr.lower())

    def test_missing_hooks_dir_is_could_not_run(self):
        """A vanished hooks dir exits 2 (could-not-run), never a false green."""
        with tempfile.TemporaryDirectory() as td:
            c = run_manifest("--check", "--hooks-dir", str(Path(td) / "nope"))
            self.assertEqual(c.returncode, 2)

    def test_committed_manifest_is_fresh(self):
        """The shipped manifest matches the shipped hooks — guards that this task
        actually ran --write and that later hook edits refresh it."""
        c = run_manifest("--check")
        self.assertEqual(c.returncode, 0, c.stderr + c.stdout)


class TestHookIntegrityRuntime(unittest.TestCase):
    def test_clean_is_silent(self):
        """A fresh manifest → the SessionStart hook is silent and exits 0."""
        with tempfile.TemporaryDirectory() as td:
            hooks = make_sandbox(Path(td))
            run_manifest("--write", "--hooks-dir", str(hooks))
            r = run_hook(hooks)
            self.assertEqual(r.returncode, 0)
            self.assertEqual(r.stdout.strip(), "")
            self.assertEqual(r.stderr.strip(), "")

    def test_tampered_hook_warns_but_never_blocks(self):
        """A tampered guard → loud named warning, still exit 0 (never blocks)."""
        with tempfile.TemporaryDirectory() as td:
            hooks = make_sandbox(Path(td))
            run_manifest("--write", "--hooks-dir", str(hooks))
            (hooks / "env-guard.py").write_text("# TAMPERED\n", encoding="utf-8")
            r = run_hook(hooks)
            self.assertEqual(r.returncode, 0)  # warn, never block
            self.assertIn("env-guard.py", r.stderr)
            self.assertIn("WARNING", r.stderr)
            # also injected into the session as SessionStart additionalContext
            payload = json.loads(r.stdout)
            ctx = payload["hookSpecificOutput"]["additionalContext"]
            self.assertEqual(payload["hookSpecificOutput"]["hookEventName"],
                             "SessionStart")
            self.assertIn("env-guard.py", ctx)

    def test_missing_manifest_degrades_loudly(self):
        """No manifest → the hook warns that tampering cannot be detected, exit 0."""
        with tempfile.TemporaryDirectory() as td:
            hooks = make_sandbox(Path(td))  # no manifest written
            r = run_hook(hooks)
            self.assertEqual(r.returncode, 0)
            self.assertIn("missing", r.stderr.lower())
            self.assertIn("WARNING", r.stderr)


if __name__ == "__main__":
    unittest.main()
