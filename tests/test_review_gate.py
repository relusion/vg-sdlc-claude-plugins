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
    def run_gate(
        self, summary: dict | None, *extra: str
    ) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            spec_dir = Path(tmp) / "04-checkout"
            spec_dir.mkdir()
            if summary is not None:
                (spec_dir / "review-summary.json").write_text(
                    json.dumps(summary), encoding="utf-8"
                )
            return subprocess.run(
                [sys.executable, str(SCRIPT), str(spec_dir), "--json", *extra],
                capture_output=True,
                text=True,
                timeout=30,
            )

    def test_clean_summary_passes_and_allows_unrelated_fields(self):
        result = self.run_gate({
            "status": "pass",
            "blocking_high": 0,
            "blocking_route": None,
            "future_extension": {"compatible": True},
        })
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "pass")

    def test_blocked_summary_returns_finding(self):
        result = self.run_gate({
            "status": "blocked", "blocking_high": 3,
            "blocking_route": "implement",
        })
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        verdict = json.loads(result.stdout)
        self.assertEqual(verdict["status"], "fail")
        self.assertEqual(verdict["blocking_high"], 3)
        self.assertEqual(len(verdict["hard_failures"]), 1)
        self.assertIn("3 unresolved", verdict["hard_failures"][0])
        self.assertEqual(verdict["blocking_route"], "implement")

    def test_plan_conflict_route_is_validated_and_returned(self):
        summary = {
            "status": "blocked",
            "blocking_high": 1,
            "blocking_route": "plan-conflict",
            "findings": [{
                "lens": "security",
                "severity": "high",
                "confidence": "confirmed",
                "observation": "plan_conflict: undocumented public boundary",
                "suggested_escalation": "/core-engineering:ce-plan",
            }],
        }
        result = self.run_gate(summary, "--require-blocking-route")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(
            json.loads(result.stdout)["blocking_route"], "plan-conflict"
        )

    def test_automation_rejects_missing_or_discarded_plan_conflict_route(self):
        base = {
            "status": "blocked",
            "blocking_high": 1,
            "findings": [{
                "lens": "security",
                "severity": "high",
                "confidence": "confirmed",
                "observation": "plan_conflict: undocumented public boundary",
                "suggested_escalation": "/core-engineering:ce-plan",
            }],
        }
        cases = {
            "missing": dict(base),
            "null": {**base, "blocking_route": None},
            "implement": {**base, "blocking_route": "implement"},
            "false-pass": {
                **base,
                "status": "pass",
                "blocking_high": 0,
                "blocking_route": None,
            },
        }
        for label, summary in cases.items():
            with self.subTest(case=label):
                result = self.run_gate(summary, "--require-blocking-route")
                self.assertEqual(result.returncode, 2)
                self.assertIn("plan_conflict", json.loads(result.stdout)["message"])

    def test_automation_requires_route_even_without_plan_conflict(self):
        result = self.run_gate(
            {"status": "blocked", "blocking_high": 1},
            "--require-blocking-route",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("blocking_route is required", json.loads(result.stdout)["message"])

    def test_partial_plan_conflict_signal_cannot_fall_back_to_implement(self):
        rows = (
            {
                "lens": "security", "severity": "high", "confidence": "confirmed",
                "observation": "plan_conflict: projection is stale",
                "suggested_escalation": "/core-engineering:ce-implement",
            },
            {
                "lens": "security", "severity": "high", "confidence": "confirmed",
                "observation": "projection is stale",
                "suggested_escalation": "/core-engineering:ce-plan",
            },
        )
        for row in rows:
            with self.subTest(row=row):
                result = self.run_gate({
                    "status": "blocked",
                    "blocking_high": 1,
                    "blocking_route": "implement",
                    "findings": [row],
                }, "--require-blocking-route")
                self.assertEqual(result.returncode, 2)
                self.assertIn("plan_conflict", json.loads(result.stdout)["message"])

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
