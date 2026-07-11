import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/skills/ce-auto-build/scripts/worktree-preflight.py"


def run_preflight(root: Path, plan: Path):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--root",
            str(root),
            "--plan",
            str(plan),
            "--skip-git",
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )


class WorktreePreflight(unittest.TestCase):
    def test_groups_only_dependency_and_modify_independent_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = root / "plan.json"
            plan.write_text(json.dumps({
                "features": [
                    {"id": "01-a", "ship_order": 1, "depends_on": [], "modify_reach": ["src/a.py"]},
                    {"id": "02-b", "ship_order": 2, "depends_on": [], "modify_reach": ["src/b.py"]},
                    {"id": "03-c", "ship_order": 3, "depends_on": ["01-a"], "modify_reach": ["src/c.py"]},
                    {"id": "04-d", "ship_order": 4, "depends_on": []},
                ]
            }), encoding="utf-8")

            res = run_preflight(root, plan)
            self.assertEqual(res.returncode, 0, res.stderr)
            data = json.loads(res.stdout)
            self.assertEqual(data["parallel_groups"][0], ["01-a", "02-b"])
            self.assertIn(["03-c"], data["parallel_groups"])
            self.assertIn(["04-d"], data["parallel_groups"])
            self.assertIn("04-d lacks MODIFY reach", "\n".join(data["warnings"]))

    def test_missing_modify_reach_stays_sequential(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = root / "plan.json"
            plan.write_text(json.dumps({
                "features": [
                    {"id": "01-a", "ship_order": 1, "depends_on": []},
                    {"id": "02-b", "ship_order": 2, "depends_on": []},
                ]
            }), encoding="utf-8")

            res = run_preflight(root, plan)
            self.assertEqual(res.returncode, 0, res.stderr)
            data = json.loads(res.stdout)
            self.assertEqual(data["parallel_groups"], [["01-a"], ["02-b"]])
            self.assertIn("no safe parallel group found", "\n".join(data["warnings"]))


def make_plan(root: Path, features: list, specs: dict | None = None) -> Path:
    """A plan dir with plan.json and, optionally, per-feature specs/<id>/tasks.json."""
    plan_dir = root / "docs" / "plans" / "demo"
    plan_dir.mkdir(parents=True)
    (plan_dir / "plan.json").write_text(json.dumps({"features": features}),
                                        encoding="utf-8")
    if specs is not None:
        for fid, files in specs.items():
            spec_dir = plan_dir / "specs" / fid
            spec_dir.mkdir(parents=True)
            (spec_dir / "tasks.json").write_text(json.dumps(
                {"feature_id": fid, "tasks": [{"id": "T1", "files": files}]}),
                encoding="utf-8")
    return plan_dir / "plan.json"


BARE = [
    {"id": "01-a", "ship_order": 1, "depends_on": []},
    {"id": "02-b", "ship_order": 2, "depends_on": []},
    {"id": "03-c", "ship_order": 3, "depends_on": ["01-a"]},
]


class ReachFallback(unittest.TestCase):
    """`/ce-plan` writes no reach key, so path-level reach exists only after
    `/ce-spec` has written tasks.json. The fallback makes the capability real
    post-spec WITHOUT inventing a plan-time guess."""

    def preflight(self, root: Path, plan: Path) -> dict:
        res = run_preflight(root, plan)
        self.assertEqual(res.returncode, 0, res.stderr)
        return json.loads(res.stdout)

    def test_reach_derived_from_tasks_json_when_plan_lacks_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = make_plan(root, BARE, {"01-a": ["src/a.py"], "02-b": ["src/b.py"],
                                          "03-c": ["src/c.py"]})
            data = self.preflight(root, plan)
            self.assertEqual(data["parallel_groups"][0], ["01-a", "02-b"])
            self.assertIn(["03-c"], data["parallel_groups"])  # hard dep on 01-a
            self.assertEqual(data["reach_sources"]["01-a"], "tasks.json")

    def test_overlapping_tasks_files_stay_sequential(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = make_plan(root, BARE, {"01-a": ["src/shared.py"],
                                          "02-b": ["src/shared.py"],
                                          "03-c": ["src/c.py"]})
            data = self.preflight(root, plan)
            for group in data["parallel_groups"]:
                self.assertFalse({"01-a", "02-b"} <= set(group),
                                 "features sharing a file must never group")

    def test_plan_reach_key_still_wins_when_present(self):
        """An explicit plan.json key overrides tasks.json — here it declares a
        collision the tasks.json files[] would have missed."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            features = [dict(f) for f in BARE]
            features[0]["modify_reach"] = ["src/collide.py"]
            features[1]["modify_reach"] = ["src/collide.py"]
            plan = make_plan(root, features, {"01-a": ["src/a.py"], "02-b": ["src/b.py"]})
            data = self.preflight(root, plan)
            self.assertEqual(data["reach_sources"]["01-a"], "plan.json")
            for group in data["parallel_groups"]:
                self.assertFalse({"01-a", "02-b"} <= set(group))

    def test_no_tasks_json_stays_sequential(self):
        """auto-build's call sites run BEFORE specs exist (the spec agent runs
        inside the group). They must keep returning singletons — this fallback
        does not silently enable parallelism there."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = make_plan(root, BARE, specs=None)
            data = self.preflight(root, plan)
            self.assertEqual(data["parallel_groups"], [["01-a"], ["02-b"], ["03-c"]])
            self.assertEqual(set(data["reach_sources"].values()), {"none"})
            self.assertIn("lacks MODIFY reach", "\n".join(data["warnings"]))

    def test_tasks_json_present_but_no_files_stays_conservative(self):
        """An empty files[] must read as 'unknown', never as 'touches nothing' —
        the latter would make every feature look independent."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = make_plan(root, BARE, {"01-a": [], "02-b": []})
            data = self.preflight(root, plan)
            self.assertEqual(data["parallel_groups"], [["01-a"], ["02-b"], ["03-c"]])
            self.assertEqual(data["reach_sources"]["01-a"], "none")

    def test_unreadable_tasks_json_stays_conservative(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = make_plan(root, BARE, {"01-a": ["src/a.py"], "02-b": ["src/b.py"]})
            (plan.parent / "specs" / "01-a" / "tasks.json").write_text("{broken",
                                                                       encoding="utf-8")
            data = self.preflight(root, plan)
            self.assertEqual(data["reach_sources"]["01-a"], "none")
            for group in data["parallel_groups"]:
                self.assertFalse({"01-a", "02-b"} <= set(group))

    def test_unsafe_feature_id_is_not_traversed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = make_plan(root, [
                {"id": "../../../etc", "ship_order": 1},
                {"id": "02-b", "ship_order": 2},
            ])
            (plan.parent / "specs").mkdir(parents=True, exist_ok=True)
            data = self.preflight(root, plan)
            self.assertEqual(data["reach_sources"]["../../../etc"], "none")

    def test_honest_limitations_state_the_post_spec_constraint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = self.preflight(root, make_plan(root, BARE))
            joined = "\n".join(data["honest_limitations"])
            self.assertIn("only after", joined)
            self.assertIn("worktree-merge.py", joined)


if __name__ == "__main__":
    unittest.main()
