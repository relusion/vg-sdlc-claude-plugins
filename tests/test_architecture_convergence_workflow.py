"""Pin the plan/architecture convergence boundary and route ordering."""

import re
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PLAN = REPO / "plugins/core-engineering/skills/ce-plan"
ARCH = REPO / "plugins/core-engineering/skills/ce-architecture"


class ArchitectureConvergenceWorkflow(unittest.TestCase):
    def test_architecture_direction_stage_precedes_feature_decomposition(self):
        orchestrator = (PLAN / "SKILL.md").read_text(encoding="utf-8")
        intake = (PLAN / "stage-0-1-understand.md").read_text(encoding="utf-8")
        direction = (PLAN / "stage-1a-architecture-direction.md").read_text(
            encoding="utf-8"
        )
        decomposition = (PLAN / "stage-2-3-decompose-score.md").read_text(
            encoding="utf-8"
        )

        stage_map = orchestrator[
            orchestrator.index("| Stages |") : orchestrator.index(
                "Stage 0 branches", orchestrator.index("| Stages |")
            )
        ]
        self.assertLess(stage_map.index("| 1A |"), stage_map.index("| 2–3 |"))
        self.assertIn(
            "**Next:** when Stage 1 is complete, load\n"
            "`${CLAUDE_SKILL_DIR}/stage-1a-architecture-direction.md`",
            intake,
        )
        self.assertIn("## 1A.1 Build the coarse capability model", direction)
        self.assertIn("Use capability ids `C01`, `C02`, …", direction)
        self.assertIn("does **not** create provisional features", direction)
        self.assertIn(
            "Invoke `/core-engineering:ce-architecture explore:<slug>`",
            direction,
        )
        selection_lint = direction.index("architecture-selection-lint.py")
        decomposition_route = direction.index(
            "exit 0 load `${CLAUDE_SKILL_DIR}/stage-2-3-decompose-score.md`"
        )
        self.assertLess(selection_lint, decomposition_route)
        self.assertIn(
            "Load this file only\nafter Stage 1A has recorded a fresh selected architecture direction",
            decomposition,
        )

    def test_required_route_needs_human_direction_selection_before_stage_two(self):
        direction = (PLAN / "stage-1a-architecture-direction.md").read_text(
            encoding="utf-8"
        )
        exploration = (ARCH / "exploration-mode.md").read_text(encoding="utf-8")

        required_gate = direction[
            direction.index("For `required`, ask:") : direction.index(
                "For `recommended`, add one option:"
            )
        ]
        selection_validation = direction[
            direction.index("## 1A.7 Validate and persist the selected binding") :
            direction.index("## 1A.8 Freshness and back-edge rule")
        ]

        self.assertIn("Stage 2 remains blocked until a fresh human selection", required_gate)
        self.assertNotIn("Defer", required_gate)
        self.assertIn("There is no defer option for `required`", direction)
        self.assertIn(
            "`selection.status` is exactly `direction-selected`",
            selection_validation,
        )
        self.assertIn(
            "`selection.decided_by` is exactly `human`",
            selection_validation,
        )
        self.assertRegex(
            exploration,
            r"Even a sole viable direction requires an\s+affirmative selection",
        )
        self.assertIn(
            "A recommendation is decision support",
            exploration,
        )
        self.assertIn("canonical decision-relevant projection", selection_validation)
        self.assertNotIn("current exact input bytes", selection_validation)

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
        convergence = (PLAN / "stage-5a-architecture-convergence.md").read_text(
            encoding="utf-8"
        )
        route = gates.index("After `Continue`, route by the recorded applicability result")
        shape = gates.index("stage-5a-architecture-convergence.md", route)
        reachability = gates.index("## Stage 6 — Reachability", route)

        self.assertLess(route, shape)
        self.assertLess(shape, reachability)
        self.assertIn("and run Stage 5A before Stage 6", gates[shape:reachability])
        self.assertIn("Load this file after\nCandidate Review", convergence)

    def test_selected_direction_is_hash_bound_through_shape_and_final_write(self):
        convergence = (PLAN / "stage-5a-architecture-convergence.md").read_text(
            encoding="utf-8"
        )
        shaping = (ARCH / "shaping-mode.md").read_text(encoding="utf-8")
        write = (PLAN / "stage-8-9-write.md").read_text(encoding="utf-8")
        template = (PLAN / "artifact-template.md").read_text(encoding="utf-8")

        for field in (
            "architecture_selection_path:",
            "architecture_selection_sha256:",
            "exploration_id:",
            "selected_option_id:",
            "selected_option_sha256:",
        ):
            self.assertIn(field, convergence)
            self.assertIn(field, shaping)

        self.assertIn(
            "source_architecture_selection_sha256",
            convergence,
        )
        self.assertIn("source_selected_option_sha256", convergence)
        self.assertIn("selected-direction-changed-during-shaping", shaping)

        publish = write[
            write.index("**Publish the selected direction.**") : write.index(
                "**Record the plan tier.**"
            )
        ]
        self.assertIn("Copy the exact reviewed draft", publish)
        self.assertIn("architecture-selection.json", publish)
        self.assertIn("Compute the\nSHA-256 of the final bytes", publish)
        self.assertIn("`architecture_disposition.direction`", publish)
        self.assertIn("selected option id/hash", publish)
        self.assertIn("architecture-selection.json", template)

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
            "shaping_input_sha256:",
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
        self.assertIn("source_shaping_input_sha256", convergence)
        self.assertIn("source_shaping_input_sha256", shaping)
        self.assertIn("hash the\nexact UTF-8 bytes", convergence)
        self.assertIn("shaping-input-changed", shaping)
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

    def test_recommended_shaping_has_an_explicit_human_election_in_both_tiers(self):
        orchestrator = (PLAN / "SKILL.md").read_text(encoding="utf-8")
        gates = (PLAN / "stage-4-7-gates.md").read_text(encoding="utf-8")
        write = (PLAN / "stage-8-9-write.md").read_text(encoding="utf-8")
        template = (PLAN / "artifact-template.md").read_text(encoding="utf-8")

        self.assertIn("### 5.4.1 Recommended Architecture Shaping Election", gates)
        self.assertIn("in both standard and light tiers", gates)
        self.assertIn("**Shape this candidate**", gates)
        self.assertIn("**Defer candidate shaping**", gates)
        self.assertIn("`iteration_count: 0`", gates)
        self.assertIn("recommended-shaping election still fires", orchestrator)
        self.assertIn("return to §5.4.1", write)
        self.assertIn("Stage 9 never invents", write)
        self.assertIn("direction status and shaping convergence are independent", template)

    def test_minimal_plan_carries_security_instead_of_inferring_no_surface(self):
        gates = (PLAN / "stage-4-7-gates.md").read_text(encoding="utf-8")
        template = (PLAN / "artifact-template.md").read_text(encoding="utf-8")
        spec = (REPO / "plugins/core-engineering/skills/ce-spec/SKILL.md").read_text(
            encoding="utf-8"
        )
        spec_design = (
            REPO
            / "plugins/core-engineering/skills/ce-spec/stage-2-3-testable-design.md"
        ).read_text(encoding="utf-8")

        minimal = template[template.index("## Recommended Minimal Output"):]
        self.assertNotIn("no cross-boundary surface *by construction*", minimal)
        self.assertIn("### Security Projection", minimal)
        self.assertIn("security_obligations", minimal)
        self.assertIn("feature count is never\nevidence that security is absent", gates)
        self.assertIn("minimal plan whose inline Security Projection assigns", spec)
        self.assertIn("minimal plan's inline Security Projection", spec_design)
        self.assertIn("For `TZ-NNN`, consume\nthe inline Security Projection", spec_design)
        self.assertIn("explicit empty `threat_ids` list is an assessed\nnegative", spec_design)
        self.assertNotIn(
            "`TZ-NNN`, and `IC-NNN` rows above as `N/A by construction`",
            spec_design,
        )

    def test_plan_revalidates_hash_bound_brief_before_any_skip(self):
        intake = (PLAN / "stage-0-1-understand.md").read_text(encoding="utf-8")
        brief = (REPO / "plugins/core-engineering/skills/ce-brief/SKILL.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("brief-lint.py", intake)
        self.assertIn("--skip-persona-check --json", intake)
        self.assertIn("Only exit 0 authorizes the skip map", intake)
        self.assertIn("authorize **no skips**", intake)
        self.assertIn('"brief_sha256":"<hash>"', brief)
        self.assertIn("Exit 2 never arms skipping", brief)

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
        self.assertIn("architecture-selection-lint.py", write)
        self.assertIn("--require-architecture-direction", write)

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
        self.assertIn("missing legacy disposition/direction", revision)
        self.assertIn("Architecture applicability + convergence", revision)
        self.assertRegex(
            revision,
            r"Architecture proposes;\s+Stage R and the\s+human alone modify the\s+plan",
        )
        self.assertIn("Preserve or replace independent locks independently", revision)
        self.assertIn("`architecture-selection.json` byte-for-byte", revision)
        self.assertIn("Stable source (revision only)", convergence)
        self.assertIn("revision-only stable source when applicable", shaping)
        self.assertIn("unique `PNN-slug` alias", revision)
        self.assertIn("Translate every returned delta\n   through the alias map", revision)
        self.assertIn("never let architecture alter a\n   stable id", revision)

        direction = revision.index("Pre-decomposition architecture direction")
        preshape = revision.index("Pre-Reachability architecture applicability", direction)
        reachability = revision.index("**Reachability**", preshape)
        post_reach = revision.index("Post-Reachability architecture re-screen", reachability)
        session_fit = revision.index("**Session-Fit**", post_reach)
        attest = revision.index("**8.2.1 / 8.2.2 attestations**", session_fit)
        final_recheck = revision.index("Post-attestation architecture convergence recheck", attest)
        self.assertEqual(
            [
                direction,
                preshape,
                reachability,
                post_reach,
                session_fit,
                attest,
                final_recheck,
            ],
            sorted(
                [
                    direction,
                    preshape,
                    reachability,
                    post_reach,
                    session_fit,
                    attest,
                    final_recheck,
                ]
            ),
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

    def test_public_spine_describes_architecture_first_planning(self):
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        matrix = (REPO / "docs/USAGE-MATRIX.md").read_text(encoding="utf-8")
        how = (REPO / "docs/HOW-IT-WORKS.md").read_text(encoding="utf-8")

        self.assertIn(
            "plan [architecture explore + human direction] → decompose ⇄ architecture shape",
            readme,
        )
        self.assertIn("pre-decomposition architecture exploration/selection", matrix)
        self.assertIn("Detailed decomposition starts only after", matrix)
        self.assertIn(
            "generate and score complete solution directions before decomposition",
            how,
        )
        self.assertIn("required missing or stale architecture blocks", how)


if __name__ == "__main__":
    unittest.main()
