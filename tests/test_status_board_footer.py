"""Fixture tests for status-board.py's returning-user behaviors.

Covers the two serve-the-returning-user features: the degraded (no plan.json)
board — a reduced, disk-derived projection over specs/<id>/ dirs that exits 0
instead of hard-failing on light plans — and the `Next:` footer every board
(normal and degraded) ends with. Both stay projections: the footer is a
suggestion, never a gate, and the hard-fail (exit 1) survives only when
neither plan.json nor specs/ nor feature-plan.md exists.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/skills/ce-auto-build/scripts/status-board.py"

FOOTER_SUFFIX = "  (suggestion — a projection, never a gate)"


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
        (d / "ce-spec.md").write_text("# spec\n")
    if tasks is not None:
        (d / "tasks.json").write_text(json.dumps(
            {"feature_id": fid,
             "tasks": [{"id": f"T{i}", "status": s} for i, s in enumerate(tasks)]}))
    if verified:
        (d / "verification.md").write_text("# verified\n")
    if review is not None:
        (d / "review-summary.json").write_text(json.dumps(review))


def last_line(out: str) -> str:
    return out.strip().splitlines()[-1]


class DegradedBoard(unittest.TestCase):
    """No plan.json + specs/ present → reduced board, exit 0, labeled loudly."""

    def test_specs_only_dir_renders_labeled_board_with_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "plan"
            plan.mkdir()
            # implemented: spec + all tasks done + verification.md
            add_feature_state(plan, "01-a", spec=True, tasks=["done"], verified=True)
            # specced: spec only, no task progress
            add_feature_state(plan, "02-b", spec=True)
            # in-progress: spec + partial tasks
            add_feature_state(plan, "03-c", spec=True, tasks=["done", "todo"])
            res = run(str(plan))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("degraded (no plan.json", res.stdout)
            for fid, status in [("01-a", "implemented"), ("02-b", "specced"),
                                ("03-c", "in-progress")]:
                row = next(l for l in res.stdout.splitlines() if f"`{fid}`" in l)
                self.assertIn(f"**{status}**", row, f"{fid}: {row}")

    def test_legacy_spec_md_counts_as_specced_when_degraded(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "plan"
            (plan / "specs" / "01-a").mkdir(parents=True)
            (plan / "specs" / "01-a" / "spec.md").write_text("# spec\n")
            res = run(str(plan))
            self.assertEqual(res.returncode, 0, res.stderr)
            row = next(l for l in res.stdout.splitlines() if "`01-a`" in l)
            self.assertIn("**specced**", row, row)

    def test_feature_plan_md_only_still_degrades_not_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "plan"
            plan.mkdir()
            (plan / "feature-plan.md").write_text("# plan\n")
            res = run(str(plan))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("degraded (no plan.json", res.stdout)

    def test_malformed_tasks_json_degrades_one_row_never_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "plan"
            plan.mkdir()
            add_feature_state(plan, "01-a", spec=True)
            (plan / "specs" / "01-a" / "tasks.json").write_text("{not json")
            add_feature_state(plan, "02-b", spec=True)
            res = run(str(plan))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertNotIn("Traceback", res.stderr)
            row = next(l for l in res.stdout.splitlines() if "`01-a`" in l)
            self.assertIn("tasks.json unreadable", row)   # visible marker
            self.assertIn("`02-b`", res.stdout)           # board still renders

    def test_neither_plan_json_nor_specs_nor_feature_plan_hard_fails(self):
        # Regression: an empty dir is still an invalid plan dir — exit 1.
        with tempfile.TemporaryDirectory() as tmp:
            res = run(tmp)
            self.assertEqual(res.returncode, 1)
            self.assertIn("missing or malformed", res.stderr)


class NextFooter(unittest.TestCase):
    """Every board ends with exactly one Next: line — a suggestion, not a gate."""

    def test_first_unspecced_feature_suggests_ce_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp), [("01-a", "A"), ("02-b", "B")])
            res = run(str(plan))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertEqual(last_line(res.stdout),
                             f"Next: /core-engineering:ce-spec 01-a{FOOTER_SUFFIX}")

    def test_implemented_then_specced_suggests_implement_second(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp), [("01-a", "A"), ("02-b", "B")])
            add_feature_state(plan, "01-a", spec=True, tasks=["done"], verified=True)
            add_feature_state(plan, "02-b", spec=True)
            res = run(str(plan))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertEqual(last_line(res.stdout),
                             f"Next: /core-engineering:ce-implement 02-b{FOOTER_SUFFIX}")

    def test_all_implemented_suggests_ce_verify_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp), [("01-a", "A"), ("02-b", "B")])
            for fid in ("01-a", "02-b"):
                add_feature_state(plan, fid, spec=True, tasks=["done"],
                                  verified=True)
            res = run(str(plan))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertEqual(last_line(res.stdout),
                             f"Next: /core-engineering:ce-verify plan{FOOTER_SUFFIX}")

    def test_footer_present_and_actionable_on_degraded_board(self):
        # Listing order when degraded: 01 implemented, 02 specced → implement 02.
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "plan"
            plan.mkdir()
            add_feature_state(plan, "01-a", spec=True, tasks=["done"], verified=True)
            add_feature_state(plan, "02-b", spec=True)
            res = run(str(plan))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("degraded (no plan.json", res.stdout)
            self.assertEqual(last_line(res.stdout),
                             f"Next: /core-engineering:ce-implement 02-b{FOOTER_SUFFIX}")

    def test_footer_walks_ship_order_not_json_order(self):
        # Feature listed first in plan.json but shipping SECOND must not win.
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "plan"
            plan.mkdir()
            (plan / "plan.json").write_text(json.dumps({"features": [
                {"id": "02-b", "title": "B", "ship_order": 2},
                {"id": "01-a", "title": "A", "ship_order": 1},
            ]}))
            res = run(str(plan))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertEqual(last_line(res.stdout),
                             f"Next: /core-engineering:ce-spec 01-a{FOOTER_SUFFIX}")


if __name__ == "__main__":
    unittest.main()
