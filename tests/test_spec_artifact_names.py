"""Canonical-vs-legacy spec artifact filename tests.

`ce-spec.md` is the canonical per-feature spec artifact name (what
ce-spec's write step emits); `spec.md` is accepted as a legacy fallback.
These tests pin that contract across the machine layer that reads the
artifact: spec-lint dir-mode (the auto-build blocking gate), the
status-board projection, retro's audit-export, and gate_runner's
committed-spec-dir discovery — so neither name ever degrades to a
"spec not found" exit 2 or an "unspecced" row again.
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SPEC_LINT = REPO / "plugins/core-engineering/skills/ce-spec/scripts/spec-lint.py"
STATUS_BOARD = REPO / "plugins/core-engineering/skills/ce-auto-build/scripts/status-board.py"
AUDIT_EXPORT = REPO / "plugins/core-engineering/skills/ce-retro/scripts/audit-export.py"
GATE_RUNNER = REPO / "scripts/gate_runner.py"

# A minimal spec/tasks pair that satisfies spec-lint's hard checks H1-H4
# (H5 is N/A without threat ids), so a clean load exits 0.
VALID_SPEC = """# Feature spec

## AC-1 When invoked, the system shall respond [criterion]

### TC-1 responds (proves AC-1)
modality: cli
verification: auto

## Section 6 — Tasks

### T-1 implement the response
"""
VALID_TASKS = json.dumps(
    {"tasks": [{"id": "T-1", "verifies": ["TC-1"], "status": "todo"}]})


def run(script, *args):
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True, text=True, timeout=30,
    )


class SpecLintDirMode(unittest.TestCase):
    """Dir-mode input resolution: prefer ce-spec.md, fall back to spec.md."""

    def _lint_dir(self, spec_name):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / spec_name).write_text(VALID_SPEC)
            (d / "tasks.json").write_text(VALID_TASKS)
            return run(SPEC_LINT, str(d))

    def test_canonical_ce_spec_md_loads(self):
        res = self._lint_dir("ce-spec.md")
        self.assertIn(res.returncode, (0, 1),
                      f"ce-spec.md dir must load, never exit 2: {res.stdout}{res.stderr}")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_legacy_spec_md_still_loads(self):
        res = self._lint_dir("spec.md")
        self.assertIn(res.returncode, (0, 1),
                      f"legacy spec.md dir must load, never exit 2: {res.stdout}{res.stderr}")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_canonical_preferred_when_both_present(self):
        # A valid ce-spec.md beside a garbled legacy spec.md must lint clean —
        # proof the canonical name wins the dir-mode resolution.
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "ce-spec.md").write_text(VALID_SPEC)
            (d / "spec.md").write_text("no test cases in here at all\n")
            (d / "tasks.json").write_text(VALID_TASKS)
            res = run(SPEC_LINT, str(d))
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_neither_name_exits_2_naming_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "tasks.json").write_text(VALID_TASKS)
            res = run(SPEC_LINT, str(tmp))
            self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
            self.assertIn("ce-spec.md", res.stdout + res.stderr)


class StatusBoardSpecName(unittest.TestCase):
    """A feature whose spec is the canonical ce-spec.md is specced, not queued."""

    def _board_for(self, spec_name):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "plan"
            (plan / "specs" / "01-a").mkdir(parents=True)
            (plan / "plan.json").write_text(json.dumps({
                "features": [{"id": "01-a", "title": "A", "ship_order": 1}]}))
            (plan / "specs" / "01-a" / spec_name).write_text("# spec\n")
            res = run(STATUS_BOARD, str(plan))
            self.assertEqual(res.returncode, 0, res.stderr)
            return next(l for l in res.stdout.splitlines() if "`01-a`" in l)

    def test_ce_spec_md_only_is_specced(self):
        row = self._board_for("ce-spec.md")
        self.assertIn("**specced**", row, row)
        self.assertNotIn("**queued**", row, row)

    def test_legacy_spec_md_only_is_still_specced(self):
        row = self._board_for("spec.md")
        self.assertIn("**specced**", row, row)


class AuditExportSpecName(unittest.TestCase):
    def test_ce_spec_md_counts_as_spec_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "plan"
            (plan / "specs" / "01-a").mkdir(parents=True)
            (plan / "plan.json").write_text(json.dumps({
                "features": [{"id": "01-a", "title": "A", "ship_order": 1}]}))
            (plan / "specs" / "01-a" / "ce-spec.md").write_text("# spec\n")
            res = run(AUDIT_EXPORT, str(plan))
            self.assertEqual(res.returncode, 0, res.stderr)
            data = json.loads(res.stdout)
            feats = {f["id"]: f for f in data["features"]}
            self.assertTrue(feats["01-a"]["spec_present"])


class GateRunnerSpecDirDiscovery(unittest.TestCase):
    """committed_spec_dirs finds ce-spec.md dirs (and legacy spec.md dirs)."""

    def test_both_names_discovered_empty_dir_is_not(self):
        spec = importlib.util.spec_from_file_location("gate_runner_under_test",
                                                      GATE_RUNNER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for fid, name in (("01-canon", "ce-spec.md"), ("02-legacy", "spec.md")):
                d = root / "docs/plans/p/specs" / fid
                d.mkdir(parents=True)
                (d / name).write_text("# spec\n")
            (root / "docs/plans/p/specs/03-empty").mkdir(parents=True)
            found = [d.name for d in mod.committed_spec_dirs(root)]
            self.assertEqual(found, ["01-canon", "02-legacy"])


if __name__ == "__main__":
    unittest.main()
