"""Tests for scripts/metrics_report.py, the repository-level metrics dashboard."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "metrics_report.py"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


def make_fixture(root: Path) -> None:
    plan = root / "docs" / "plans" / "demo"
    spec = plan / "specs" / "01-core"
    spec.mkdir(parents=True)
    (plan / "plan.json").write_text(json.dumps({
        "status": "implemented",
        "features": [{"id": "01-core", "title": "Core"}],
    }), encoding="utf-8")
    (plan / ".metrics.jsonl").write_text("\n".join([
        json.dumps({"event": "gate", "gate": "pass"}),
        json.dumps({"event": "escalation", "escalation_type": "/core-engineering:ce-plan"}),
        "{not json",
    ]) + "\n", encoding="utf-8")
    (spec / "verification.md").write_text("# verified\n", encoding="utf-8")
    (spec / "review-summary.json").write_text(json.dumps({
        "findings_total": 2,
        "blocking_high": 1,
        "by_severity": {"high": {"confirmed": 1}, "medium": 1},
    }), encoding="utf-8")
    (plan / "ce-auto-build").mkdir()
    (plan / "ce-auto-build" / "2026-06-28-run.md").write_text("# run\n", encoding="utf-8")

    run_dir = root / "evals" / "runs" / "20260628"
    run_dir.mkdir(parents=True)
    (run_dir / "metadata.json").write_text(json.dumps({
        "schema_version": 1,
        "dry_run": True,
        "records": [
            {"id": "EVAL-013", "profile": "benchmark", "status": "planned"},
            {"id": "EVAL-014", "profile": "benchmark", "status": "failed",
             "failure_kind": "budget-exceeded"},
        ],
    }), encoding="utf-8")


class MetricsReport(unittest.TestCase):
    def test_collects_repo_metrics_and_reports_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_fixture(root)
            res = run("--root", str(root), "--json")
            self.assertEqual(res.returncode, 0, res.stderr)
            doc = json.loads(res.stdout)

            self.assertEqual(doc["schema_version"], 1)
            self.assertEqual(doc["plans"]["count"], 1)
            self.assertEqual(doc["plans"]["with_metrics"], 1)
            self.assertEqual(doc["metrics"]["lines_total"], 3)
            self.assertEqual(doc["metrics"]["lines_unparseable"], 1)
            self.assertEqual(doc["metrics"]["lines_invalid_schema"], 0)
            self.assertEqual(doc["metrics"]["event_schema"]["legacy_unversioned"], 2)
            self.assertEqual(doc["metrics"]["field_coverage"]["valid_events"], 2)
            self.assertEqual(doc["metrics"]["gates"]["pass"], 1)
            self.assertEqual(doc["metrics"]["escalations_by_type"]["/core-engineering:ce-plan"], 1)
            self.assertEqual(doc["reviews"]["findings_total"], 2)
            self.assertEqual(doc["reviews"]["blocking_high"], 1)
            self.assertEqual(doc["verifications"]["files"], 1)
            self.assertEqual(doc["auto_build"]["run_reports"], 1)
            self.assertEqual(doc["evals"]["records_total"], 2)
            self.assertEqual(doc["evals"]["by_profile"]["benchmark"], 2)
            self.assertEqual(doc["evals"]["by_failure_kind"]["budget-exceeded"], 1)
            self.assertTrue(any("unparseable metrics" in gap for gap in doc["gaps"]))

    def test_v2_contract_validation_and_runtime_metadata_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_fixture(root)
            metrics = root / "docs" / "plans" / "demo" / ".metrics.jsonl"
            metrics.write_text("\n".join([
                json.dumps({
                    "schema_version": 2,
                    "ts": "2026-07-21",
                    "stage": "verify",
                    "plan": "demo",
                    "feature": "01-core",
                    "event": "run-terminal",
                    "run_id": "20260721-120000Z-a1b2",
                    "outcome": "completed",
                    "duration_ms": 1234,
                    "model": "claude-opus-resolved",
                    "claude_cli_version": "1.2.3",
                    "plugin_version": "0.10.1",
                }),
                json.dumps({
                    "schema_version": 2,
                    "ts": "2026-07-21",
                    "stage": "review",
                    "plan": "demo",
                    "feature": "01-core",
                    "event": "attestation",
                    "run_id": "20260721-120001Z-b2c3",
                    "gate": "finding-triage",
                    "gate_index": "1 of 1",
                    "action": "confirm",
                    "basis_shown": True,
                    "model": None,
                }),
                # Explicit v1 remains readable with its historical permissive shape.
                json.dumps({"schema_version": 1, "event": "gate", "gate": "pass"}),
                # Parseable v2 telemetry is excluded when its schema is invalid.
                json.dumps({
                    "schema_version": 2,
                    "ts": "2026-07-21",
                    "stage": "verify",
                    "plan": "demo",
                    "feature": None,
                    "event": "run-terminal",
                    "outcome": "completed",
                    "duration_ms": -1,
                }),
                json.dumps({"schema_version": 99, "event": "gate", "gate": "fail"}),
            ]) + "\n", encoding="utf-8")

            res = run("--root", str(root), "--json")
            self.assertEqual(res.returncode, 0, res.stderr)
            doc = json.loads(res.stdout)
            summary = doc["metrics"]

            self.assertEqual(summary["event_schema"]["version_1"], 1)
            self.assertEqual(summary["event_schema"]["version_2"], 3)
            self.assertEqual(summary["event_schema"]["unsupported"], 1)
            self.assertEqual(summary["lines_invalid_schema"], 2)
            self.assertEqual(summary["field_coverage"], {
                "valid_events": 3,
                "run_id": 2,
                "terminal_outcome": 1,
                "duration_ms": 1,
                "model": 1,
                "claude_cli_version": 1,
                "plugin_version": 1,
            })
            self.assertEqual(summary["terminal_outcomes"], {"completed": 1})
            self.assertEqual(summary["gates"]["pass"], 1)
            self.assertEqual(summary["gates"]["fail"], 0)
            self.assertTrue(any("duration_ms" in gap for gap in doc["gaps"]))
            self.assertTrue(any("unsupported schema_version" in gap for gap in doc["gaps"]))

    def test_missing_plan_stream_is_a_coverage_gap_not_a_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for slug in ("with-stream", "without-stream"):
                plan = root / "docs" / "plans" / slug
                plan.mkdir(parents=True)
                (plan / "plan.json").write_text(json.dumps({
                    "status": "planned",
                    "features": [],
                }), encoding="utf-8")
            (root / "docs" / "plans" / "with-stream" / ".metrics.jsonl").write_text(
                "", encoding="utf-8")

            res = run("--root", str(root), "--json")
            self.assertEqual(res.returncode, 0, res.stderr)
            doc = json.loads(res.stdout)

            self.assertEqual(doc["plans"]["metrics_coverage"], {
                "plans_expected": 2,
                "plans_with_stream": 1,
                "plans_missing_stream": 1,
            })
            self.assertEqual(doc["plans"]["with_metrics"], 1)
            self.assertEqual(doc["plans"]["without_metrics"], 1)
            missing = next(p for p in doc["plans"]["items"]
                           if p["slug"] == "without-stream")
            self.assertFalse(missing["metrics_present"])
            self.assertEqual(missing["metrics"]["lines_total"], 0)
            self.assertTrue(any(
                "without-stream/.metrics.jsonl: missing metrics stream" in gap
                and "not complete zeros" in gap
                for gap in doc["gaps"]
            ))

    def test_writes_json_and_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_fixture(root)
            out = root / "reports" / "metrics.json"
            html = root / "reports" / "metrics.html"
            res = run("--root", str(root), "--out", str(out), "--html", str(html))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertEqual(res.stdout, "")
            doc = json.loads(out.read_text(encoding="utf-8"))
            page = html.read_text(encoding="utf-8")
            self.assertEqual(doc["plans"]["count"], 1)
            self.assertIn("Core Engineering Metrics", page)
            self.assertIn("demo", page)

    def test_fail_on_gaps_is_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_fixture(root)
            res = run("--root", str(root), "--fail-on-gaps")
            self.assertEqual(res.returncode, 1)
            self.assertIn("unparseable metrics", res.stdout)


def make_dated_fixture(root: Path) -> None:
    """Two plans, each with one June event, one July event, and one undated line."""
    for slug in ("alpha", "beta"):
        plan = root / "docs" / "plans" / slug
        (plan / "specs" / "01-core").mkdir(parents=True)
        (plan / "plan.json").write_text(json.dumps({
            "status": "implemented",
            "features": [{"id": "01-core", "title": "Core"}],
        }), encoding="utf-8")
        (plan / ".metrics.jsonl").write_text("\n".join([
            json.dumps({"ts": "2026-06-11", "event": "gate", "gate": "pass"}),
            json.dumps({"ts": "2026-07-04", "event": "park"}),
            json.dumps({"event": "retry"}),  # undated
        ]) + "\n", encoding="utf-8")


class MetricsReportWindowing(unittest.TestCase):
    """The cross-plan rollup mirrors audit-export's honesty contract: only the
    stream is windowed; review / verification / eval blocks stay as-of-now."""

    def report(self, root, *args):
        res = run("--root", str(root), "--json", *args)
        self.assertEqual(res.returncode, 0, res.stderr)
        return json.loads(res.stdout)

    def test_no_window_is_unmarked(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_dated_fixture(Path(tmp))
            doc = self.report(Path(tmp))
            self.assertNotIn("window", doc)
            self.assertNotIn("windowing", doc)
            self.assertNotIn("windowed", doc["metrics"])
            self.assertEqual(doc["metrics"]["parks"], 2)    # one per plan
            self.assertEqual(doc["metrics"]["retries"], 2)  # the undated ones

    def test_since_windows_stream_only_across_plans(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_dated_fixture(Path(tmp))
            doc = self.report(Path(tmp), "--since", "2026-07-01")
            self.assertTrue(doc["window"]["applied"])
            self.assertTrue(doc["metrics"]["windowed"])
            self.assertEqual(doc["metrics"]["parks"], 2)          # both July parks
            self.assertEqual(doc["metrics"]["gates"]["pass"], 0)  # June excluded
            self.assertEqual(doc["metrics"]["retries"], 0)        # undated excluded
            self.assertEqual(doc["window"]["stream_lines"],
                             {"in_window": 2, "out_of_window": 2, "undated": 2})
            self.assertIn("metrics", doc["windowing"]["windowed_blocks"])
            self.assertIn("reviews", doc["windowing"]["as_of_now_blocks"])
            self.assertTrue(any("missing/unparseable ts" in g for g in doc["gaps"]))

    def test_plan_with_no_in_window_activity_still_appears(self):
        """Windowed zeros are honest; dropping the plan would hide it."""
        with tempfile.TemporaryDirectory() as tmp:
            make_dated_fixture(Path(tmp))
            doc = self.report(Path(tmp), "--since", "2027-01-01")
            self.assertEqual(doc["plans"]["count"], 2)
            self.assertEqual(doc["metrics"]["parks"], 0)

    def test_malformed_and_inverted_window_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_dated_fixture(Path(tmp))
            self.assertEqual(run("--root", tmp, "--json", "--since", "nope").returncode, 2)
            self.assertEqual(run("--root", tmp, "--json", "--since", "2026-08-01",
                                 "--until", "2026-07-01").returncode, 2)


if __name__ == "__main__":
    unittest.main()
