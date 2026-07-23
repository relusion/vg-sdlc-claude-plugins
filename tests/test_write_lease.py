"""Tests for the forked write-lease.py — the session-lease halves of the write-scope discipline."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/skills/ce-review/scripts/write-lease.py"
HOOK = REPO / "plugins/core-engineering/hooks/write-scope-guard.py"
FORK_MANIFEST = REPO / "plugins/core-engineering/fork-manifest.json"
VERIFY_SKILL = REPO / "plugins/core-engineering/skills/ce-verify/SKILL.md"
VERIFY_REPORT_STAGE = (
    REPO / "plugins/core-engineering/skills/ce-verify/stage-3-acceptance-report.md"
)
LEASE_REL = ".claude/ce-write-scope.json"


def run_lease(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def read_lease(root: Path) -> dict:
    return json.loads((root / LEASE_REL).read_text(encoding="utf-8"))


class WriteLease(unittest.TestCase):
    def test_verify_declares_and_bundles_its_bounded_write_lease(self):
        manifest = json.loads(FORK_MANIFEST.read_text(encoding="utf-8"))
        write_lease_fork = next(
            fork for fork in manifest["forks"]
            if fork["canonical"].endswith("ce-review/scripts/write-lease.py")
        )
        verify_copy = "plugins/core-engineering/skills/ce-verify/scripts/write-lease.py"
        self.assertIn(verify_copy, write_lease_fork["copies"])

        contract = VERIFY_SKILL.read_text(encoding="utf-8")
        self.assertIn("--set --skill ce-verify", contract)
        self.assertIn("docs/plans/**/verification-report.md", contract)
        self.assertIn("docs/plans/**/verification-summary.json", contract)
        self.assertIn("docs/plans/**/.metrics.jsonl", contract)
        self.assertIn("--restore-baseline", contract)

        reporting = VERIFY_REPORT_STAGE.read_text(encoding="utf-8")
        self.assertIn("scripts/verification-gate.py", reporting)
        self.assertIn("verification-summary.json", reporting)
        self.assertIn("one `attestation` line for each interactive gate", reporting)
        self.assertIn("exactly one best-effort `run-terminal`", reporting)
        self.assertIn("resolved model, Claude CLI, and plugin versions", reporting)

    def test_set_writes_a_lease_with_baseline_denies(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run_lease("--set", "--skill", "ce-review",
                            "--allow", "docs/plans/**/code-review.md", "--root", tmp)
            self.assertEqual(res.returncode, 0, res.stderr)
            lease = read_lease(Path(tmp))
            self.assertEqual(lease["mode"], "lease")
            self.assertEqual(lease["skill"], "ce-review")
            self.assertTrue(lease["enabled"])
            self.assertIn("docs/plans/**/code-review.md", lease["allow"])
            self.assertIn(".git/**", lease["deny"])
            self.assertIn(LEASE_REL, lease["deny"])
            # The reason is a short statement of the lease; the lift path lives
            # only in the guard's deny message, never in the stored reason.
            self.assertIn("session write lease set by /core-engineering:ce-review", lease["reason"])
            self.assertNotIn("stale", lease["reason"])
            self.assertNotIn(LEASE_REL, lease["reason"])

    def test_set_stamps_lease_id_and_created_at(self):
        # The session-binding identity fields the write-scope-guard reads to bind
        # a lease to its session and detect a dead-session orphan.
        with tempfile.TemporaryDirectory() as tmp:
            run_lease("--set", "--skill", "ce-review", "--root", tmp)
            lease = read_lease(Path(tmp))
            # lease_id is a uuid4 string
            uuid.UUID(lease["lease_id"], version=4)
            # created_at is a parseable UTC ISO timestamp
            parsed = datetime.fromisoformat(lease["created_at"])
            self.assertIsNotNone(parsed.tzinfo, "created_at must be timezone-aware (UTC)")

    def test_each_set_mints_a_fresh_lease_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_lease("--set", "--skill", "ce-review", "--root", tmp)
            first = read_lease(Path(tmp))["lease_id"]
            run_lease("--set", "--skill", "ce-review", "--root", tmp)
            second = read_lease(Path(tmp))["lease_id"]
            self.assertNotEqual(first, second)

    def test_baseline_has_no_lease_id(self):
        # The deny-only baseline carries no session identity — the guard only
        # binds/degrades lease-mode policies.
        with tempfile.TemporaryDirectory() as tmp:
            run_lease("--restore-baseline", "--root", tmp)
            baseline = read_lease(Path(tmp))
            self.assertNotIn("lease_id", baseline)
            self.assertNotIn("created_at", baseline)

    def test_set_without_allow_means_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_lease("--set", "--skill", "ce-ask", "--root", tmp)
            lease = read_lease(Path(tmp))
            self.assertEqual(lease["allow"], [])

    def test_set_requires_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run_lease("--set", "--root", tmp)
            self.assertEqual(res.returncode, 2)

    def test_restore_baseline_is_deny_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_lease("--set", "--skill", "ce-review", "--root", tmp)
            res = run_lease("--restore-baseline", "--root", tmp)
            self.assertEqual(res.returncode, 0, res.stderr)
            baseline = read_lease(Path(tmp))
            self.assertEqual(baseline["mode"], "deny-only")
            self.assertNotIn("allow", baseline)
            self.assertIn(".git/**", baseline["deny"])

    def test_replacing_a_stale_lease_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_lease("--set", "--skill", "ce-review", "--root", tmp)
            res = run_lease("--set", "--skill", "ce-ask", "--root", tmp)
            self.assertEqual(res.returncode, 0)
            self.assertIn("stale lease", res.stderr)
            self.assertIn("ce-review", res.stderr)

    def test_lease_is_enforced_by_the_hook_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_lease("--set", "--skill", "ce-review",
                      "--allow", "docs/plans/**/code-review.md", "--root", tmp)
            env = os.environ.copy()
            env["CLAUDE_PROJECT_DIR"] = str(root)
            env.pop("CE_WRITE_SCOPE_POLICY", None)

            def hook(target):
                return subprocess.run(
                    [sys.executable, str(HOOK)],
                    input=json.dumps({
                        "tool_name": "Edit",
                        "cwd": str(root),
                        "tool_input": {"file_path": target},
                    }),
                    capture_output=True, text=True, env=env, timeout=60,
                )

            denied = hook("src/app.py")
            out = json.loads(denied.stdout)["hookSpecificOutput"]
            self.assertEqual(out["permissionDecision"], "deny")
            self.assertIn("ce-review", out["permissionDecisionReason"])

            allowed = hook("docs/plans/team/specs/f1/code-review.md")
            self.assertEqual(allowed.stdout.strip(), "")

            run_lease("--restore-baseline", "--root", tmp)
            after = hook("src/app.py")
            self.assertEqual(after.stdout.strip(), "", "baseline must not block source writes")


if __name__ == "__main__":
    unittest.main()
