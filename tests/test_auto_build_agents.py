"""Static checks for auto-build's bounded sequential product contract."""

import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO / "plugins/core-engineering/skills/ce-auto-build"
SKILL = SKILL_DIR / "SKILL.md"
PIPELINE = SKILL_DIR / "stage-1-2-pipeline.md"
REPORT_TEMPLATE = SKILL_DIR / "run-report-template.md"


class AutoBuildMvp(unittest.TestCase):
    def test_skill_prefers_plugin_agents_with_bounded_generic_fallback(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("spec-author", text)
        self.assertIn("spec-impl", text)
        self.assertIn("fresh generic Task", text)
        self.assertIn("Do not collapse the work into the orchestrator context", text)

    def test_pipeline_is_fixed_sequential_and_keeps_all_core_stages(self):
        text = PIPELINE.read_text(encoding="utf-8")
        self.assertIn("exactly one feature at a time", text)
        for heading in ("### 1. Specify", "### 2. Implement and verify",
                        "### 3. Review", "## Integration verification"):
            self.assertIn(heading, text)
        self.assertIn("queued → specced → implementing → verifying → reviewed → done",
                      text)

    def test_cumulative_gates_preserve_uncommitted_sequential_work(self):
        text = PIPELINE.read_text(encoding="utf-8")
        self.assertIn("cumulative approved file union", text)
        self.assertIn("cumulative-verified-dependency-names", text)
        self.assertIn("Retain this feature's", text)
        self.assertIn("rerun `test-guard --verify-passes`", text)

    def test_nonzero_deterministic_gate_cannot_be_reinterpreted(self):
        text = PIPELINE.read_text(encoding="utf-8")
        self.assertIn("A non-zero deterministic gate is authoritative", text)
        self.assertIn("Never replace it with a manual Git", text)

    def test_review_uses_shared_machine_schema_and_gate(self):
        text = PIPELINE.read_text(encoding="utf-8")
        self.assertIn("../ce-review/artifact-template.md", text)
        self.assertIn('${CLAUDE_SKILL_DIR}/scripts/review-gate.py', text)
        self.assertNotIn("../ce-review/scripts/review-gate.py", text)
        self.assertIn("status` / `blocking_high` schema", text)

    def test_review_retry_returns_state_to_implementing(self):
        text = PIPELINE.read_text(encoding="utf-8")
        self.assertIn("run `run-state.py advance <id> implementing`", text)

    def test_removed_advanced_components_are_not_shipped(self):
        for rel in (
            "gate-diagnose.md",
            "gate-enrich-parks.md",
            "gate-worktree.md",
            "scripts/gate_runner.py",
            "scripts/task-evidence.py",
            "scripts/worktree-merge.py",
            "scripts/worktree-preflight.py",
        ):
            self.assertFalse((SKILL_DIR / rel).exists(), rel)

    def test_run_report_records_bounds_workers_and_human_disposition(self):
        text = REPORT_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("Worker selection:", text)
        self.assertIn("Budget:", text)
        self.assertIn("End-Review Record", text)
        self.assertIn("No branch, commit, push, PR, merge, deployment", text)


if __name__ == "__main__":
    unittest.main()
