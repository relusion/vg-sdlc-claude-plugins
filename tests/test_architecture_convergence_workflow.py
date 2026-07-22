"""Pin the plan/architecture convergence boundary and route ordering."""

import re
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PLAN = REPO / "plugins/core-engineering/skills/ce-plan"
ARCH = REPO / "plugins/core-engineering/skills/ce-architecture"


class ArchitectureConvergenceWorkflow(unittest.TestCase):
    def test_applicability_screen_precedes_every_plan_shortcut(self):
        scoring = (PLAN / "stage-2-3-decompose-score.md").read_text(encoding="utf-8")
        gates = (PLAN / "stage-4-7-gates.md").read_text(encoding="utf-8")

        self.assertIn("### 3.9 Architecture Applicability Screen", scoring)
        self.assertIn("before Stage 4 can collapse the work into a minimal plan", scoring)
        self.assertIn("cannot** take the single-feature minimal early exit", gates)
        self.assertIn("**Architecture not required**", gates)
        self.assertIn("Stage 3.9 applicability result is\n   `recommended` or `not-required`", gates)

    def test_required_candidate_routes_through_shape_before_reachability(self):
        gates = (PLAN / "stage-4-7-gates.md").read_text(encoding="utf-8")
        route = gates.index("After `Continue`, route by the recorded applicability result")
        shape = gates.index("stage-5a-architecture-convergence.md", route)
        reachability = gates.index("## Stage 6 — Reachability", route)

        self.assertLess(route, shape)
        self.assertLess(shape, reachability)
        self.assertIn("and run Stage 5A before Stage 6", gates[shape:reachability])

    def test_plan_and_shape_mode_share_a_revision_bound_handoff(self):
        convergence = (PLAN / "stage-5a-architecture-convergence.md").read_text(
            encoding="utf-8"
        )
        shaping = (ARCH / "shaping-mode.md").read_text(encoding="utf-8")

        for marker in (
            "## Architecture Shaping Input",
            "## End Architecture Shaping Input",
            "candidate_revision:",
            "shaping_attempt:",
            "parent_gate_index:",
            "parent_gate_total:",
            "### Provisional Features",
            "### Journeys and Consumability",
            "### Durable State",
            "### Threat and Interaction Obligations",
        ):
            self.assertIn(marker, convergence)
            self.assertIn(marker, shaping)

        self.assertIn("/core-engineering:ce-architecture shape:<slug>", convergence)
        self.assertIn("source_candidate_revision", convergence)
        self.assertIn("source_shaping_attempt", convergence)
        self.assertIn("result is valid only for the echoed `source_candidate_revision`", shaping)
        self.assertIn("`source_shaping_attempt`", shaping)

    def test_evidence_only_retry_has_a_monotonic_attempt_identity(self):
        convergence = (PLAN / "stage-5a-architecture-convergence.md").read_text(
            encoding="utf-8"
        )
        shaping = (ARCH / "shaping-mode.md").read_text(encoding="utf-8")

        self.assertRegex(
            convergence,
            r"evidence-only\s+retry whose candidate\s+revision remains unchanged",
        )
        self.assertIn("`shaping_attempt` is greater than every earlier attempt", shaping)
        self.assertIn("may retain the same candidate revision", shaping)
        self.assertIn("Duplicate/decreasing attempts", shaping)

    def test_shape_mode_is_read_only_and_returns_only_bounded_outcomes(self):
        shaping = (ARCH / "shaping-mode.md").read_text(encoding="utf-8")
        classification = shaping[
            shaping.index("## Classify the Result") : shaping.index("## Result Contract")
        ]
        statuses = set(re.findall(r"^### `([^`]+)`$", classification, re.MULTILINE))

        self.assertEqual(
            statuses,
            {"converged", "requires-plan-delta", "requires-decision", "blocked"},
        )
        self.assertIn("Do not use Write or Edit", shaping)
        self.assertIn("Never apply the delta", shaping)
        self.assertIn("`/core-engineering:ce-plan` owns candidate", shaping)
        self.assertIn("The gate is scope consent, not architecture approval", shaping)

    def test_plan_owns_every_recut_and_human_owns_material_calls(self):
        convergence = (PLAN / "stage-5a-architecture-convergence.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("Only `/core-engineering:ce-plan` may apply that delta", convergence)
        self.assertIn("Only the human may approve the revised cut", convergence)
        self.assertIn("Architecture has proposed them, not applied\nthem", convergence)
        self.assertIn("maximum is three results", convergence)

    def test_convergence_is_rechecked_after_reachability_and_attestations(self):
        gates = (PLAN / "stage-4-7-gates.md").read_text(encoding="utf-8")
        write = (PLAN / "stage-8-9-write.md").read_text(encoding="utf-8")

        rescreen = gates.index("### 6.6.4 Re-screen architecture applicability")
        session_fit = gates.index("## Stage 7 — Session-Fit Check")
        final_rescreen = write.index("### 8.2.4 Architecture–Plan Convergence recheck")
        final_approval = write.index("### 8.3 Final Decision")

        self.assertLess(rescreen, session_fit)
        self.assertLess(final_rescreen, final_approval)
        self.assertIn("same attested TZ/IC rows", write[final_rescreen:final_approval])
        self.assertIn("invalidates convergence", write[final_rescreen:final_approval])

    def test_written_plan_carries_a_machine_checked_disposition(self):
        template = (PLAN / "artifact-template.md").read_text(encoding="utf-8")
        write = (PLAN / "stage-8-9-write.md").read_text(encoding="utf-8")

        for field in (
            '"architecture_disposition"',
            '"decision": "required"',
            '"decided_by": "human"',
            '"convergence"',
            '"iteration_count"',
            '"decision_refs"',
        ):
            self.assertIn(field, template)
        self.assertIn("Every new full plan writes the exact\n`architecture_disposition`", write)
        self.assertIn("required shaping result is `converged`", write)

    def test_required_baseline_is_published_only_after_stable_plan_write(self):
        write = (PLAN / "stage-8-9-write.md").read_text(encoding="utf-8")
        stage_nine = write.index("## Stage 9 — Write the Plan")
        stable_ids = write.index("freeze final IDs", stage_nine)
        baseline_route = write.rindex("/core-engineering:ce-architecture [project-slug]")

        self.assertLess(stage_nine, stable_ids)
        self.assertLess(stable_ids, baseline_route)
        self.assertIn("Do not print a direct\n  spec command", write[baseline_route:])

    def test_revision_path_reopens_architecture_only_for_relevant_delta(self):
        convergence = (PLAN / "stage-5a-architecture-convergence.md").read_text(
            encoding="utf-8"
        )
        revision = (PLAN / "stage-R-revision.md").read_text(encoding="utf-8")
        shaping = (ARCH / "shaping-mode.md").read_text(encoding="utf-8")

        self.assertIn("**architecture posture touched**", revision)
        self.assertIn("missing legacy disposition", revision)
        self.assertIn("Architecture applicability + convergence", revision)
        self.assertRegex(
            revision,
            r"Architecture proposes;\s+Stage R and the\s+human alone modify the\s+plan",
        )
        self.assertIn("Preserve architecture disposition", revision)
        self.assertIn("Stable source (revision only)", convergence)
        self.assertIn("revision-only stable source when applicable", shaping)
        self.assertIn("unique `PNN-slug` alias", revision)
        self.assertIn("Translate every returned delta\n   through the alias map", revision)
        self.assertIn("never let architecture alter a\n   stable id", revision)

        preshape = revision.index("Pre-Reachability architecture applicability")
        reachability = revision.index("**Reachability**", preshape)
        post_reach = revision.index("Post-Reachability architecture re-screen", reachability)
        session_fit = revision.index("**Session-Fit**", post_reach)
        attest = revision.index("**8.2.1 / 8.2.2 attestations**", session_fit)
        final_recheck = revision.index("Post-attestation architecture convergence recheck", attest)
        self.assertEqual(
            [preshape, reachability, post_reach, session_fit, attest, final_recheck],
            sorted([preshape, reachability, post_reach, session_fit, attest, final_recheck]),
        )

    def test_composed_shape_uses_the_parent_gate_sequence(self):
        convergence = (PLAN / "stage-5a-architecture-convergence.md").read_text(
            encoding="utf-8"
        )
        shaping = (ARCH / "shaping-mode.md").read_text(encoding="utf-8")

        self.assertIn("current plan gate manifest", convergence)
        self.assertIn(
            "Gate <parent_gate_index> of <parent_gate_total> — Architecture Shaping Scope",
            shaping,
        )
        self.assertNotIn("Gate 1 of 1 — Architecture Shaping Scope", shaping)

    def test_public_spine_is_disposition_driven(self):
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        matrix = (REPO / "docs/USAGE-MATRIX.md").read_text(encoding="utf-8")
        how = (REPO / "docs/HOW-IT-WORKS.md").read_text(encoding="utf-8")

        self.assertIn("plan ⇄ architecture shape", readme)
        self.assertIn("conditionally invokes read-only architecture shaping", matrix)
        self.assertIn("when the disposition is `required`", matrix)
        self.assertIn("required missing or stale architecture blocks", how)


if __name__ == "__main__":
    unittest.main()
