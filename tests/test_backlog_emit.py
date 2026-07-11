"""Fixture tests for ce-ship-backlog's backlog-emit.py — the four one-way emitters.

Proves that one neutral backlog.json renders to all four formats (ado-md default,
ado-csv, jira-csv, gh-jsonl) and that the parent-linking rule (every Task links to
the single Story) survives in each format's native shape. Also pins the portability
contract exit codes (usage=2, malformed=1) and the optional-Bug path.
"""

import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/skills/ce-ship-backlog/scripts/backlog-emit.py"

FIXTURE = {
    "feature_id": "03-user-profile",
    "spec_path": "docs/plans/acme/specs/03-user-profile/ce-spec.md",
    "spec_revision": 2,
    "generated": "2026-07-05",
    "story": {
        "title": "03-user-profile: Profile management",
        "description": "Let a signed-in user view and edit their profile.",
        "acceptance_criteria": [
            "WHEN a user opens /profile THE SYSTEM SHALL show their name and email.",
            "WHEN a user saves a valid change THE SYSTEM SHALL persist it within 500ms.",
        ],
        "tags": ["03-user-profile", "complexity:M", "risk:medium", "persistence"],
        "from": "docs/plans/acme/specs/03-user-profile/ce-spec.md @ spec_revision 2",
    },
    "tasks": [
        {
            "title": "Add GET /profile endpoint",
            "description": "Return the current user's profile.",
            "tags": ["03-user-profile", "verifies:TC-1"],
            "parent": "US-1",
            "from": "docs/plans/acme/specs/03-user-profile/ce-spec.md @ spec_revision 2",
        },
        {
            "title": "Add profile edit form",
            "description": "Client form bound to PUT /profile.",
            "tags": ["03-user-profile", "verifies:TC-2,TC-3"],
            "parent": "US-1",
            "from": "docs/plans/acme/specs/03-user-profile/ce-spec.md @ spec_revision 2",
        },
    ],
}


def emit(backlog, fmt=None):
    """Run the emitter on a backlog dict; return CompletedProcess (text)."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(backlog, f)
        path = f.name
    argv = [sys.executable, str(SCRIPT), path]
    if fmt is not None:
        argv += ["--format", fmt]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    Path(path).unlink(missing_ok=True)
    return proc


class AllFourFormatsEmit(unittest.TestCase):
    def test_every_format_exits_zero_and_nonempty(self):
        for fmt in (None, "ado-md", "ado-csv", "jira-csv", "gh-jsonl"):
            proc = emit(FIXTURE, fmt)
            label = fmt or "(default)"
            self.assertEqual(proc.returncode, 0, f"{label}: {proc.stderr}")
            self.assertTrue(proc.stdout.strip(), f"{label}: empty output")

    def test_default_is_ado_md(self):
        default = emit(FIXTURE, None).stdout
        explicit = emit(FIXTURE, "ado-md").stdout
        self.assertEqual(default, explicit)
        self.assertTrue(default.startswith("# Backlog — 03-user-profile"))


class AdoMarkdown(unittest.TestCase):
    def setUp(self):
        self.out = emit(FIXTURE, "ado-md").stdout

    def test_story_and_tasks_present(self):
        self.assertIn("## US-1 — User Story", self.out)
        self.assertIn("## T-1 — Task", self.out)
        self.assertIn("## T-2 — Task", self.out)

    def test_ears_copied_verbatim(self):
        for crit in FIXTURE["story"]["acceptance_criteria"]:
            self.assertIn(crit, self.out)

    def test_from_stamp_present(self):
        self.assertIn("@ spec_revision 2", self.out)

    def test_tasks_parent_link_the_story(self):
        # Both the block header and the explicit Parent field name US-1.
        self.assertEqual(self.out.count("*(parent: US-1)*"), 2)
        self.assertEqual(self.out.count("**Parent:** US-1"), 2)


class AdoCsv(unittest.TestCase):
    def setUp(self):
        self.rows = list(csv.reader(io.StringIO(emit(FIXTURE, "ado-csv").stdout)))

    def test_header_columns_exact(self):
        self.assertEqual(
            self.rows[0],
            ["Work Item Type", "Title", "Description", "Acceptance Criteria", "Tags"],
        )

    def test_one_story_then_tasks(self):
        types = [r[0] for r in self.rows[1:]]
        self.assertEqual(types, ["User Story", "Task", "Task"])

    def test_ac_on_story_only(self):
        self.assertTrue(self.rows[1][3])          # story AC non-empty
        self.assertEqual(self.rows[2][3], "")      # task AC empty
        self.assertEqual(self.rows[3][3], "")

    def test_tags_semicolon_joined(self):
        self.assertIn("complexity:M; risk:medium", self.rows[1][4])

    def test_parent_link_by_ordering(self):
        # ADO CSV has no Parent column; the Story row precedes every Task row.
        story_idx = next(i for i, r in enumerate(self.rows) if r[0] == "User Story")
        task_idxs = [i for i, r in enumerate(self.rows) if r[0] == "Task"]
        self.assertTrue(task_idxs)
        self.assertTrue(all(story_idx < ti for ti in task_idxs))


class JiraCsv(unittest.TestCase):
    def setUp(self):
        self.rows = list(csv.reader(io.StringIO(emit(FIXTURE, "jira-csv").stdout)))
        self.header = self.rows[0]

    def test_header_has_issue_id_and_parent_id(self):
        self.assertIn("Issue Id", self.header)
        self.assertIn("Parent Id", self.header)

    def test_story_then_subtasks(self):
        types = [r[0] for r in self.rows[1:]]
        self.assertEqual(types, ["Story", "Sub-task", "Sub-task"])

    def test_subtasks_parent_id_is_story_issue_id(self):
        iid = self.header.index("Issue Id")
        pid = self.header.index("Parent Id")
        story = next(r for r in self.rows[1:] if r[0] == "Story")
        story_iid = story[iid]
        self.assertTrue(story_iid)
        self.assertEqual(story[pid], "")            # story has no parent
        subs = [r for r in self.rows[1:] if r[0] == "Sub-task"]
        self.assertTrue(subs)
        for r in subs:
            self.assertEqual(r[pid], story_iid)     # every sub-task links up

    def test_labels_space_joined(self):
        labels_col = self.header.index("Labels")
        story = next(r for r in self.rows[1:] if r[0] == "Story")
        self.assertEqual(story[labels_col].split(), FIXTURE["story"]["tags"])


class GhJsonl(unittest.TestCase):
    def setUp(self):
        self.objs = [json.loads(l) for l in emit(FIXTURE, "gh-jsonl").stdout.splitlines() if l.strip()]

    def test_one_object_per_issue(self):
        self.assertEqual(len(self.objs), 3)           # 1 story + 2 tasks

    def test_each_line_is_valid_json_with_required_fields(self):
        for o in self.objs:
            for key in ("id", "type", "title", "body", "labels", "parent"):
                self.assertIn(key, o)

    def test_story_has_no_parent_tasks_point_at_story(self):
        story = next(o for o in self.objs if o["type"] == "Story")
        self.assertIsNone(story["parent"])
        tasks = [o for o in self.objs if o["type"] == "Task"]
        self.assertTrue(tasks)
        for t in tasks:
            self.assertEqual(t["parent"], "US-1")
            self.assertIn("Parent: US-1", t["body"])

    def test_story_body_carries_acceptance_criteria(self):
        story = next(o for o in self.objs if o["type"] == "Story")
        for crit in FIXTURE["story"]["acceptance_criteria"]:
            self.assertIn(crit, story["body"])


class ParentLinkingRuleAcrossFormats(unittest.TestCase):
    """The hierarchy rule — every Task links to the single Story — in each format."""

    def test_ado_md_labels_every_task_parent(self):
        out = emit(FIXTURE, "ado-md").stdout
        self.assertEqual(out.count("**Parent:** US-1"), len(FIXTURE["tasks"]))

    def test_jira_every_subtask_parents_to_story(self):
        rows = list(csv.reader(io.StringIO(emit(FIXTURE, "jira-csv").stdout)))
        header = rows[0]
        pid = header.index("Parent Id")
        iid = header.index("Issue Id")
        story_iid = next(r[iid] for r in rows[1:] if r[0] == "Story")
        subs = [r for r in rows[1:] if r[0] == "Sub-task"]
        self.assertEqual(len(subs), len(FIXTURE["tasks"]))
        self.assertTrue(all(r[pid] == story_iid for r in subs))

    def test_gh_every_task_object_parents_to_story(self):
        objs = [json.loads(l) for l in emit(FIXTURE, "gh-jsonl").stdout.splitlines() if l.strip()]
        tasks = [o for o in objs if o["type"] == "Task"]
        self.assertEqual(len(tasks), len(FIXTURE["tasks"]))
        self.assertTrue(all(t["parent"] == "US-1" for t in tasks))

    def test_ado_csv_story_precedes_all_tasks(self):
        rows = list(csv.reader(io.StringIO(emit(FIXTURE, "ado-csv").stdout)))
        story_idx = next(i for i, r in enumerate(rows) if r[0] == "User Story")
        task_idxs = [i for i, r in enumerate(rows) if r[0] == "Task"]
        self.assertEqual(len(task_idxs), len(FIXTURE["tasks"]))
        self.assertTrue(all(story_idx < ti for ti in task_idxs))


class OptionalBug(unittest.TestCase):
    def _with_bug(self):
        b = json.loads(json.dumps(FIXTURE))
        b["bugs"] = [{
            "title": "Fix avatar upload regression",
            "description": "Uploads over 2MB silently fail.",
            "tags": ["03-user-profile", "regression"],
            "parent": "US-1",
            "from": FIXTURE["story"]["from"],
        }]
        return b

    def test_bug_appears_in_each_format(self):
        b = self._with_bug()
        self.assertIn("## B-1 — Bug", emit(b, "ado-md").stdout)
        self.assertIn("Bug", emit(b, "ado-csv").stdout)
        self.assertIn("Bug", emit(b, "jira-csv").stdout)
        objs = [json.loads(l) for l in emit(b, "gh-jsonl").stdout.splitlines() if l.strip()]
        self.assertTrue(any(o["type"] == "Bug" for o in objs))


class ErrorContract(unittest.TestCase):
    def test_no_args_is_usage_error(self):
        proc = subprocess.run([sys.executable, str(SCRIPT)],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 2)

    def test_missing_file_exits_one(self):
        proc = subprocess.run([sys.executable, str(SCRIPT), "/no/such/backlog.json"],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 1)

    def test_bad_format_is_usage_error(self):
        proc = emit(FIXTURE, "trello")
        self.assertEqual(proc.returncode, 2)

    def test_malformed_backlog_exits_one(self):
        proc = emit({"story": {}}, "ado-md")   # story with no title
        self.assertEqual(proc.returncode, 1)


if __name__ == "__main__":
    unittest.main()
