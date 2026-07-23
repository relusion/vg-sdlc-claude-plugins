"""Regression tests for ce-plan's lean, decision-owned workflow contract."""

import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PLAN = REPO / "plugins/core-engineering/skills/ce-plan"
SPEC = REPO / "plugins/core-engineering/skills/ce-spec/SKILL.md"
IMPLEMENT = REPO / "plugins/core-engineering/skills/ce-implement/SKILL.md"


def read(name: str) -> str:
    return (PLAN / name).read_text(encoding="utf-8")


class CePlanHitlContract(unittest.TestCase):
    def test_adaptive_gates_map_to_human_decisions_not_stages(self):
        skill = read("SKILL.md")
        self.assertIn("## Human-in-the-Loop — adaptive", skill)
        self.assertIn("Architecture Direction Selection", skill)
        self.assertIn("Material Exceptions", skill)
        self.assertIn("Final Plan Approval", skill)
        self.assertIn("Do not gate an unambiguous route", skill)
        self.assertIn("deterministic\nPASS", skill)
        self.assertIn("Do not infer authority from participation", skill)

    def test_intake_inspects_first_and_bounds_questions(self):
        stage = read("stage-0-1-understand.md")
        self.assertLess(stage.index("## 1. Inspect before asking"), stage.index("## 1.2 Ask only"))
        self.assertIn("at most four questions per call", stage)
        self.assertIn("at\nmost two question rounds", stage)
        self.assertIn("Only exit 0 authorizes the skip map", stage)
        self.assertIn("Exit 1 or exit 2 authorize **no skips**", stage)
        self.assertIn("Gate N of M — Intent and Scope", stage)

    def test_clean_negative_architecture_screen_is_not_reattested(self):
        stage = read("stage-1a-architecture-direction.md")
        negative = stage[
            stage.index("For `not-required`") : stage.index("## 1A.3")
        ]
        self.assertIn("continue without a gate", negative)
        self.assertIn("Final Plan\nApproval", negative)
        self.assertIn("deterministic\nnegative is evidence", negative)
        self.assertNotIn("Confirm not applicable", stage)

    def test_architecture_workbench_is_decision_ready_and_revisable(self):
        stage = read("stage-1a-architecture-direction.md")
        workbench = stage[
            stage.index("## 1A.5 Run the architecture workbench") :
            stage.index("## 1A.6")
        ]
        for anchor in (
            "comparison summary",
            "every eligible option",
            "every eliminated or uncarried option",
            "reasoning, assumptions",
            "trade-offs",
            "recommendation, confidence",
            "Gate N of M — Architecture Direction Selection",
            "ask a question",
            "request an option revision",
            "change a preference or comparison weight",
            "change a requirement, driver, source, quality scenario, hard constraint, or",
            "decision owner",
            "decision-frame-delta",
            "same gate locator",
        ):
            self.assertIn(anchor, workbench)
        self.assertIn("No question or adjustment counts as approval", workbench)
        self.assertIn("Required architecture cannot be\ndeferred", workbench)
        self.assertIn("Every answered question", workbench)
        self.assertIn("selection.approved_by", read("stage-1a-architecture-direction.md"))
        self.assertIn(
            "evaluation_frame.decision_owner.identity_or_role",
            read("stage-1a-architecture-direction.md"),
        )

    def test_candidate_checks_do_not_add_generic_confirmations(self):
        stages = read("stage-2-3-decompose-score.md") + read("stage-4-7-gates.md")
        self.assertIn("Do not ask for a generic", stages)
        self.assertIn("Do not\nopen a generic Candidate Review gate", stages)
        self.assertIn("Ask only when a\nrepair changes scope", stages)
        self.assertIn("If there are no material exceptions, do not fire this gate", stages)

    def test_specification_route_is_persisted_and_bounded(self):
        decomposition = read("stage-2-3-decompose-score.md")
        template = read("artifact-template.md")
        for text in (decomposition, template):
            self.assertIn("Specification route", text)
            self.assertIn("compact", text)
            self.assertIn("explicit", text)
        self.assertIn("plan.json.features[]", decomposition)
        self.assertIn("Compact is disqualified", decomposition)
        self.assertIn("return to Plan Stage R", decomposition)
        self.assertIn('"specification_route": "explicit"', template)
        self.assertIn("Compact does not\nskip the canonical spec artifacts", decomposition)
        self.assertIn("spec-lint.py", decomposition)

    def test_compact_admission_screen_is_consistent_across_consumers(self):
        texts = (
            read("stage-2-3-decompose-score.md"),
            SPEC.read_text(encoding="utf-8"),
            IMPLEMENT.read_text(encoding="utf-8"),
        )
        anchors = (
            "`final_complexity` is `Complex`",
            "security/privacy obligation or security reviewer trigger",
            "external/public API, CLI, event, schema, or",
            "hard-dependency interface is unresolved",
            "cross-feature flow, shared shape, or interaction",
            "migration, concurrency, failure, compatibility, destructive, or",
            "acceptance-adequacy, or `manual:judgment`",
            "behavior, acceptance, test location, validation",
            "stable built dependency or already selected",
            "Plan Stage R",
        )
        for anchor in anchors:
            for text in texts:
                with self.subTest(anchor=anchor):
                    self.assertIn(anchor, text)

    def test_one_canonical_directory_shape_replaces_minimal_mode(self):
        gates = read("stage-4-7-gates.md")
        write = read("stage-8-9-write.md")
        template = read("artifact-template.md")
        self.assertIn("one canonical plan-directory artifact for every feature count", gates)
        self.assertIn("Use one plan-directory shape even for one feature", write)
        self.assertIn("including a one-feature plan", template)
        corpus = gates + write + template
        self.assertNotIn("single-feature-minimal", corpus)
        self.assertNotIn("Recommended Minimal Output", corpus)

    def test_clean_security_and_protocol_negatives_are_evidence_not_gates(self):
        gates = read("stage-4-7-gates.md")
        write = read("stage-8-9-write.md")
        self.assertIn("A clean negative is not a separate human\n  attestation", gates)
        self.assertIn("Machine PASS results and assessed clean negatives are evidence rows", write)
        self.assertNotIn("Threat-Model Attestation", write)
        self.assertNotIn("Interaction-Contract Attestation", write)

    def test_final_approval_is_single_write_authority_and_lints_are_hard(self):
        write = read("stage-8-9-write.md")
        revision = read("stage-R-revision.md")
        self.assertIn("Gate N of M — Final Plan Approval", write)
        self.assertIn("Approval is explicit and binds the exact validated byte manifest", write)
        selection = write.index("architecture-selection-lint.py")
        plan = write.index("plan-lint.py", selection)
        approval = write.index("## 8.3 Final Plan Approval")
        publication = write.index("## 9. Publish the approved bytes")
        cleanup = write.index("Delete only the exact candidate scratch")
        self.assertLess(selection, plan)
        self.assertLess(plan, approval)
        self.assertLess(approval, publication)
        self.assertLess(plan, cleanup)
        self.assertGreaterEqual(write.count("architecture-selection-lint.py"), 2)
        self.assertGreaterEqual(write.count("plan-lint.py"), 2)
        self.assertIn("post-publication runs are drift checks", write)
        self.assertIn("exit 1", write)
        self.assertIn("exit 2", write)
        self.assertIn("non-waivable", write)
        revision_lint = revision.index("architecture-selection-lint.py")
        revision_approval = revision.index("Gate N of M — Final Plan Revision Approval")
        revision_publish = revision.index("## R5. Publish and revalidate")
        self.assertLess(revision_lint, revision_approval)
        self.assertLess(revision_approval, revision_publish)
        self.assertIn("Only two exit\n0 receipts make the candidate approvable", revision)


if __name__ == "__main__":
    unittest.main()
