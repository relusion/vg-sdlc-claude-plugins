"""Static checks for auto-build's plugin-agent delegation contract."""

import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "plugins/core-engineering/skills/ce-auto-build/SKILL.md"
REPORT_TEMPLATE = REPO / "plugins/core-engineering/skills/ce-auto-build/run-report-template.md"


class AutoBuildAgents(unittest.TestCase):
    def test_skill_prefers_plugin_shipped_agents(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("spec-author", text)
        self.assertIn("spec-impl", text)
        self.assertIn("generic Task workers", text)

    def test_skill_defines_named_agent_selection_and_fallbacks(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("### Named Agent Selection", text)
        self.assertIn("spec-author", text)
        self.assertIn("spec-impl", text)
        self.assertIn("spawning orchestrator with generic Task workers", text)
        self.assertIn("in-context (spec/implement isolation relaxed)", text)

    def test_run_report_records_worker_selection(self):
        text = REPORT_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("Worker selection:", text)
        self.assertIn("spec-author", text)
        self.assertIn("spec-impl", text)


if __name__ == "__main__":
    unittest.main()
