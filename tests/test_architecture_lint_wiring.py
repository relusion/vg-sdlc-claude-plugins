"""Pin conditional architecture routing and downstream consumption seams."""

import json
import re
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
ARCH = REPO / "plugins/core-engineering/skills/ce-architecture"
SPEC = REPO / "plugins/core-engineering/skills/ce-spec"
AUTO_BUILD = REPO / "plugins/core-engineering/skills/ce-auto-build"
GO = REPO / "plugins/core-engineering/skills/ce-go/SKILL.md"
IMPLEMENT = REPO / "plugins/core-engineering/skills/ce-implement/SKILL.md"
REVIEW = REPO / "plugins/core-engineering/skills/ce-review/SKILL.md"
PLAN_R = REPO / "plugins/core-engineering/skills/ce-plan/stage-R-revision.md"
PLAN_TEMPLATE = REPO / "plugins/core-engineering/skills/ce-plan/artifact-template.md"
MINIMAL = REPO / "tests/fixtures/single-feature-minimal/docs/plans"


class ArchitectureLintWiring(unittest.TestCase):
    def test_lint_precedes_final_approval_and_publish(self):
        stage = (ARCH / "stage-3-5-review-write.md").read_text(encoding="utf-8")
        lint = stage.index("### 4.2 Run architecture-lint")
        approval = stage.index("### 5.1 Final Architecture Approval")
        publish = stage.index("### 5.2 Publish transactionally")
        self.assertLess(lint, approval)
        self.assertLess(approval, publish)

    def test_all_exit_codes_have_explicit_disposition(self):
        stage = (ARCH / "stage-3-5-review-write.md").read_text(encoding="utf-8")
        self.assertIn("**exit 0:**", stage)
        self.assertIn("**exit 1:**", stage)
        self.assertIn("**exit 2:**", stage)
        self.assertIn("Never call this a lint PASS", stage)

    def test_publish_is_bound_to_reviewed_scratch_and_human_status(self):
        stage = (ARCH / "stage-3-5-review-write.md").read_text(encoding="utf-8")
        self.assertIn("scripts/architecture-publish.py", stage)
        self.assertIn("--publish-status <approved|approved-with-gaps>", stage)
        self.assertIn("Do not edit the scratch package or destination after approval", stage)
        self.assertIn("Markdown bytes must remain identical to review", stage)
        self.assertIn("not crash-atomic", stage)

    def test_gate_pauses_drop_and_reacquire_write_authority(self):
        skill = (ARCH / "SKILL.md").read_text(encoding="utf-8")
        evidence = (ARCH / "stage-0-2-evidence-model.md").read_text(
            encoding="utf-8"
        )
        publish = (ARCH / "stage-3-5-review-write.md").read_text(encoding="utf-8")
        self.assertIn("immediately before yielding at any human\n   gate", skill)
        self.assertIn("reacquire this exact lease", skill)
        self.assertIn("lease-control baseline may remain", skill)
        self.assertIn("Restore the deny-only baseline immediately\nbefore printing", evidence)
        self.assertIn("Restore the deny-only baseline immediately before yielding", publish)
        self.assertIn("reacquire the exact ce-architecture\nlease", publish)

    def test_spec_validates_present_package_and_routes_absence_by_disposition(self):
        stage = (SPEC / "stage-0-1-frame-resolve.md").read_text(encoding="utf-8")
        self.assertIn("scripts/plan-lint.py", stage)
        self.assertIn("scripts/architecture-selection-lint.py", stage)
        self.assertIn("scripts/architecture-lint.py", stage)
        self.assertIn("--require-architecture-direction --json", stage)
        self.assertIn("--consumer --json", stage)
        self.assertIn("architecture_disposition", stage)
        self.assertIn("`required` + convergence `converged`", stage)
        self.assertIn("coverage gap — recommended package absent", stage)
        self.assertIn("N/A — plan disposition not-required", stage)
        self.assertIn("Architecture: waived by human", stage)
        self.assertIn("legacy `A12`/`A13` gaps are defects", stage)
        self.assertIn("readable ADR recorded as accepted", stage)
        self.assertIn("repository evidence drift", stage)
        self.assertIn("data entities/lifecycle", stage)
        self.assertIn("Missing-package disposition", stage)
        self.assertIn("present package is never", stage)
        self.assertLess(
            stage.index("scripts/plan-lint.py"),
            stage.index("scripts/architecture-selection-lint.py"),
        )
        self.assertLess(
            stage.index("scripts/architecture-selection-lint.py"),
            stage.index("scripts/architecture-lint.py"),
        )

    def test_auto_build_enforces_architecture_before_execution_baseline(self):
        stage = (AUTO_BUILD / "stage-0-kickoff.md").read_text(encoding="utf-8")
        self.assertIn("### 1.1 Enforce the architecture disposition", stage)
        self.assertIn("scripts/plan-lint.py", stage)
        self.assertIn("scripts/architecture-selection-lint.py", stage)
        self.assertIn("scripts/architecture-lint.py", stage)
        self.assertIn("--require-architecture-direction --json", stage)
        self.assertIn("--consumer --json", stage)
        self.assertIn("recommended architecture package absent", stage)
        self.assertIn("N/A — plan disposition not-required", stage)
        self.assertIn("human waiver rationale", stage)
        self.assertIn("legacy `A12`/`A13` gaps are also blocking", stage)
        self.assertIn("both a fresh\nrun and `--resume`", stage)
        self.assertLess(
            stage.index("scripts/plan-lint.py"),
            stage.index("scripts/architecture-selection-lint.py"),
        )
        self.assertLess(
            stage.index("scripts/architecture-selection-lint.py"),
            stage.index("scripts/architecture-lint.py"),
        )
        self.assertLess(
            stage.index("### 1.1 Enforce the architecture disposition"),
            stage.index("## 2. Check the execution baseline"),
        )

    def test_go_routes_architecture_prerequisite_before_spec_or_auto_build(self):
        skill = GO.read_text(encoding="utf-8")
        self.assertIn("What is the plan's architecture prerequisite?", skill)
        self.assertIn("`decided_by: human`", skill)
        self.assertIn("non-negative\n    integer `iteration_count`", skill)
        self.assertIn("`required` + `converged`", skill)
        self.assertIn("lstat-confirmed package absence", skill)
        self.assertIn("/core-engineering:ce-architecture <slug>", skill)
        self.assertIn("/core-engineering:ce-plan` Stage R", skill)
        self.assertIn("Never claim presence means current", skill)

    def test_go_applies_full_h9_h10_before_every_downstream_build_route(self):
        skill = GO.read_text(encoding="utf-8")
        self.assertIn(
            "`/core-engineering:ce-spec`, `/core-engineering:ce-implement`, or\n"
            "  `/core-engineering:ce-auto-build`",
            skill,
        )
        self.assertIn("Reproduce the full plan H9/H10 check here", skill)
        self.assertIn("has exactly `decision`, `triggers`, `rationale`", skill)
        self.assertIn("direction has exactly `status`, `artifact`, `artifact_sha256`", skill)
        self.assertIn("`architecture-selection.json`", skill)
        self.assertIn("non-boolean integer >= 0", skill)
        self.assertIn("`explicit-architecture-deliverable`", skill)
        self.assertIn("`baseline-preference`", skill)
        self.assertIn("triggers are unique", skill)
        self.assertIn("first nine load-bearing trigger ids", skill)
        self.assertIn("`recommended` uses only the final three recommendation ids", skill)
        self.assertIn("and pairs with\n    `converged`", skill)
        self.assertIn("`deferred` and zero iterations", skill)
        self.assertIn("preserves a prior `direction-selected`/`adopted-existing` binding", skill)
        self.assertIn("`plan_tier`, when present, is exactly `standard` or `light`", skill)
        self.assertIn("single-feature minimal plan records the prerequisite\n   `N/A by construction`", skill)

    def test_implement_preflights_plan_and_architecture_before_spec_trust(self):
        skill = IMPLEMENT.read_text(encoding="utf-8")
        preflight = skill.index("Complete the architecture preflight")
        lint = skill.index('scripts/plan-lint.py')
        selection_lint = skill.index("scripts/architecture-selection-lint.py")
        architecture_lint = skill.index("scripts/architecture-lint.py")
        trust = skill.index("After that preflight, load the spec")
        mutation = skill.index("Ensure `.test-guard/` is ignored")
        self.assertLess(preflight, lint)
        self.assertLess(lint, selection_lint)
        self.assertLess(selection_lint, architecture_lint)
        self.assertLess(architecture_lint, trust)
        self.assertLess(trust, mutation)
        self.assertIn("legacy missing disposition/direction (`A12`/`A13`)", skill)
        self.assertIn("Exit 1 or 2 routes to Stage R before the spec is trusted", skill)
        self.assertIn("--require-architecture-direction --json", skill)
        self.assertIn("scripts/architecture-selection-lint.py", skill)
        self.assertIn("scripts/architecture-lint.py", skill)
        self.assertIn("--consumer --json", skill)
        self.assertIn("`convergence.decision_refs` entry", skill)
        self.assertIn("readable, regular ADR recorded as\n**accepted**", skill)

    def test_implement_inventory_and_absence_matrix_precede_code_mutation(self):
        skill = IMPLEMENT.read_text(encoding="utf-8")
        transaction = skill.index(".architecture-publish-")
        occupied_lint = skill.index("scripts/architecture-lint.py")
        absence = skill.index("Missing-package implementation disposition")
        mutation = skill.index("Ensure `.test-guard/` is ignored")
        self.assertLess(transaction, occupied_lint)
        self.assertLess(occupied_lint, absence)
        self.assertLess(absence, mutation)
        for transaction_kind in ("lock", "stage", "backup", "rejected"):
            self.assertIn(transaction_kind, skill)
        self.assertIn("`required` + convergence `converged`", skill)
        self.assertIn("coverage gap — recommended package absent", skill)
        self.assertIn("N/A — plan disposition not-required", skill)
        self.assertIn("Architecture: waived by human", skill)
        self.assertIn("visible at this\n**Proceed** gate", skill)
        self.assertIn("N/A by construction", skill)

    def test_plan_floor_precedes_single_feature_retirement(self):
        stage = (ARCH / "stage-0-2-evidence-model.md").read_text(encoding="utf-8")
        plan_floor = stage.index("### 0.4 Run the full-plan floor")
        single_feature = stage.index("lint-validated one-feature full plan")
        self.assertLess(plan_floor, single_feature)
        self.assertIn("cannot enter the\n  destructive retirement branch", stage)
        self.assertIn("scripts/architecture-retire.py", stage)
        self.assertIn("--expected-token <reviewed-64-lowercase-sha256>", stage)
        self.assertIn("`removed_paths`, do not claim rollback or completion", stage)

    def test_baseline_architecture_requires_selection_and_direction_before_synthesis(self):
        stage = (ARCH / "stage-0-2-evidence-model.md").read_text(encoding="utf-8")
        floor = stage.index("### 0.4 Run the full-plan floor")
        selection_lint = stage.index("scripts/architecture-selection-lint.py", floor)
        plan_lint = stage.index("scripts/plan-lint.py", selection_lint)
        synthesis = stage.index("uses the normal workflow below", plan_lint)
        self.assertLess(floor, selection_lint)
        self.assertLess(selection_lint, plan_lint)
        self.assertLess(plan_lint, synthesis)
        self.assertIn("--require-architecture-direction --json", stage[plan_lint:synthesis])
        self.assertIn("either exit 1", stage[selection_lint:synthesis])
        self.assertIn("either exit 2", stage[selection_lint:synthesis])
        self.assertIn("route to `/core-engineering:ce-plan` Stage R", stage[selection_lint:synthesis])
        self.assertIn("absent legacy posture or direction routes to Stage R", stage[selection_lint:synthesis])

    def test_all_absence_routes_park_on_publish_transaction_state(self):
        architecture = (ARCH / "stage-0-2-evidence-model.md").read_text(
            encoding="utf-8"
        )
        spec = (SPEC / "stage-0-1-frame-resolve.md").read_text(encoding="utf-8")
        plan_revision = PLAN_R.read_text(encoding="utf-8")
        for text in (architecture, spec, plan_revision):
            self.assertIn(".architecture-publish-", text)
            for transaction_kind in ("lock", "stage", "backup", "rejected"):
                self.assertIn(transaction_kind, text)
            self.assertIn("explicit human recovery", text)

        scan = architecture.index("### 0.2 Recover publication transaction state")
        absent_route = architecture.index("lstat-confirmed `architecture` namespace absence")
        self.assertLess(scan, absent_route)
        self.assertIn("never record architecture as absent", spec)
        self.assertIn("never treat their presence as architecture\nabsence", plan_revision)

    def test_minimal_plan_fixture_has_stable_qualified_identity(self):
        registry = json.loads((MINIMAL / "plans.json").read_text(encoding="utf-8"))
        self.assertEqual(len(registry["plans"]), 1)
        slug = registry["plans"][0]["slug"]
        plan_dir = MINIMAL / slug
        plan = (plan_dir / "feature-plan.md").read_text(encoding="utf-8")

        self.assertFalse((plan_dir / "plan.json").exists())
        self.assertFalse((plan_dir / "architecture-selection.json").exists())
        self.assertFalse((plan_dir / "shared-context.md").exists())
        self.assertFalse((plan_dir / "features").exists())
        self.assertEqual(len(re.findall(r"^## 4\. Single Feature\s*$", plan, re.M)), 1)
        ids = re.findall(r"^Feature ID:\s*(\S+)\s*$", plan, re.M)
        runs = re.findall(
            r"^Run:\s*/core-engineering:ce-spec\s+(\S+)/(\S+)\s*$",
            plan,
            re.M,
        )
        self.assertEqual(ids, ["01-health-check"])
        self.assertEqual(runs, [(slug, ids[0])])
        checkboxes = re.findall(r"^- \[ \] (\S+) — implemented and verified\s*$", plan, re.M)
        self.assertEqual(checkboxes, ids)
        self.assertIn("### Security Projection", plan)
        self.assertRegex(
            plan,
            r"security_obligations:\s*\n\s*- feature: 01-health-check\s*\n"
            r"\s*threat_ids: \[\]",
        )
        self.assertIn("assessment: assessed-negative", plan)
        self.assertIn("confirmed_by: human", plan)

    def test_minimal_plan_routes_before_full_plan_floor(self):
        architecture = (ARCH / "stage-0-2-evidence-model.md").read_text(
            encoding="utf-8"
        )
        transaction_scan = architecture.index(".architecture-publish-")
        minimal_route = architecture.index("registry-backed single-feature minimal")
        plan_floor = architecture.index("Run the full-plan floor")
        self.assertLess(transaction_scan, minimal_route)
        self.assertLess(minimal_route, plan_floor)
        self.assertIn("/core-engineering:ce-spec <slug>/<id>", architecture)

    def test_spec_documents_minimal_authority_and_normal_output(self):
        stage = (SPEC / "stage-0-1-frame-resolve.md").read_text(encoding="utf-8")
        skill = (SPEC / "SKILL.md").read_text(encoding="utf-8")
        write = (SPEC / "stage-4-5-tasks-write.md").read_text(encoding="utf-8")
        for text in (stage, skill):
            self.assertIn("plan_mode: single-feature-minimal", text)
            self.assertIn("architecture-selection.json", text)
            self.assertIn("Feature ID: <id>", text)
            self.assertIn("Run: /core-engineering:ce-spec <slug>/<id>", text)
            self.assertIn("sole plan authority", text)
        self.assertIn("N/A by construction", stage)
        self.assertIn("write the same normal spec outputs", write)
        self.assertIn("no\nledger file", write)

    def test_plan_template_requires_minimal_qualified_run_line(self):
        template = PLAN_TEMPLATE.read_text(encoding="utf-8")
        minimal = template[template.index("## Recommended Minimal Output"):]
        self.assertIn("Feature ID: <id>", minimal)
        self.assertIn(
            "Run: /core-engineering:ce-spec service-health/01-health-check",
            minimal,
        )
        self.assertIn("must agree exactly", minimal)
        self.assertIn("implemented and verified", minimal)

    def test_minimal_plan_handoff_reaches_implement_and_review(self):
        implement = IMPLEMENT.read_text(encoding="utf-8")
        review = REVIEW.read_text(encoding="utf-8")
        for text in (implement, review):
            self.assertIn("single-feature-minimal", text)
            self.assertIn("feature-plan.md", text)
            self.assertIn("N/A by construction", text)
            self.assertIn("/core-engineering:ce-plan", text)
        self.assertIn("sole plan context", implement)
        self.assertIn("the ordinary Security and Correctness lenses still run", review)

    def test_review_consumes_minimal_inline_security_projection(self):
        review = REVIEW.read_text(encoding="utf-8")
        self.assertIn("including its inline\n  `### Security Projection`", review)
        self.assertIn("matching `security_obligations` row", review)
        self.assertIn("An explicit `threat_ids: []` is an\n   assessed negative", review)
        self.assertIn(
            "Record only the\n   interaction contract and cross-feature obligations `N/A by construction`",
            review,
        )
        self.assertIn("minimal plan's inline Security Projection", review)
        self.assertIn("previously undocumented untrusted entry reaches the sink", review)
        self.assertIn("name the projection contradiction as `plan_conflict`", review)
        self.assertIn("set `suggested_escalation` to `/core-engineering:ce-plan`", review)
        self.assertIn("defect is also `confirmed`", review)
        self.assertNotIn("record both plan-owned projections `N/A by\n   construction`", review)

    def test_implement_reuses_minimal_plan_authority(self):
        implement = IMPLEMENT.read_text(encoding="utf-8")
        self.assertIn("plan_mode: single-feature-minimal", implement)
        self.assertIn("architecture-selection.json", implement)
        self.assertIn("feature-plan.md` as the\n  sole plan context", implement)
        self.assertIn("ce-spec.md` + `tasks.json` remain the implementation authority", implement)
        self.assertIn("mixed shape", implement)
        self.assertIn("match the one checkbox keyed by the exact `Feature ID`", implement)
        self.assertIn("rather than appending or guessing a row", implement)

    def test_validator_is_registered_fork(self):
        manifest = (REPO / "plugins/core-engineering/fork-manifest.json").read_text(
            encoding="utf-8"
        )
        self.assertIn("ce-architecture/scripts/architecture-lint.py", manifest)
        self.assertIn("ce-spec/scripts/architecture-lint.py", manifest)
        self.assertIn("ce-auto-build/scripts/architecture-lint.py", manifest)
        self.assertIn("ce-implement/scripts/architecture-lint.py", manifest)
        self.assertIn("ce-implement/scripts/plan-lint.py", manifest)
        self.assertIn("ce-architecture/scripts/architecture-selection-lint.py", manifest)
        self.assertIn("ce-spec/scripts/architecture-selection-lint.py", manifest)
        self.assertIn("ce-auto-build/scripts/architecture-selection-lint.py", manifest)
        self.assertIn("ce-implement/scripts/architecture-selection-lint.py", manifest)
        self.assertEqual(
            (ARCH / "scripts/architecture-lint.py").read_bytes(),
            (SPEC / "scripts/architecture-lint.py").read_bytes(),
        )
        self.assertEqual(
            (ARCH / "scripts/architecture-lint.py").read_bytes(),
            (AUTO_BUILD / "scripts/architecture-lint.py").read_bytes(),
        )
        self.assertEqual(
            (ARCH / "scripts/architecture-lint.py").read_bytes(),
            (REPO / "plugins/core-engineering/skills/ce-implement/scripts/architecture-lint.py").read_bytes(),
        )
        self.assertEqual(
            (ARCH / "scripts/architecture-selection-lint.py").read_bytes(),
            (SPEC / "scripts/architecture-selection-lint.py").read_bytes(),
        )
        self.assertEqual(
            (ARCH / "scripts/architecture-selection-lint.py").read_bytes(),
            (AUTO_BUILD / "scripts/architecture-selection-lint.py").read_bytes(),
        )
        self.assertEqual(
            (ARCH / "scripts/architecture-selection-lint.py").read_bytes(),
            (REPO / "plugins/core-engineering/skills/ce-implement/scripts/architecture-selection-lint.py").read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
