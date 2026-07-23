"""Pin conditional architecture routing and downstream consumption seams."""

import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
ARCH = REPO / "plugins/core-engineering/skills/ce-architecture"
SPEC = REPO / "plugins/core-engineering/skills/ce-spec"
AUTO_BUILD = REPO / "plugins/core-engineering/skills/ce-auto-build"
GO = REPO / "plugins/core-engineering/skills/ce-go/SKILL.md"
IMPLEMENT = REPO / "plugins/core-engineering/skills/ce-implement/SKILL.md"
IMPLEMENT_PREFLIGHT = (
    REPO
    / "plugins/core-engineering/skills/ce-implement/stage-0-architecture-preflight.md"
)
REVIEW = REPO / "plugins/core-engineering/skills/ce-review/SKILL.md"
REVIEW_PREFLIGHT = (
    REPO
    / "plugins/core-engineering/skills/ce-review/stage-0-architecture-preflight.md"
)
AUTO_PIPELINE = AUTO_BUILD / "stage-1-2-pipeline.md"
PLAN_R = REPO / "plugins/core-engineering/skills/ce-plan/stage-R-revision.md"
PLAN_TEMPLATE = REPO / "plugins/core-engineering/skills/ce-plan/artifact-template.md"


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
        self.assertRegex(
            stage,
            r"--publish-status\s+\\?\n?\s*"
            r"<accepted-for-specification\\?\|accepted-for-specification-with-gaps>",
        )
        self.assertIn("--recorded-by", stage)
        self.assertIn("--approval-authority", stage)
        self.assertIn("--approval-reference", stage)
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
        self.assertIn(
            "Restore the deny-only baseline immediately before yielding this gate",
            evidence,
        )
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
        self.assertIn("coverage gap — recommended package explicitly deferred", stage)
        self.assertIn("N/A — plan disposition not-required", stage)
        self.assertIn("selected and converged direction requires its governed package", stage)
        self.assertNotIn("| `waived` |", stage)
        self.assertIn("malformed or missing required", stage)
        self.assertIn("disposition/direction is one such defect", stage)
        self.assertNotIn("legacy", stage)
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

    def test_active_consumers_require_the_current_selection_schema(self):
        stages = (
            SPEC / "stage-0-1-frame-resolve.md",
            IMPLEMENT_PREFLIGHT,
            REVIEW_PREFLIGHT,
            AUTO_BUILD / "stage-0-kickoff.md",
        )
        for path in stages:
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                command_start = text.index("scripts/architecture-selection-lint.py")
                command_end = text.index("--json", command_start)
                self.assertIn(
                    "--require-current-schema",
                    text[command_start:command_end],
                )

    def test_auto_build_enforces_architecture_before_execution_baseline(self):
        stage = (AUTO_BUILD / "stage-0-kickoff.md").read_text(encoding="utf-8")
        self.assertIn("### 1.1 Enforce the architecture disposition", stage)
        self.assertIn("scripts/plan-lint.py", stage)
        self.assertIn("scripts/architecture-selection-lint.py", stage)
        self.assertIn("scripts/architecture-lint.py", stage)
        self.assertIn("--require-architecture-direction --json", stage)
        self.assertIn("--consumer --json", stage)
        self.assertIn("recommended architecture package explicitly deferred", stage)
        self.assertIn("N/A — plan disposition not-required", stage)
        self.assertIn("selected direction requires its governed package", stage)
        self.assertNotIn("| `waived` |", stage)
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
        self.assertIn(
            "the architecture prerequisite before spec, implement, or auto-build",
            skill,
        )
        self.assertIn(
            "docs/plans/<slug> --require-architecture-direction --json",
            skill,
        )
        self.assertIn(
            "exit 0 plus `required`/selected/converged",
            skill,
        )
        self.assertIn("lstat-confirmed absent", skill)
        self.assertIn("/core-engineering:ce-architecture <slug>", skill)
        self.assertIn("/core-engineering:ce-plan` Stage R", skill)
        self.assertIn("Never claim namespace presence means current", skill)

    def test_go_delegates_architecture_floor_to_colocated_plan_lint(self):
        skill = GO.read_text(encoding="utf-8")
        self.assertIn(
            "run the plan's deterministic floor rather than\n"
            "reproducing its schema in this router",
            skill,
        )
        self.assertIn(
            '"${CLAUDE_SKILL_DIR}/../ce-plan/scripts/plan-lint.py"',
            skill,
        )
        self.assertIn(
            "docs/plans/<slug> --require-architecture-direction --json",
            skill,
        )
        self.assertIn(
            "exit 1 or 2 routes to `/core-engineering:ce-plan` Stage R",
            skill,
        )
        self.assertIn(
            "otherwise continue to the requested downstream workflow",
            skill,
        )
        self.assertNotIn("Reproduce the full plan H9/H10 check here", skill)
        self.assertNotIn("first nine load-bearing trigger ids", skill)
        self.assertNotIn("single-feature minimal plan", skill)

    def test_implement_preflights_plan_and_architecture_before_spec_trust(self):
        skill = IMPLEMENT.read_text(encoding="utf-8")
        companion = IMPLEMENT_PREFLIGHT.read_text(encoding="utf-8")
        preflight = skill.index("stage-0-architecture-preflight.md")
        compact_route = skill.index("If `ce-spec.md` or `tasks.json` is missing")
        binding = skill.index(
            "After the artifacts exist, complete the companion's spec-binding check"
        )
        mutation = skill.index("Ensure `.test-guard/` is ignored")
        self.assertLess(preflight, compact_route)
        self.assertLess(compact_route, binding)
        self.assertLess(binding, mutation)
        lint = companion.index("scripts/plan-lint.py")
        selection_lint = companion.index("scripts/architecture-selection-lint.py")
        architecture_lint = companion.index("scripts/architecture-lint.py")
        context_check = companion.index("scripts/architecture_context.py")
        self.assertLess(lint, selection_lint)
        self.assertLess(selection_lint, architecture_lint)
        self.assertLess(architecture_lint, context_check)
        self.assertIn("missing required\ndisposition/direction (`A12`/`A13`)", companion)
        self.assertIn("--require-architecture-direction --json", companion)
        self.assertIn("--consumer --json", companion)
        self.assertIn("`convergence.decision_refs` entry", companion)
        self.assertIn("readable regular ADR recorded as\n`Status: accepted`", companion)
        self.assertIn("refuse implementation", companion)
        self.assertIn("Only a recorded exit 0 proceeds", skill)
        self.assertIn("human acknowledgement never", skill)

    def test_implement_inventory_and_absence_matrix_precede_code_mutation(self):
        skill = IMPLEMENT.read_text(encoding="utf-8")
        companion = IMPLEMENT_PREFLIGHT.read_text(encoding="utf-8")
        transaction = companion.index(".architecture-publish-")
        occupied_lint = companion.index("scripts/architecture-lint.py")
        absence = companion.index("Missing-package implementation disposition")
        mutation = skill.index("Ensure `.test-guard/` is ignored")
        self.assertLess(transaction, occupied_lint)
        self.assertLess(occupied_lint, absence)
        self.assertLess(
            skill.index("stage-0-architecture-preflight.md"), mutation
        )
        for transaction_kind in ("lock", "stage", "backup", "rejected"):
            self.assertIn(transaction_kind, companion)
        self.assertIn("`required` + convergence `converged`", companion)
        self.assertIn("coverage gap — recommended package explicitly deferred", companion)
        self.assertIn("N/A — plan disposition not-required", companion)
        self.assertIn("selected direction + convergence `converged`", companion)
        self.assertNotIn("| `waived` |", companion)
        self.assertIn("A dirty\n  tree is not a gate", skill)
        self.assertNotIn("**Proceed** gate", skill)
        self.assertNotIn("single-feature minimal", companion)

    def test_canonical_plan_floor_has_no_feature_count_retirement_branch(self):
        stage = (ARCH / "stage-0-2-evidence-model.md").read_text(encoding="utf-8")
        audit = (
            REPO
            / "plugins/core-engineering/skills/ce-plan-audit/SKILL.md"
        ).read_text(encoding="utf-8")
        resolve = stage.index("### 0.1 Resolve the registered plan directory")
        plan_floor = stage.index("### 0.3 Run the deterministic plan floor")
        self.assertLess(resolve, plan_floor)
        self.assertRegex(
            stage,
            r"Every feature\s+count uses this one plan-directory shape",
        )
        self.assertIn("Require regular, non-symlink `plan.json`", stage)
        self.assertNotIn("architecture-retire.py", stage)
        self.assertNotIn("Single-Feature Architecture Disposition", stage)
        self.assertIn("Missing `plan.json`", audit)
        self.assertIn("--require-architecture-direction --json", audit)
        self.assertNotIn("single-feature minimal", audit)
        self.assertNotIn("minimal-output", audit)
        self.assertNotIn("Confirm scope with the human", audit)

    def test_baseline_architecture_requires_selection_and_direction_before_synthesis(self):
        stage = (ARCH / "stage-0-2-evidence-model.md").read_text(encoding="utf-8")
        floor = stage.index("### 0.3 Run the deterministic plan floor")
        selection_lint = stage.index("scripts/architecture-selection-lint.py", floor)
        plan_lint = stage.index("scripts/plan-lint.py", selection_lint)
        synthesis = stage.index("### 0.4 Load the bounded evidence set", plan_lint)
        self.assertLess(floor, selection_lint)
        self.assertLess(selection_lint, plan_lint)
        self.assertLess(plan_lint, synthesis)
        self.assertIn("--require-current-schema", stage[selection_lint:plan_lint])
        self.assertIn("--require-architecture-direction --json", stage[plan_lint:synthesis])
        self.assertIn("either exit 1", stage[selection_lint:synthesis])
        self.assertIn("either exit 2", stage[selection_lint:synthesis])
        self.assertIn("route to `/core-engineering:ce-plan` Stage R", stage[selection_lint:synthesis])
        self.assertIn("cannot authorize baseline synthesis", stage[selection_lint:synthesis])
        self.assertIn("Only the current receipt-bound architecture schema", stage)

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
        package_check = architecture.index("### 0.5 Existing-package check")
        self.assertLess(scan, package_check)
        self.assertIn("never record architecture as absent", spec)
        self.assertIn(
            "never infer absence through an\nincomplete publication", plan_revision
        )

    def test_transaction_recovery_precedes_the_canonical_plan_floor(self):
        architecture = (ARCH / "stage-0-2-evidence-model.md").read_text(
            encoding="utf-8"
        )
        transaction_scan = architecture.index(".architecture-publish-")
        plan_floor = architecture.index("Run the deterministic plan floor")
        evidence = architecture.index("Load the bounded evidence set")
        self.assertLess(transaction_scan, plan_floor)
        self.assertLess(plan_floor, evidence)
        self.assertNotIn("registry-backed single-feature minimal", architecture)
        self.assertNotIn("/core-engineering:ce-spec <slug>/<id>", architecture)

    def test_spec_uses_canonical_plan_authority_and_normal_output(self):
        stage = (SPEC / "stage-0-1-frame-resolve.md").read_text(encoding="utf-8")
        skill = (SPEC / "SKILL.md").read_text(encoding="utf-8")
        write = (SPEC / "stage-4-5-tasks-write.md").read_text(encoding="utf-8")
        for text in (stage, skill):
            self.assertIn("plan.json", text)
            self.assertIn("architecture-selection.json", text)
            self.assertIn("shared-context.md", text)
            self.assertIn("features/<id>.md", text)
            self.assertNotIn("single-feature-minimal", text)
            self.assertNotIn("N/A by construction", text)
        self.assertIn("ce-spec.md` and `tasks.json", write)
        self.assertIn("derive docs/plans/<slug> <id> --json", write)
        self.assertNotIn("--plan-mode", write)

    def test_plan_template_uses_one_directory_shape_for_every_feature_count(self):
        template = PLAN_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("## Plan Directory Structure", template)
        self.assertIn("features/<id>.md", template)
        self.assertIn("## Plan Manifest (`plan.json`)", template)
        self.assertNotIn("## Recommended Minimal Output", template)

    def test_implement_and_review_consume_the_canonical_plan(self):
        implement = IMPLEMENT.read_text(encoding="utf-8")
        review = REVIEW.read_text(encoding="utf-8")
        review_preflight = REVIEW_PREFLIGHT.read_text(encoding="utf-8")
        for text in (implement,):
            self.assertIn("plan.json", text)
            self.assertIn("architecture-selection.json", text)
            self.assertIn("features/<id>.md", text)
            self.assertIn("/core-engineering:ce-plan", text)
            self.assertNotIn("single-feature-minimal", text)
            self.assertNotIn("N/A by construction", text)
        self.assertIn("stage-0-architecture-preflight.md", review)
        self.assertIn("scripts/plan-lint.py", review_preflight)
        self.assertIn("scripts/architecture-selection-lint.py", review_preflight)
        self.assertIn("/core-engineering:ce-plan", review_preflight)
        self.assertNotIn("single-feature-minimal", review + review_preflight)
        self.assertNotIn("N/A by construction", review + review_preflight)

    def test_review_consumes_canonical_security_and_interaction_contracts(self):
        review = REVIEW.read_text(encoding="utf-8")
        self.assertIn("docs/plans/<slug>/threat-model.md", review)
        self.assertIn("docs/plans/<slug>/interaction-contract.md", review)
        self.assertIn("plan_conflict", review)
        self.assertIn("/core-engineering:ce-plan", review)
        self.assertIn("confirmed", review)
        self.assertNotIn("inline Security Projection", review)
        self.assertNotIn("N/A by construction", review)

    def test_implement_requires_canonical_spec_authority(self):
        implement = IMPLEMENT.read_text(encoding="utf-8")
        companion = IMPLEMENT_PREFLIGHT.read_text(encoding="utf-8")
        self.assertIn("plan.json.features[].specification_route", implement)
        self.assertIn("**Specification route:** compact|explicit", implement)
        self.assertIn("ce-spec.md", implement)
        self.assertIn("tasks.json", implement)
        self.assertIn("spec-lint.py", implement)
        self.assertIn("plan.json", implement)
        self.assertIn("architecture-selection.json", implement)
        self.assertIn(
            "after canonical `ce-spec.md` and `tasks.json` exist",
            companion,
        )
        self.assertIn("Run sections 1–2 before trusting or compact-composing", companion)
        self.assertIn("## 3. Require the spec's exact current binding", companion)
        self.assertIn("exact feature row", implement)
        self.assertIn("never append or guess a row", implement)
        self.assertNotIn("single-feature-minimal", implement)
        self.assertNotIn("single-feature-minimal", companion)

    def test_review_preflights_and_binds_current_architecture_context(self):
        review = REVIEW.read_text(encoding="utf-8")
        companion = REVIEW_PREFLIGHT.read_text(encoding="utf-8")
        self.assertIn("stage-0-architecture-preflight.md", review)
        self.assertLess(
            review.index("stage-0-architecture-preflight.md"),
            review.index("## Stage 1 — Review"),
        )
        plan_lint = companion.index("scripts/plan-lint.py")
        selection_lint = companion.index("scripts/architecture-selection-lint.py")
        package_lint = companion.index("scripts/architecture-lint.py")
        context_check = companion.index("check docs/plans/<slug>/specs/<id>")
        review_binding = companion.index(
            "review-binding docs/plans/<slug>/specs/<id>"
        )
        self.assertLess(plan_lint, selection_lint)
        self.assertLess(selection_lint, package_lint)
        self.assertLess(package_lint, context_check)
        self.assertLess(context_check, review_binding)
        self.assertIn("unknown implementation surface", companion)
        template = (
            REPO / "plugins/core-engineering/skills/ce-review/artifact-template.md"
        ).read_text(encoding="utf-8")
        for field in (
            '"plan_sha256"',
            '"feature_sha256"',
            '"spec_sha256"',
            '"tasks_sha256"',
            '"architecture_context_sha256"',
            '"architecture_package_receipt_sha256"',
            '"implementation_files_sha256"',
            '"repository_state_sha256"',
            '"commit_sha"',
        ):
            self.assertIn(field, template)

    def test_auto_build_uses_strict_spec_and_review_provenance_gates(self):
        pipeline = AUTO_PIPELINE.read_text(encoding="utf-8")
        self.assertIn("--require-architecture-context --json", pipeline)
        self.assertIn(
            "--repo-root . --plan-dir \"docs/plans/<slug>\" --feature <id>",
            pipeline,
        )
        self.assertIn("persisted architecture binding differs", pipeline)
        self.assertIn("plan/feature/spec/package/commit `binding`", pipeline)
        review_call = pipeline[pipeline.index(
            'scripts/review-gate.py'
        ):pipeline.index(
            "Every high-severity", pipeline.index("scripts/review-gate.py")
        )]
        self.assertIn("--require-blocking-route --json", review_call)
        sweep = pipeline.index("final review-freshness sweep")
        integration = pipeline.index("## Integration verification")
        verification_worker = pipeline.index(
            "spawn one fresh verification worker"
        )
        self.assertLess(integration, verification_worker)
        self.assertLess(verification_worker, sweep)
        sweep_end = pipeline.index(
            "Do not repair integration failures", sweep
        )
        self.assertIn("every completed\nfeature", pipeline[sweep:sweep_end])
        self.assertIn(
            "stale or mismatched binding", pipeline[sweep:sweep_end]
        )

    def test_breaking_lean_core_declares_one_canonical_contract(self):
        compatibility = (REPO / "docs/COMPATIBILITY.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("## Breaking lean-core release", compatibility)
        self.assertIn(
            "one canonical plan-directory shape replaces special "
            "feature-count modes",
            compatibility,
        )
        self.assertIn(
            "architecture work runs only when load-bearing and uses an iterative\n"
            "  evidence/question/adjust/selection loop",
            compatibility,
        )
        self.assertIn(
            "only actual human decisions are gates",
            compatibility,
        )
        self.assertIn(
            "Do not preserve old artifact modes by weakening validators or "
            "fabricating\nreceipts",
            compatibility,
        )
        self.assertIn(
            "Re-run the owning workflow on a representative branch",
            compatibility,
        )

    def test_retired_architecture_waiver_is_absent_from_active_consumers(self):
        paths = (
            REPO / "plugins/core-engineering/skills/ce-plan/artifact-template.md",
            REPO / "plugins/core-engineering/skills/ce-plan-audit/scripts/plan-lint.py",
            ARCH / "scripts/architecture-lint.py",
            SPEC / "scripts/architecture_context.py",
            SPEC / "SKILL.md",
            SPEC / "stage-0-1-frame-resolve.md",
            SPEC / "stage-4-5-tasks-write.md",
            SPEC / "artifact-template.md",
            IMPLEMENT_PREFLIGHT,
            REVIEW_PREFLIGHT,
            AUTO_BUILD / "SKILL.md",
            AUTO_BUILD / "stage-0-kickoff.md",
        )
        for path in paths:
            with self.subTest(path=path.relative_to(REPO)):
                self.assertNotIn("waived", path.read_text(encoding="utf-8").lower())

    def test_validator_is_registered_fork(self):
        manifest = (REPO / "plugins/core-engineering/fork-manifest.json").read_text(
            encoding="utf-8"
        )
        self.assertIn("ce-architecture/scripts/architecture-lint.py", manifest)
        self.assertIn("ce-spec/scripts/architecture-lint.py", manifest)
        self.assertIn("ce-auto-build/scripts/architecture-lint.py", manifest)
        self.assertIn("ce-implement/scripts/architecture-lint.py", manifest)
        self.assertIn("ce-review/scripts/architecture-lint.py", manifest)
        self.assertIn("ce-architecture/scripts/architecture-render.py", manifest)
        self.assertIn("ce-spec/scripts/architecture-render.py", manifest)
        self.assertIn("ce-auto-build/scripts/architecture-render.py", manifest)
        self.assertIn("ce-implement/scripts/architecture-render.py", manifest)
        self.assertIn("ce-review/scripts/architecture-render.py", manifest)
        self.assertIn("ce-implement/scripts/plan-lint.py", manifest)
        self.assertIn("ce-review/scripts/plan-lint.py", manifest)
        self.assertIn("ce-architecture/scripts/architecture-selection-lint.py", manifest)
        self.assertIn("ce-spec/scripts/architecture-selection-lint.py", manifest)
        self.assertIn("ce-auto-build/scripts/architecture-selection-lint.py", manifest)
        self.assertIn("ce-implement/scripts/architecture-selection-lint.py", manifest)
        self.assertIn("ce-review/scripts/architecture-selection-lint.py", manifest)
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
