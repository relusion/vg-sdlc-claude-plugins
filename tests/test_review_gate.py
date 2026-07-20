"""Behavioral contract tests for the machine-readable review evidence gate."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/skills/ce-review/scripts/review-gate.py"
AUTO_COPY = REPO / "plugins/core-engineering/skills/ce-auto-build/scripts/review-gate.py"
FORK_MANIFEST = REPO / "plugins/core-engineering/fork-manifest.json"


class ReviewGate(unittest.TestCase):
    def run_gate(self, summary: dict | None) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            spec_dir = Path(tmp) / "04-checkout"
            spec_dir.mkdir()
            if summary is not None:
                (spec_dir / "review-summary.json").write_text(
                    json.dumps(summary), encoding="utf-8"
                )
            return subprocess.run(
                [sys.executable, str(SCRIPT), str(spec_dir), "--json"],
                capture_output=True,
                text=True,
                timeout=30,
            )

    def test_clean_summary_passes_and_allows_unrelated_fields(self):
        result = self.run_gate({
            "status": "pass",
            "blocking_high": 0,
            "future_extension": {"compatible": True},
        })
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "pass")

    def test_blocked_summary_returns_finding(self):
        result = self.run_gate({"status": "blocked", "blocking_high": 3})
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        verdict = json.loads(result.stdout)
        self.assertEqual(verdict["status"], "fail")
        self.assertEqual(verdict["blocking_high"], 3)
        self.assertEqual(len(verdict["hard_failures"]), 1)
        self.assertIn("3 unresolved", verdict["hard_failures"][0])

    def test_missing_or_invalid_status_fails_closed(self):
        for status in (None, "unknown", 0, []):
            with self.subTest(status=status):
                summary = {"blocking_high": 0}
                if status is not None:
                    summary["status"] = status
                result = self.run_gate(summary)
                self.assertEqual(result.returncode, 2)
                verdict = json.loads(result.stdout)
                self.assertEqual(verdict["status"], "error")
                self.assertIn("status must be", verdict["message"])

    def test_status_must_agree_with_blocking_high(self):
        for status, blocking, expected in (
            ("blocked", 0, "expected 'pass'"),
            ("pass", 1, "expected 'blocked'"),
        ):
            with self.subTest(status=status, blocking=blocking):
                result = self.run_gate({
                    "status": status,
                    "blocking_high": blocking,
                })
                self.assertEqual(result.returncode, 2)
                self.assertIn(expected, json.loads(result.stdout)["message"])

    def test_blocking_high_must_be_a_nonnegative_integer(self):
        for blocking in (-1, True, "1", None):
            with self.subTest(blocking=blocking):
                result = self.run_gate({
                    "status": "pass",
                    "blocking_high": blocking,
                })
                self.assertEqual(result.returncode, 2)
                verdict = json.loads(result.stdout)
                self.assertEqual(verdict["status"], "error")
                self.assertIn("non-negative integer", verdict["message"])

    def test_missing_file_stays_a_could_not_run_error(self):
        result = self.run_gate(None)
        self.assertEqual(result.returncode, 2)
        self.assertIn("missing", json.loads(result.stdout)["message"])


class ReviewGateFork(unittest.TestCase):
    def test_auto_build_copy_is_registered_and_identical(self):
        manifest = json.loads(FORK_MANIFEST.read_text(encoding="utf-8"))
        entry = next(
            item
            for item in manifest["forks"]
            if item["canonical"].endswith("ce-review/scripts/review-gate.py")
        )
        self.assertIn(
            "plugins/core-engineering/skills/ce-auto-build/scripts/review-gate.py",
            entry["copies"],
        )
        self.assertEqual(SCRIPT.read_bytes(), AUTO_COPY.read_bytes())


if __name__ == "__main__":
    unittest.main()
