"""Product contract for the lean plan/architecture convergence workflow."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PLAN = REPO / "plugins/core-engineering/skills/ce-plan"
ARCH = REPO / "plugins/core-engineering/skills/ce-architecture"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def between(text: str, start: str, end: str) -> str:
    return text[text.index(start) : text.index(end, text.index(start))]


def decision_rows(text: str) -> list[str]:
    return re.findall(r"^\| \*\*.*$", text, flags=re.MULTILINE)


class ArchitectureConvergenceWorkflow(unittest.TestCase):
    def test_architecture_orchestrator_is_lean_and_dispatches_three_modes(self):
        skill = read(ARCH / "SKILL.md")

        self.assertLessEqual(len(skill.splitlines()), 220)
        for marker in (
            "`explore:<draft-slug>`",
            "`shape:<draft-slug>`",
            "Baseline",
            "${CLAUDE_SKILL_DIR}/exploration-mode.md",
            "${CLAUDE_SKILL_DIR}/shaping-mode.md",
            "${CLAUDE_SKILL_DIR}/stage-0-2-evidence-model.md",
            "${CLAUDE_SKILL_DIR}/stage-3-5-review-write.md",
        ):
            self.assertIn(marker, skill)
        self.assertIn("sole permitted domain write", skill)
        self.assertIn("do not add a nested scope or consent gate", skill)
        self.assertIn("Final Architecture Approval", skill)

    def test_direction_workbench_precedes_feature_decomposition(self):
        orchestrator = read(PLAN / "SKILL.md")
        intake = read(PLAN / "stage-0-1-understand.md")
        direction = read(PLAN / "stage-1a-architecture-direction.md")
        decomposition = read(PLAN / "stage-2-3-decompose-score.md")

        stage_map = between(orchestrator, "| Stage |", "At write time")
        self.assertLess(stage_map.index("| 1A |"), stage_map.index("| 2–3 |"))
        self.assertIn("stage-1a-architecture-direction.md", intake)
        self.assertIn("Run this stage before feature decomposition", direction)
        self.assertIn("Create no provisional features here", direction)
        self.assertIn(
            "/core-engineering:ce-architecture explore:<slug>", direction
        )
        self.assertIn(
            "validated a fresh selected/deferred architecture binding",
            decomposition,
        )

    def test_planning_owns_a_complete_hash_bound_decision_frame(self):
        direction = read(PLAN / "stage-1a-architecture-direction.md")
        exploration = read(ARCH / "exploration-mode.md")

        for criterion in (
            "requirements-fit",
            "quality-attribute-fit",
            "repository-fit",
            "evolvability",
            "operability",
            "delivery-feasibility",
        ):
            self.assertIn(f"`{criterion}`", direction)
            self.assertIn(f'"id": "{criterion}"', exploration)
        for field in (
            "capability_revision",
            "exploration_attempt",
            "parent_gate_index",
            "parent_gate_total",
            "decision_owner",
            "hard_constraints",
            "quality_attribute_scenarios",
            "sources",
        ):
            self.assertIn(field, direction)
            self.assertIn(field, exploration)
        self.assertIn("canonical `source_input_sha256`", direction)
        self.assertRegex(
            read(ARCH / "stage-0-2-evidence-model.md"),
            r"Every feature\s+count uses this one plan-directory shape",
        )

    def test_workbench_exposes_the_complete_decision_surface(self):
        plan_skill = read(PLAN / "SKILL.md")
        direction = read(PLAN / "stage-1a-architecture-direction.md")
        exploration = read(ARCH / "exploration-mode.md")

        required_concepts = (
            "every option considered",
            "eliminated options",
            "criteria/weights",
            "repository evidence",
            "reasoning",
            "assumptions",
            "unknowns",
            "trade-offs",
            "consequences",
            "recommendation",
            "confidence",
        )
        for concept in required_concepts:
            with self.subTest(concept=concept):
                self.assertIn(concept, plan_skill)

        self.assertIn("all considered directions", exploration)
        self.assertIn("current constraints", exploration)
        self.assertIn("cost-if-wrong", exploration)
        self.assertIn("irreversible_commitments", exploration)
        self.assertIn("sensitivity", exploration)
        self.assertIn("Before any selection it must show", direction)

    def test_workbench_primary_and_revision_dialogs_have_four_choices(self):
        exploration = read(ARCH / "exploration-mode.md")
        primary = between(
            exploration,
            "Ask one direction decision with exactly these four primary choices:",
            "Every follow-up uses the same locator",
        )
        revision = between(
            exploration,
            "### Revise the decision frame or options",
            "For a frame adjustment",
        )

        self.assertEqual(4, len(decision_rows(primary)))
        self.assertEqual(4, len(decision_rows(revision)))
        for choice in (
            "Select a direction",
            "Ask questions / inspect evidence",
            "Revise the decision frame or options",
            "Defer (recommended only), park, or abort",
        ):
            self.assertIn(choice, primary)
        for choice in (
            "Adjust requirements, criteria weights, hard constraints, or decision owner",
            "Change an existing direction",
            "Add a new alternative",
            "Return to workbench",
        ):
            self.assertIn(choice, revision)
        self.assertIn("at most four choices", exploration)

    def test_questions_and_revisions_return_to_the_same_locator(self):
        direction = read(PLAN / "stage-1a-architecture-direction.md")
        exploration = read(ARCH / "exploration-mode.md")
        report = read(ARCH / "architecture-options-template.md")

        locator = "Architecture Direction Selection"
        self.assertIn(locator, direction)
        self.assertIn(locator, exploration)
        self.assertIn(locator, report)
        self.assertIn("same locator", direction)
        self.assertIn("same locator", exploration)
        self.assertIn("decision-frame-delta", direction)
        self.assertIn("decision-frame-delta", exploration)
        for delta_field in (
            "criterion_weights",
            "driver_screen",
            "sources",
            "quality_attribute_scenarios",
            "decision_owner",
        ):
            self.assertIn(delta_field, exploration)
        self.assertIn("increments\n`capability_revision` and `exploration_attempt`", exploration)
        self.assertIn("Option-only changes remain in this mode", exploration)
        self.assertIn("Every answered question creates a new\npersisted workbench revision", exploration)

    def test_report_revisions_preserve_an_audit_chain(self):
        exploration = read(ARCH / "exploration-mode.md")
        report = read(ARCH / "architecture-options-template.md")

        for marker in (
            "workbench_revision",
            "prior report SHA-256",
            "human question/request",
            "Carry forward every audit row",
        ):
            self.assertIn(marker, exploration)
        for marker in (
            "Workbench revision",
            "## Decision Workbench Audit",
            "Human input / question",
            "Prior report SHA-256",
            "frame-change",
            "option-change",
            "alternative-added",
        ):
            self.assertIn(marker, report)
        self.assertIn("Before explicit selection", exploration)
        self.assertIn("final snapshot is immutable", exploration)
        self.assertIn("non-selectable audit revision", exploration)
        self.assertIn("frame-change-requested", exploration)

    def test_comparison_is_written_linted_and_reread_before_choice(self):
        exploration = read(ARCH / "exploration-mode.md")
        skill = read(ARCH / "SKILL.md")

        persist = exploration.index("## Persist the Pre-Approval Comparison")
        lint = exploration.index("architecture-options-lint.py", persist)
        gate = exploration.index("## Architecture Direction Selection Gate")
        prompt = exploration.index("Ask one direction decision", gate)
        self.assertLess(persist, lint)
        self.assertLess(lint, gate)
        self.assertLess(gate, prompt)
        self.assertIn("re-read the entire file", exploration)
        self.assertIn("--repo-root . --json", exploration)
        self.assertIn("Require exit 0", exploration)
        self.assertIn("Do not call `AskUserQuestion` unless", exploration)
        self.assertIn(
            "--allow 'docs/plans/.drafts/<slug>/architecture-options.md'",
            exploration,
        )
        self.assertIn("requires\n  `architecture-options-lint.py`", skill)

    def test_report_template_preserves_visible_comparison_and_hashes(self):
        report = read(ARCH / "architecture-options-template.md")

        for section in (
            "## What Needs Your Decision",
            "## Evaluation Frame",
            "## Hard-Constraint Screen",
            "## Weighted Comparison",
            "## Direction A01 — <title>",
            "## Eliminated, Unresolved, and Uncarried Directions",
            "## Evidence Sources",
            "## Decision Workbench Audit",
            "## Machine-Readable Comparison Projection",
            "## Human Decision",
            "## Integrity",
        ):
            self.assertIn(section, report)
        for binding in (
            "Source input SHA-256",
            "Evidence fingerprint",
            "Option-set SHA-256",
            "Option hash",
            "awaiting-selection",
            "Decision owner / authority",
            "Approved by",
            "score basis",
        ):
            self.assertIn(binding, report)

    def test_terminal_selection_is_human_and_deterministically_bound(self):
        direction = read(PLAN / "stage-1a-architecture-direction.md")
        exploration = read(ARCH / "exploration-mode.md")

        for marker in (
            "selection.decided_by",
            "selection.approved_by",
            "evaluation_frame.decision_owner.identity_or_role",
            "non-empty rationale",
            "architecture-options.md",
            "architecture-selection-lint.py",
            "--require-current-schema",
        ):
            self.assertIn(marker, direction)
        self.assertRegex(direction, r"selected option is\s+eligible")
        for marker in (
            "architecture_options_report",
            "option_sha256",
            "option_set_sha256",
            "evidence_fingerprint",
            "source_input_sha256",
            "next_owner",
        ):
            self.assertIn(marker, exploration)
        self.assertIn("decided_by` is `human`", exploration)
        self.assertIn("approved_by` exactly matches", exploration)
        self.assertIn("Delegation is out of scope", exploration)
        self.assertIn("Even a sole viable direction requires an affirmative selection", exploration)

    def test_shape_runs_read_only_without_a_nested_consent_gate(self):
        convergence = read(PLAN / "stage-5a-architecture-convergence.md")
        shaping = read(ARCH / "shaping-mode.md")

        self.assertIn("## 5A.2 Invoke shaping without a consent prompt", convergence)
        self.assertIn("Do not\nask permission merely to run it", convergence)
        self.assertIn("Do not use Write or Edit", shaping)
        self.assertRegex(shaping, r"Do not print a gate\s+locator")
        self.assertEqual(1, shaping.count("AskUserQuestion"))
        self.assertNotIn("Architecture Shaping Scope", shaping)
        self.assertRegex(
            shaping, r"already recorded the human's\s+direction choice and elected this shaping path"
        )

    def test_plan_and_shape_share_a_revision_and_hash_bound_handoff(self):
        convergence = read(PLAN / "stage-5a-architecture-convergence.md")
        shaping = read(ARCH / "shaping-mode.md")

        for marker in (
            "## Architecture Shaping Input",
            "## End Architecture Shaping Input",
            "project_slug:",
            "candidate_revision:",
            "shaping_attempt:",
            "shaping_input_sha256:",
            "parent_gate_index:",
            "parent_gate_total:",
            "architecture_selection_path:",
            "architecture_selection_sha256:",
            "exploration_id:",
            "selected_option_id:",
            "selected_option_sha256:",
            "### Scope and Decision Frame",
            "### Provisional Features",
            "### Journeys and Consumability",
            "### Durable State",
            "### Threat and Interaction Obligations",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, convergence)
                self.assertIn(marker, shaping)
        for result_field in (
            "source_candidate_revision",
            "source_shaping_attempt",
            "source_shaping_input_sha256",
            "source_architecture_selection_sha256",
            "source_selected_option_sha256",
        ):
            self.assertIn(result_field, convergence)
            self.assertIn(result_field, shaping)
        self.assertIn("shaping-input-changed", shaping)
        self.assertIn("selected-direction-changed-during-shaping", shaping)
        self.assertIn("--require-current-schema", shaping)

    def test_shape_has_four_bounded_outcomes_and_preserves_ownership(self):
        convergence = read(PLAN / "stage-5a-architecture-convergence.md")
        shaping = read(ARCH / "shaping-mode.md")
        classification = between(shaping, "## Classify the Result", "## Result Contract")
        statuses = set(re.findall(r"^### `([^`]+)`$", classification, re.MULTILINE))

        self.assertEqual(
            {"converged", "requires-plan-delta", "requires-decision", "blocked"},
            statuses,
        )
        self.assertIn("Never apply the delta", shaping)
        self.assertIn("only `/core-engineering:ce-plan` may apply that delta", convergence)
        self.assertIn("Only the human may approve a material revised cut", convergence)
        self.assertIn("selected-direction-invalid", shaping)
        self.assertIn("return to Stage 6 without a human gate", convergence)

    def test_shape_precedes_reachability_and_uses_one_plan_locator_for_exceptions(self):
        gates = read(PLAN / "stage-4-7-gates.md")
        convergence = read(PLAN / "stage-5a-architecture-convergence.md")

        shape_route = gates.index("stage-5a-architecture-convergence.md")
        reachability = gates.index("## Stage 6 — Reachability")
        self.assertLess(shape_route, reachability)
        self.assertIn("without a\nconsent gate", gates[shape_route:reachability])
        self.assertIn("existing Material\nExceptions locator", convergence)
        self.assertIn("Questions or requested revisions remain at that locator", convergence)

    def test_one_canonical_plan_directory_replaces_feature_count_branches(self):
        plan_gates = read(PLAN / "stage-4-7-gates.md")
        plan_write = read(PLAN / "stage-8-9-write.md")
        architecture_stage = read(ARCH / "stage-0-2-evidence-model.md")

        self.assertIn("one canonical plan-directory artifact for every feature count", plan_gates)
        self.assertIn("Use one plan-directory shape even for one feature", plan_write)
        self.assertIn("Every feature\ncount uses this one plan-directory shape", architecture_stage)
        corpus = "\n".join(
            read(path)
            for root in (PLAN, ARCH)
            for path in root.glob("*.md")
        ).lower()
        for retired in (
            "single-feature-minimal",
            "recommended minimal output",
            "architecture-retire.py",
            "adopted-existing",
            "schema-v1",
            "legacy",
        ):
            self.assertNotIn(retired, corpus)

    def test_final_plan_write_preserves_reviewed_architecture_artifacts(self):
        write = read(PLAN / "stage-8-9-write.md")

        candidate = write.index("## 8. Assemble the exact candidate in scratch")
        selection_lint = write.index("architecture-selection-lint.py", candidate)
        plan_lint = write.index("plan-lint.py", selection_lint)
        approval = write.index("## 8.3 Final Plan Approval")
        publish = write.index("## 9. Publish the approved bytes")
        post_publish_lint = write.index("post-publication runs", publish)
        self.assertLess(candidate, selection_lint)
        self.assertLess(selection_lint, plan_lint)
        self.assertLess(plan_lint, approval)
        self.assertLess(approval, publish)
        self.assertLess(publish, post_publish_lint)
        self.assertIn("binds the exact validated byte manifest", write)
        self.assertIn("Publish those exact bytes", write)
        self.assertIn("copy the exact reviewed draft `architecture-selection.json`", write)
        self.assertIn("copy the exact immutable\n  `architecture-options.md` bytes", write)
        self.assertIn("A hard failure or could-not-run result is non-waivable", write)
        self.assertIn("/core-engineering:ce-architecture <slug>", write)

    def test_baseline_requires_current_plan_then_human_approval(self):
        stage = read(ARCH / "stage-0-2-evidence-model.md")
        review = read(ARCH / "stage-3-5-review-write.md")
        skill = read(ARCH / "SKILL.md")

        transaction = stage.index("### 0.2 Recover publication transaction state")
        floor = stage.index("### 0.3 Run the deterministic plan floor")
        evidence = stage.index("### 0.4 Load the bounded evidence set")
        evidence_resolution = stage.index(
            "### 0.6 Freeze evidence; resolve exceptions only"
        )
        self.assertLess(transaction, floor)
        self.assertLess(floor, evidence)
        self.assertLess(evidence, evidence_resolution)
        self.assertIn("architecture-selection-lint.py", stage[floor:evidence])
        self.assertIn("--require-current-schema", stage[floor:evidence])
        self.assertIn("--require-architecture-direction --json", stage[floor:evidence])
        self.assertIn("Only the current receipt-bound architecture schema", stage)
        self.assertIn("continues to Stage 1", stage[evidence_resolution:])
        self.assertIn("Do not ask the human to re-confirm", stage[evidence_resolution:])

        lint = review.index("### 4.2 Run architecture-lint")
        approval = review.index("### 5.1 Final Architecture Approval")
        publish = review.index("### 5.2 Publish transactionally")
        self.assertLess(lint, approval)
        self.assertLess(approval, publish)
        self.assertIn("No final package is written before approval", skill)

    def test_baseline_package_and_authority_remain_bounded(self):
        skill = read(ARCH / "SKILL.md")

        for output in (
            "solution-architecture.md",
            "views.md",
            "data-and-integrations.md",
            "quality-attributes.md",
            "architecture.json",
        ):
            self.assertIn(output, skill)
        for choice in ("Approve & publish", "Adjust", "Park", "Abort"):
            self.assertIn(choice, skill)
        self.assertIn("The human owns whole-solution direction selection", skill)
        self.assertIn("Never approve security or compliance risk", skill)


if __name__ == "__main__":
    unittest.main()
