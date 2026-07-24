"""Pin documentation readiness before the final release decision."""

import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "plugins/core-engineering/skills/ce-ship-release/SKILL.md"
STAGES = REPO / "plugins/core-engineering/skills/ce-ship-release/stages.md"


class ReleaseDocumentationReadiness(unittest.TestCase):
    def test_delivery_order_places_docs_and_audit_before_release(self):
        skill = SKILL.read_text(encoding="utf-8")
        spine = skill[skill.index("plan → architecture?") : skill.index("```", skill.index("plan → architecture?"))]
        self.assertLess(spine.index("{review + verify}"), spine.index("ship-document?"))
        self.assertLess(spine.index("ship-document?"), spine.index("doc-audit?"))
        self.assertLess(
            spine.index("doc-audit?"),
            spine.index("{refresh review + verify when docs/audit changed state}"),
        )
        self.assertLess(
            spine.index("{refresh review + verify when docs/audit changed state}"),
            spine.index("ship-release"),
        )

    def test_docs_are_conditional_but_required_coverage_is_nonwaivable(self):
        skill = SKILL.read_text(encoding="utf-8")
        for status in ("`not-required`", "`required`", "`audit-required`"):
            self.assertIn(status, skill)
        self.assertIn("Missing required documentation", skill)
        self.assertIn("Missing/failed required audit", skill)
        self.assertIn("cannot waive", skill)

    def test_documentation_readiness_precedes_version_and_release_decision(self):
        stages = STAGES.read_text(encoding="utf-8")
        evidence = stages.index("## Stage 0 — Resolve range and hard evidence")
        docs = stages.index("## Stage 1 — Documentation readiness")
        version = stages.index("## Stage 2 — Version")
        decision = stages.index("## Stage 4 — Release Decision")
        self.assertLess(evidence, docs)
        self.assertLess(docs, version)
        self.assertLess(version, decision)
        self.assertIn("docs-manifest.md", stages[docs:version])
        self.assertIn("docs/doc-audits/", stages[docs:version])

    def test_release_requires_current_independent_review_and_verification_gates(self):
        skill = SKILL.read_text(encoding="utf-8")
        stages = STAGES.read_text(encoding="utf-8")
        evidence = stages[
            stages.index("## Stage 0 — Resolve range and hard evidence") :
            stages.index("## Stage 1 — Documentation readiness")
        ]
        for command in (
            "scripts/architecture-selection-lint.py",
            "scripts/plan-lint.py",
            "scripts/task-evidence.py",
            "scripts/review-gate.py",
            "scripts/verification-gate.py",
        ):
            self.assertIn(command, evidence)
        self.assertLess(
            evidence.index("scripts/architecture-selection-lint.py"),
            evidence.index("scripts/task-evidence.py"),
        )
        self.assertLess(
            evidence.index("scripts/plan-lint.py"),
            evidence.index("scripts/task-evidence.py"),
        )
        self.assertNotIn("--require-current-schema", evidence)
        self.assertNotIn("--require-architecture-direction", evidence)
        self.assertIn("--evaluated-commit <full-head-sha>", evidence)
        self.assertIn("--require-blocking-route", evidence)
        self.assertIn("--feature <id-1> --feature <id-2>", evidence)
        self.assertIn("Every exit 1/2", evidence)
        self.assertIn("cannot replace a gate", evidence)
        self.assertIn(
            "cannot waive failed/stale task, review, or verification gates",
            skill,
        )

    def test_normal_run_has_one_material_release_gate(self):
        skill = SKILL.read_text(encoding="utf-8")
        self.assertIn("normal run has one material gate", skill)
        self.assertIn("Gate N of M — Release Decision", skill)
        self.assertNotIn("Stage 5 (material)", skill)

    def test_documentation_changes_restart_freshness_from_candidate_head(self):
        skill = SKILL.read_text(encoding="utf-8")
        stages = STAGES.read_text(encoding="utf-8")
        normalized_skill = " ".join(skill.split())
        self.assertIn(
            "human incorporates those changes into the candidate HEAD",
            normalized_skill,
        )
        self.assertIn(
            "reruns both review and verification, and",
            normalized_skill,
        )
        self.assertIn(
            "rerun both `/core-engineering:ce-review` and "
            "`/core-engineering:ce-verify`",
            stages,
        )
        self.assertIn("restart at Stage 0", stages)
        self.assertIn("Do not reuse a pre-documentation receipt", stages)


if __name__ == "__main__":
    unittest.main()
