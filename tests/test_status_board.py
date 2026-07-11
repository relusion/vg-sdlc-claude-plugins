"""Fixture tests for auto-build's status-board.py — the STATUS.md projection.

Asserts the disk-derived status ladder, the parked/failed state overlay, the
generated-file header, and the 0/1/2 exit-code contract (1 = invalid plan dir,
2 = never impersonated by an unexpected crash).
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/skills/ce-auto-build/scripts/status-board.py"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, timeout=30,
    )


def make_plan(root: Path, features):
    plan = root / "plan"
    plan.mkdir(parents=True)
    (plan / "plan.json").write_text(json.dumps({
        "features": [
            {"id": fid, "title": title, "ship_order": i + 1}
            for i, (fid, title) in enumerate(features)
        ]
    }))
    return plan


def add_feature_state(plan: Path, fid: str, *, spec=False, tasks=None,
                      verified=False, review=None):
    d = plan / "specs" / fid
    d.mkdir(parents=True, exist_ok=True)
    if spec:
        (d / "spec.md").write_text("# spec\n")
    if tasks is not None:
        (d / "tasks.json").write_text(json.dumps(
            {"feature_id": fid,
             "tasks": [{"id": f"T{i}", "status": s} for i, s in enumerate(tasks)]}))
    if verified:
        (d / "verification.md").write_text("# verified\n")
    if review is not None:
        (d / "review-summary.json").write_text(json.dumps(review))


class StatusLadder(unittest.TestCase):
    def test_full_ladder_and_overlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp), [
                ("01-a", "Queued"), ("02-b", "Specced"), ("03-c", "Implementing"),
                ("04-d", "Implemented"), ("05-e", "Reviewed"),
                ("06-f", "Blocked"), ("07-g", "Parked"),
            ])
            add_feature_state(plan, "02-b", spec=True)
            add_feature_state(plan, "03-c", spec=True, tasks=["done", "todo"])
            add_feature_state(plan, "04-d", spec=True, tasks=["done"], verified=True)
            add_feature_state(plan, "05-e", spec=True, tasks=["done"], verified=True,
                              review={"blocking_high": 0,
                                      "by_severity": {"high": {"confirmed": 0,
                                                               "suspected": 1}}})
            add_feature_state(plan, "06-f", spec=True, tasks=["done"], verified=True,
                              review={"blocking_high": 2,
                                      "by_severity": {"high": {"confirmed": 2,
                                                               "suspected": 0}}})
            add_feature_state(plan, "07-g", spec=True)
            # Canonical run-state location is ce-auto-build/ (SKILL.md path).
            (plan / "ce-auto-build").mkdir()
            (plan / "ce-auto-build" / "2026-06-11-state.json").write_text(
                json.dumps({"features": {"07-g": {"status": "parked"}}}))

            res = run(str(plan))
            self.assertEqual(res.returncode, 0, res.stderr)
            out = res.stdout
            for fid, status in [("01-a", "queued"), ("02-b", "specced"),
                                ("03-c", "implementing"), ("04-d", "implemented"),
                                ("05-e", "reviewed"), ("06-f", "gate-blocked"),
                                ("07-g", "parked")]:
                row = next(line for line in out.splitlines() if f"`{fid}`" in line)
                self.assertIn(f"**{status}**", row, f"{fid}: {row}")
            self.assertIn("0c/1s", out)          # reviewed high counts rendered
            self.assertIn("per state.json", out)  # overlay labeled, never silent

    def test_all_tasks_done_without_verification_is_still_implementing(self):
        # The verification-artifact gate's rule: implemented = all-done AND
        # verification.md. The board must not call it implemented early.
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp), [("01-a", "A")])
            add_feature_state(plan, "01-a", spec=True, tasks=["done", "done"])
            res = run(str(plan))
            self.assertEqual(res.returncode, 0)
            self.assertIn("**implementing**", res.stdout)

    def test_write_creates_generated_board(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp), [("01-a", "A")])
            res = run(str(plan), "--write")
            self.assertEqual(res.returncode, 0, res.stderr)
            board = (plan / "STATUS.md").read_text()
            self.assertIn("GENERATED", board)
            self.assertIn("DO NOT EDIT", board)
            self.assertIn("`01-a`", board)


class Degradation(unittest.TestCase):
    """Fail-safe, loud-degradation behaviors the adversarial review demanded."""

    def test_path_traversal_id_is_rejected_not_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # An artifact one level ABOVE the plan dir the traversal would hit.
            (root / "evil").mkdir()
            (root / "evil" / "spec.md").write_text("# outside\n")
            plan = root / "plan"
            plan.mkdir()
            (plan / "plan.json").write_text(json.dumps(
                {"features": [{"id": "../../evil", "title": "Escape", "ship_order": 1}]}))
            res = run(str(plan))
            self.assertEqual(res.returncode, 0, res.stderr)
            row = next(l for l in res.stdout.splitlines() if "Escape" in l)
            self.assertIn("**invalid-id**", row)
            self.assertNotIn("**reviewed**", row)  # never sourced from outside

    def test_string_blocking_high_is_not_fail_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp), [("01-a", "A")])
            add_feature_state(plan, "01-a", spec=True, tasks=["done"], verified=True,
                              review={"blocking_high": "2",
                                      "by_severity": {"high": {"confirmed": 2,
                                                               "suspected": 0}}})
            res = run(str(plan))
            self.assertEqual(res.returncode, 0)
            row = next(l for l in res.stdout.splitlines() if "`01-a`" in l)
            self.assertNotIn("**reviewed**", row)  # must NOT show the all-clear
            self.assertIn("gate-blocked", row)

    def test_corrupt_review_summary_is_flagged_not_swallowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp), [("01-a", "A")])
            add_feature_state(plan, "01-a", spec=True, tasks=["done"], verified=True)
            (plan / "specs" / "01-a" / "review-summary.json").write_bytes(b"\xff\xfe bad")
            res = run(str(plan))
            self.assertEqual(res.returncode, 0)
            self.assertIn("unreadable", res.stdout)

    def test_heterogeneous_ship_order_does_not_abort_board(self):
        # best-effort guarantee: a string ship_order among ints must not kill it.
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "p"
            plan.mkdir()
            (plan / "plan.json").write_text(json.dumps({"features": [
                {"id": "01-a", "title": "A", "ship_order": 1},
                {"id": "02-b", "title": "B", "ship_order": "2"},
                {"id": "03-c", "title": "C", "ship_order": None},
            ]}))
            res = run(str(plan))
            self.assertEqual(res.returncode, 0, res.stderr)
            for fid in ("01-a", "02-b", "03-c"):
                self.assertIn(f"`{fid}`", res.stdout)

    def test_state_overlay_newest_by_mtime(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp), [("01-a", "A")])
            add_feature_state(plan, "01-a", spec=True, tasks=["done"], verified=True,
                              review={"blocking_high": 0})
            ab = plan / "ce-auto-build"          # canonical location
            ab.mkdir()
            older = ab / "2026-06-01-state.json"
            newer = ab / "2026-06-02-state.json"
            older.write_text(json.dumps({"features": {"01-a": "failed"}}))
            newer.write_text(json.dumps({"features": {"01-a": "parked"}}))
            # Make the lexically-LATER file the OLDER one by mtime.
            os.utime(newer, (1, 1))
            os.utime(older, (10_000_000, 10_000_000))
            res = run(str(plan))
            self.assertEqual(res.returncode, 0)
            row = next(l for l in res.stdout.splitlines() if "`01-a`" in l)
            self.assertIn("**failed**", row)  # mtime-newest (older-named) wins

    def test_legacy_auto_build_dir_is_read_as_back_compat(self):
        # An old run wrote to auto-build/ (pre-run-state.py). With no canonical
        # ce-auto-build/ dir, the board must still overlay its parked/failed.
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp), [("01-a", "A")])
            add_feature_state(plan, "01-a", spec=True)
            (plan / "auto-build").mkdir()
            (plan / "auto-build" / "2026-06-11-state.json").write_text(
                json.dumps({"features": {"01-a": {"status": "parked"}}}))
            res = run(str(plan))
            self.assertEqual(res.returncode, 0, res.stderr)
            row = next(l for l in res.stdout.splitlines() if "`01-a`" in l)
            self.assertIn("**parked**", row)
            self.assertIn("per state.json", row)

    def test_canonical_dir_wins_over_legacy_when_both_present(self):
        # ce-auto-build/ is canonical: when both dirs exist, the legacy dir is
        # ignored entirely (not merged), so a stale legacy state cannot override.
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp), [("01-a", "A")])
            add_feature_state(plan, "01-a", spec=True)
            (plan / "auto-build").mkdir()
            (plan / "auto-build" / "2026-06-11-state.json").write_text(
                json.dumps({"features": {"01-a": {"status": "failed"}}}))
            (plan / "ce-auto-build").mkdir()
            (plan / "ce-auto-build" / "2026-06-12-state.json").write_text(
                json.dumps({"features": {"01-a": {"status": "parked"}}}))
            res = run(str(plan))
            self.assertEqual(res.returncode, 0, res.stderr)
            row = next(l for l in res.stdout.splitlines() if "`01-a`" in l)
            self.assertIn("**parked**", row)      # canonical wins
            self.assertNotIn("**failed**", row)


class ExitCodes(unittest.TestCase):
    def test_missing_plan_json_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run(tmp)
            self.assertEqual(res.returncode, 1)
            self.assertIn("missing or malformed", res.stderr)

    def test_malformed_plan_json_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "plan.json").write_text("{not json")
            res = run(tmp)
            self.assertEqual(res.returncode, 1)

    def test_non_dict_plan_json_exits_1_not_2(self):
        # A top-level list/string is a malformed plan.json -> deliberate 1,
        # never a crash to could-not-run (2).
        for body in ("[1,2,3]", '"hello"', "42"):
            with tempfile.TemporaryDirectory() as tmp:
                Path(tmp, "plan.json").write_text(body)
                res = run(tmp)
                self.assertEqual(res.returncode, 1, f"{body}: {res.stderr}")
                self.assertNotIn("Traceback", res.stderr)

    def test_non_utf8_plan_json_exits_1_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "plan.json").write_bytes(b"\xff\xfe\x00broken")
            res = run(tmp)
            self.assertEqual(res.returncode, 1)
            self.assertNotIn("Traceback", res.stderr)


if __name__ == "__main__":
    unittest.main()
